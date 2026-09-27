#!/usr/bin/env python3
"""Raspberry Pi status dashboard for the Waveshare 2.13inch e-Paper HAT (V4).

Shows date/time, CPU/RAM/temperature, weather (Open-Meteo, no API key), and
network status (IP address, Wi-Fi SSID or wired, online/offline).

If your panel is a different Waveshare model, change the `epd2in13_V4` import
and class name below to match your model (e.g. epd2in7, epd2in9_V2) -- the
rest of the script (drawing, data collection) does not need to change.
"""
import configparser
import importlib.machinery
import json
import logging
import os
import signal
import socket
import subprocess
import sys
import time
import types
from datetime import datetime
from pathlib import Path

import psutil
import qrcode
import requests
from PIL import Image, ImageDraw, ImageFont, ImageOps

import icons

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE_DIR / "config" / "config.ini"
DOOM_LOGO_PATH = BASE_DIR / "assets" / "doom_logo.png"
_logo_missing_warned = False
# Written by the DSI kiosk launcher (/usr/local/bin/dsi-kiosk.sh) while an
# on-demand kiosk (Ezykam, Camera) is open: line 1 is the screen title (e.g.
# "CAMERA MODE ON"), line 2 the label (e.g. "Ezykam"). Lives in the tmpfs
# runtime dir so a crash or reboot can't leave it stale.
KIOSK_FLAG = Path("/run/user") / str(os.getuid()) / "kiosk-mode"
# Written by pinet-ups-guard while the UPS battery is flat and a power-off is
# counting down: one line, the power-off time (epoch seconds). tmpfs, so a
# reboot never leaves it behind.
UPS_LOW_FLAG = Path("/run/pinet-ups-low")
UPS_COUNTDOWN_REFRESH = 5   # seconds between countdown redraws (partial refreshes)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("eink-dashboard")

FONT_DIR = Path("/usr/share/fonts/truetype/roboto/unhinted/RobotoTTF")
FONT_REGULAR_PATH = str(FONT_DIR / "Roboto-Regular.ttf")
FONT_BOLD_PATH = str(FONT_DIR / "Roboto-Bold.ttf")
FONT_SMALL = ImageFont.truetype(FONT_REGULAR_PATH, 13)

# Open-Meteo WMO weather codes -> short description
WEATHER_CODES = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Rime fog",
    51: "Light drizzle", 53: "Drizzle", 55: "Dense drizzle",
    56: "Freezing drizzle", 57: "Freezing drizzle",
    61: "Slight rain", 63: "Rain", 65: "Heavy rain",
    66: "Freezing rain", 67: "Freezing rain",
    71: "Slight snow", 73: "Snow", 75: "Heavy snow", 77: "Snow grains",
    80: "Rain showers", 81: "Rain showers", 82: "Violent showers",
    85: "Snow showers", 86: "Snow showers",
    95: "Thunderstorm", 96: "Thunderstorm+hail", 99: "Thunderstorm+hail",
}


def load_config():
    cfg = configparser.ConfigParser()
    cfg.read(CONFIG_PATH)
    if "dashboard" not in cfg:
        cfg["dashboard"] = {}
    return cfg["dashboard"]


def is_dark_mode(cfg):
    """True during configured night hours (dark_mode_start_hour..dark_mode_end_hour).
    Both bounds accept fractional hours (e.g. 17.5 = 5:30 PM) for
    minute-level precision, not just whole hours."""
    start = cfg.getfloat("dark_mode_start_hour", fallback=20)
    end = cfg.getfloat("dark_mode_end_hour", fallback=6)
    if start == end:
        return False
    now = datetime.now()
    t = now.hour + now.minute / 60
    if start < end:
        return start <= t < end
    return t >= start or t < end


def reverse_geocode(lat, lon):
    try:
        r = requests.get(
            "https://api.bigdatacloud.net/data/reverse-geocode-client",
            params={"latitude": lat, "longitude": lon, "localityLanguage": "en"},
            timeout=5,
        )
        r.raise_for_status()
        data = r.json()
        return data.get("city") or data.get("locality") or data.get("principalSubdivision")
    except Exception as exc:
        logger.warning("Reverse geocoding failed: %s", exc)
        return None


def get_location(cfg):
    lat = cfg.get("latitude", fallback="").strip()
    lon = cfg.get("longitude", fallback="").strip()
    if lat and lon:
        lat, lon = float(lat), float(lon)
        return lat, lon, reverse_geocode(lat, lon)
    try:
        r = requests.get("http://ip-api.com/json/", timeout=5)
        r.raise_for_status()
        data = r.json()
        name = data.get("city") or data.get("regionName")
        return float(data["lat"]), float(data["lon"]), name
    except Exception as exc:
        logger.warning("IP geolocation failed: %s", exc)
        return None, None, None


def get_weather(lat, lon):
    if lat is None or lon is None:
        return None
    try:
        url = (
            "https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat}&longitude={lon}"
            "&current=temperature_2m,relative_humidity_2m,weather_code"
        )
        r = requests.get(url, timeout=8)
        r.raise_for_status()
        cur = r.json()["current"]
        return {
            "temp": cur["temperature_2m"],
            "humidity": cur["relative_humidity_2m"],
            "code": cur["weather_code"],
            "desc": WEATHER_CODES.get(cur["weather_code"], "Unknown"),
        }
    except Exception as exc:
        logger.warning("Weather fetch failed: %s", exc)
        return None


def get_system_stats():
    cpu = psutil.cpu_percent(interval=1)
    mem = psutil.virtual_memory()
    ram_pct = mem.percent
    # Deliberately (total - available), not mem.used: mem.percent is itself
    # derived from mem.available (Linux's "reclaimable cache doesn't count
    # as used" model, matching free(1)'s "available" column and htop), but
    # mem.used follows a different accounting rule -- pairing mem.percent
    # with mem.used/total made the two numbers on this line disagree (e.g.
    # "46%  0.3GB" when 0.3GB is actually 36% of total RAM). This keeps both
    # figures on the same basis so they're mutually consistent.
    ram_used_gb = (mem.total - mem.available) / (1024 ** 3)
    try:
        cpu_temp = psutil.sensors_temperatures()["cpu_thermal"][0].current
    except Exception:
        cpu_temp = None
    return cpu, ram_pct, ram_used_gb, cpu_temp


def is_wifi_pentest_active():
    """True while wlan1 (the Pi's home WiFi uplink, normally NetworkManager-
    managed) has been switched to monitor mode by
    /usr/local/sbin/wifi-pentest-start for use with WiFi pentesting tools.
    wlan1 has no route to anything while in this state, so get_network_status()
    already reports "Offline" -- this just lets the network box show *why*
    instead of looking like an ordinary connectivity drop. Returns False
    (never raises) if wlan1 doesn't exist or `iw` isn't available, e.g. off
    this specific Pi. The /run/pentest-mode flag (dropped by kali-power-shed
    via wifi-pentest-start) is the authoritative signal and also covers the
    brief window before wlan1 actually reports monitor mode."""
    if os.path.exists("/run/pentest-mode"):
        return True
    try:
        out = subprocess.run(
            ["/usr/sbin/iw", "dev", "wlan1", "info"],
            capture_output=True, text=True, timeout=3,
        ).stdout
        return "type monitor" in out
    except Exception:
        return False


PWR_LED = Path("/sys/class/leds/PWR")


def pwr_led_says_low():
    """True while the red PWR LED is off in its "input" mode: it mirrors the
    Pi 3B's PWR_LOW_N line, so off = under-voltage. Unlike get_throttled this
    still works with avoid_warnings=2 in config.txt, which this Pi runs (full
    CPU clock) and which zeroes the firmware's under-voltage flags."""
    try:
        if "[input]" not in (PWR_LED / "trigger").read_text():
            return False
        return (PWR_LED / "brightness").read_text().strip() == "0"
    except OSError:
        return False


def get_power_status():
    """Core voltage and *current* under-voltage/throttle flags from vcgencmd
    -- this Pi's supply has a history of under-voltage events, so the
    carousel's image screen surfaces it directly. Only bits 0 (under-voltage
    now) and 2 (throttled now) are read, not the "has occurred since boot"
    history bits (16/18), since those stay set long after the condition
    clears and would make a recovered Pi look like it's still in trouble.
    Any return value is None if vcgencmd isn't available (e.g. not running
    on a Pi)."""
    voltage = None
    try:
        out = subprocess.run(
            ["/usr/bin/vcgencmd", "measure_volts", "core"],
            capture_output=True, text=True, timeout=3,
        ).stdout.strip()
        voltage = float(out.split("=")[1].rstrip("V"))
    except Exception:
        pass

    under_voltage_now = None
    throttled_now = None
    try:
        out = subprocess.run(
            ["/usr/bin/vcgencmd", "get_throttled"],
            capture_output=True, text=True, timeout=3,
        ).stdout.strip()
        flags = int(out.split("=")[1], 16)
        under_voltage_now = bool(flags & 0x1)
        throttled_now = bool(flags & 0x4)
    except Exception:
        pass
    if pwr_led_says_low():
        under_voltage_now = True

    return voltage, under_voltage_now, throttled_now


BATTERY_READER = "/usr/local/bin/pinet-battery"
BATTERY_RETRY_SECONDS = 60   # no HAT found: don't look again before this
_battery = None   # (reader module, open SMBus, INA219 address) once found
_battery_missing_since = None   # monotonic time the last search came up empty
_rest_volts = []   # last SMOOTH resting voltages, averaged like the taskbar does


def _drop_battery():
    global _battery
    if _battery is not None:
        try:
            _battery[1].close()
        except Exception:
            pass
    _battery = None


def get_battery():
    """{"percent": int, "state": "charging"|"battery"|"full", "charging": bool}
    from the UPS HAT, or None when there is no HAT (or I2C is off).

    Loads /usr/local/bin/pinet-battery -- the reader the taskbar icon runs --
    as a module, so the INA219 maths lives in one place, and keeps its bus
    open: the wait loop polls this every few seconds to catch a charger
    being plugged in or pulled, and a python subprocess per poll would cost
    the Pi 3B real CPU."""
    global _battery, _battery_missing_since, _rest_volts
    if _battery is None and _battery_missing_since is not None \
            and time.monotonic() - _battery_missing_since < BATTERY_RETRY_SECONDS:
        return None
    try:
        if _battery is None:
            loader = importlib.machinery.SourceFileLoader("pinet_battery", BATTERY_READER)
            mod = types.ModuleType(loader.name)
            loader.exec_module(mod)
            from smbus2 import SMBus
            bus = SMBus(mod.BUS)
            addr = mod.find(bus)
            if addr is None:
                bus.close()
                _battery_missing_since = time.monotonic()
                return None
            _battery, _battery_missing_since, _rest_volts = (mod, bus, addr), None, []
        mod, bus, addr = _battery
        volts, amps = mod.read(bus, addr)
        state = mod.power_state(amps)
        _rest_volts = (_rest_volts + [mod.rest_volts(volts, amps)])[-mod.SMOOTH:]
        pct = mod.percent(sum(_rest_volts) / len(_rest_volts))
        return {"percent": pct, "state": state, "charging": state == "charging",
                "mah": mod.remaining_mah(pct), "capacity_mah": mod.CAPACITY_MAH}
    except Exception:
        # HAT gone or an I2C hiccup: close the bus (no fd leak) and look again
        # on the next call -- an unreadable reader counts as no HAT.
        _drop_battery()
        _battery_missing_since = time.monotonic()
        return None


CHARGE_SWEEP_FRAMES = 5
LOW_BATTERY_PCT = 15


def battery_fill(battery, frame=0):
    """Percent of the icon to fill on animation frame `frame`. Charging: the
    fill sweeps from the real level up to full in CHARGE_SWEEP_FRAMES steps and
    starts again, like a phone on its charger. On battery it sits still at the
    real level, except when low, where it blinks."""
    pct = battery["percent"]
    if battery["charging"]:
        step = frame % CHARGE_SWEEP_FRAMES
        return pct + (100 - pct) * step // (CHARGE_SWEEP_FRAMES - 1)
    if battery["state"] == "battery" and pct <= LOW_BATTERY_PCT:
        return pct if frame % 2 == 0 else 0
    return pct


BATTERY_LABELS = {"charging": "Charging", "battery": "On battery", "full": "Charged"}


def get_disk_usage(path="/"):
    """Free/used/total space (GB) for the root filesystem. The SD card
    fills up gradually (logs, uploads from the PINET file-share board,
    etc.), so this rides along on the same screen as the power health
    readout rather than needing its own carousel phase. Returns
    (None, None, None) if the check fails for any reason."""
    try:
        usage = psutil.disk_usage(path)
        gb = 1024 ** 3
        return usage.free / gb, usage.used / gb, usage.total / gb
    except Exception:
        return None, None, None


def get_ip_address():
    """Local IP of the interface used for outbound traffic (no packets sent)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(1)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return None


def get_wifi_ssid(iface=None):
    """SSID of `iface`, or of whichever Wi-Fi interface iwgetid finds first
    if no interface is given. Now that wlan0 can also be a Wi-Fi interface
    (running as the PINET hotspot) at the same time as a station interface
    like wlan1, an unqualified query is ambiguous -- callers that already
    know the active interface should pass it explicitly."""
    cmd = ["/usr/sbin/iwgetid", "-r"]
    if iface:
        cmd.append(iface)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=3)
        ssid = result.stdout.strip()
        return ssid or None
    except Exception:
        return None


def get_active_interface(ip):
    """Name of the interface that owns `ip` (the address actually used for
    outbound traffic), or None if it can't be matched."""
    if not ip:
        return None
    try:
        for name, addrs in psutil.net_if_addrs().items():
            if any(addr.family == socket.AF_INET and addr.address == ip for addr in addrs):
                return name
    except Exception:
        pass
    return None


def _is_wifi(iface, ssid):
    """Whether the active connection is Wi-Fi. Prefers checking the interface
    that is actually carrying traffic -- unlike relying on SSID association
    alone, this doesn't get stuck on "WiFi" when Ethernet is plugged in while
    wlan0 stays associated to an access point in the background."""
    if iface:
        return iface.startswith(("wl", "ww"))
    return bool(ssid)


def get_network_status():
    ip = get_ip_address()
    iface = get_active_interface(ip)
    ssid = get_wifi_ssid(iface)
    return {"ip": ip, "is_wifi": _is_wifi(iface, ssid)}


def get_network_fingerprint():
    """Cheap (ip, is_wifi) snapshot for detecting a network change during a
    poll loop -- unlike get_wifi_credentials(), this never shells out to sudo."""
    ip = get_ip_address()
    iface = get_active_interface(ip)
    ssid = get_wifi_ssid(iface)
    return (ip, _is_wifi(iface, ssid))


def get_wifi_credentials():
    """(ssid, password) for the currently active Wi-Fi connection, or (None, None)
    if not currently on Wi-Fi (e.g. connected via Ethernet, even if wlan0 stays
    associated to an access point in the background). Looked up fresh each
    call, so it always reflects the Pi's current network config."""
    iface = get_active_interface(get_ip_address())
    ssid = get_wifi_ssid(iface)
    if not ssid or not _is_wifi(iface, ssid):
        return None, None
    try:
        result = subprocess.run(
            ["sudo", "-n", "nmcli", "-s", "-g", "802-11-wireless-security.psk",
             "connection", "show", ssid],
            capture_output=True, text=True, timeout=5,
        )
        # A broken sudoers grant (bad file permissions, revoked rule, etc.)
        # exits non-zero with stderr but doesn't raise -- log it here too,
        # not just the except below, or this failure mode goes completely
        # silent (this exact case happened once: see the vault's
        # "power and undervoltage" note, sudoers permissions section).
        if result.returncode != 0:
            logger.warning(
                "Wi-Fi password lookup failed (rc=%s): %s",
                result.returncode, result.stderr.strip(),
            )
            return ssid, None
        password = result.stdout.strip()
        return ssid, (password or None)
    except Exception as exc:
        logger.warning("Wi-Fi password lookup failed: %s", exc)
        return ssid, None


def get_hotspot_passphrase(hostapd_conf="/etc/hostapd/hostapd.conf"):
    """The PINET passphrase, read live from hostapd's own config (world-
    readable, no sudo needed) rather than hardcoded -- so a screen showing
    it always matches whatever hostapd is actually broadcasting."""
    try:
        with open(hostapd_conf) as f:
            for line in f:
                if line.startswith("wpa_passphrase="):
                    return line.split("=", 1)[1].strip()
    except Exception as exc:
        logger.warning("Hotspot passphrase read failed: %s", exc)
    return None


def get_board_password(path="/etc/pinet-board/guest_password_plaintext.txt"):
    """The PINET board's GUEST password, for display next to the Wi-Fi join
    QR on the hotspot screen -- same "physical display only" trust model as
    get_hotspot_passphrase() above. Shows the GUEST tier deliberately: the
    admin password can delete uploads, so it must NOT appear on a screen
    anyone near the Pi can read. Plaintext copies are written solely for this
    display by /opt/pinet-board/set_guest_password.py (guest) and
    set_password.py (admin); the web app only ever checks salted hashes.
    Never falls back to the admin plaintext: if the guest file is missing,
    empty or unreadable the Board row is simply left off."""
    try:
        with open(path) as f:
            return f.read().strip() or None
    except Exception:
        return None


def get_hotspot_status(iface="wlan0", ssid="PINET"):
    """Whether the PINET access point is up, how many devices are
    associated -- read from hostapd's service state and a live `iw` station
    dump rather than the dnsmasq lease file, so the count reflects actual
    Wi-Fi associations instead of leases that may be stale/expired -- its
    passphrase, so the carousel screen can show a scannable QR code the
    same way the home Wi-Fi screen does -- and the PINET board's portal
    password, shown alongside that same QR."""
    password = get_hotspot_passphrase()
    board_password = get_board_password()
    storage_free_gb, _storage_used, storage_total_gb = get_disk_usage("/mnt/pinet-media")
    try:
        active = subprocess.run(
            ["systemctl", "is-active", "hostapd"],
            capture_output=True, text=True, timeout=3,
        ).stdout.strip() == "active"
    except Exception:
        active = False
    if not active:
        return {
            "active": False, "ssid": ssid, "ip": None, "client_count": 0,
            "password": password, "board_password": board_password,
            "storage_free_gb": storage_free_gb, "storage_total_gb": storage_total_gb,
        }

    ip = None
    for addr in psutil.net_if_addrs().get(iface, []):
        if addr.family == socket.AF_INET:
            ip = addr.address
            break

    client_count = 0
    try:
        result = subprocess.run(
            ["/usr/sbin/iw", "dev", iface, "station", "dump"],
            capture_output=True, text=True, timeout=3,
        )
        client_count = result.stdout.count("Station ")
    except Exception as exc:
        logger.warning("Hotspot station dump failed: %s", exc)

    return {
        "active": True, "ssid": ssid, "ip": ip, "client_count": client_count,
        "password": password, "board_password": board_password,
        "storage_free_gb": storage_free_gb, "storage_total_gb": storage_total_gb,
    }


def _librespot_live_state():
    """'playing' when the librespot PipeWire node is actually flowing audio,
    else None. The --onevent state file only changes when librespot emits an
    event, so a session already playing when the hook started (or between
    events) would otherwise look idle -- this live check fixes that. The
    dashboard runs as rupal, so pw-dump reaches the user PipeWire with
    XDG_RUNTIME_DIR set. Best-effort."""
    try:
        env = dict(os.environ)
        env.setdefault("XDG_RUNTIME_DIR", "/run/user/1000")
        out = subprocess.run(
            ["pw-dump"], capture_output=True, text=True, timeout=4, env=env,
        ).stdout
        for o in json.loads(out):
            info = o.get("info") or {}
            props = info.get("props") or {}
            name = str(props.get("application.name", "")).lower()
            if name.startswith("librespot") or props.get("media.software") == "Spotify":
                if info.get("state") == "running":
                    return "playing"
    except Exception:
        pass
    return None


def get_spotify_status():
    """Now-playing info for the Spotify panel shown on the hotspot carousel
    screen when PINET is down. Track title/artist come from the librespot
    --onevent state file (raspotify-nowplaying-hook); the play/idle state is
    taken from the live PipeWire node so it is right even between events.
    Returns None when raspotify isn't running so the caller can say so."""
    try:
        active = subprocess.run(
            ["systemctl", "is-active", "raspotify"],
            capture_output=True, text=True, timeout=3,
        ).stdout.strip() == "active"
    except Exception:
        active = False
    if not active:
        return None
    data = {"state": "idle", "name": "", "artists": "", "album": "", "output": ""}
    try:
        with open("/run/user/1000/raspotify-nowplaying") as f:
            for line in f:
                key, _, val = line.strip().partition("=")
                if key in data:
                    data[key] = val
    except OSError:
        pass
    if _librespot_live_state() == "playing":
        data["state"] = "playing"
    elif data["state"] == "playing":
        data["state"] = "idle"
    return data


def get_kiosk_mode():
    """(title, label) while a DSI kiosk is open (see KIOSK_FLAG), else None."""
    try:
        lines = [l.strip() for l in KIOSK_FLAG.read_text().splitlines() if l.strip()]
    except OSError:
        return None
    if len(lines) >= 2:
        return lines[0], lines[1]
    return "KIOSK MODE ON", (lines[0] if lines else "Kiosk")


UPS_COUNTDOWN_STALE = 30   # overdue by this much: the guard is gone, ignore it


def get_ups_countdown():
    """Seconds until pinet-ups-guard powers off (0 when due), or None."""
    try:
        deadline = float(UPS_LOW_FLAG.read_text().split()[0])
    except (OSError, ValueError, IndexError):
        return None
    left = deadline - time.time()
    if left < -UPS_COUNTDOWN_STALE:
        return None
    return max(0, round(left))


def _text_width(draw, text, font):
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0]


def fit_text(draw, text, font_path, max_size, min_size, max_width):
    """Shrink font size to fit max_width; truncate with '..' only as a last resort."""
    for size in range(max_size, min_size - 1, -1):
        font = ImageFont.truetype(font_path, size)
        if _text_width(draw, text, font) <= max_width:
            return text, font
    font = ImageFont.truetype(font_path, min_size)
    trimmed = text
    while len(trimmed) > 1 and _text_width(draw, trimmed + "..", font) > max_width:
        trimmed = trimmed[:-1]
    return (trimmed + ".." if trimmed else ".."), font


def _centre_block(draw, width, icon_size, gap, lines, font):
    """x for an icon and for a left-aligned text column, so the icon plus the
    widest line sits centred in *width*. Text lines stay left-aligned with each
    other -- centring each line separately would make an IP jitter under its
    label every time the address changes length."""
    text_w = max(draw.textlength(line, font=font) for line in lines)
    x_icon = (width - (icon_size + gap + text_w)) / 2
    return int(x_icon), int(x_icon + icon_size + gap)


def draw_stat_box(draw, x, y, w, h, label, value, secondary, icon_fn):
    """The hero tile: a large value takes the visual weight, with quiet
    label/secondary text around it. Only weather and network use this --
    they're the two things worth a glance from across the room, unlike the
    diagnostic CPU/RAM figures (see draw_mini_stat)."""
    draw.rectangle((x, y, x + w, y + h), outline=0)
    icon_fn(x, y)
    text_x = x + 34
    max_width = x + w - text_x - 3

    label_text, label_font = fit_text(draw, label, FONT_REGULAR_PATH, 13, 9, max_width)
    draw.text((text_x, y + 4), label_text, font=label_font, fill=0)

    value_text, value_font = fit_text(draw, value, FONT_BOLD_PATH, 26, 16, max_width)
    draw.text((text_x, y + 20), value_text, font=value_font, fill=0)

    if secondary:
        # Centred across the whole tile, not indented to text_x like the label
        # and value: the icon sits on the value row, so nothing occupies the
        # left of this row and a short secondary (a 10.10.10.1, a "Hum 71%")
        # left-aligned at text_x reads as pushed off-centre. Fit to the full
        # width for the same reason.
        secondary_text, secondary_font = fit_text(draw, secondary, FONT_REGULAR_PATH, 13, 9, w - 6)
        sec_w = draw.textlength(secondary_text, font=secondary_font)
        draw.text((x + (w - sec_w) / 2, y + h - 20), secondary_text, font=secondary_font, fill=0)


def draw_mini_stat(draw, x, y, w, h, icon_fn, text):
    """Compact single-line stat: icon + one line of text, deliberately lower
    visual weight than draw_stat_box -- CPU/RAM are diagnostic figures, not
    the thing worth a glance from across the room."""
    icon_fn(x, y)
    text_x = x + 20
    max_width = x + w - text_x - 2
    line, font = fit_text(draw, text, FONT_BOLD_PATH, 12, 9, max_width)
    draw.text((text_x, y + (h - font.size) // 2 - 1), line, font=font, fill=0)


def render(epd, cpu, ram_pct, ram_used_gb, cpu_temp, weather, net, location_name, dark_mode=False,
           battery=None):
    # Landscape canvas: panel is physically portrait (epd.width x epd.height),
    # so we draw on a rotated (height x width) image -- this is the standard
    # Waveshare convention and getbuffer() handles the rotation back.
    image = Image.new("1", (epd.height, epd.width), 255)
    draw = ImageDraw.Draw(image)
    W = epd.height  # 250

    now = datetime.now()
    date_text = now.strftime("%a %d %b")
    time_text = now.strftime("%-I:%M:%S %p")
    # UPS HAT charge centred between date and time: a small phone-style
    # battery filled to the level and the percentage, with a bolt in front
    # while on mains (charging or charged) and none when running on it.
    batt_text = f"{battery['percent']}%" if battery else ""
    on_mains = bool(battery) and battery["state"] != "battery"
    glyph_w = (icons.POWER_GLYPH_W + 2 if on_mains else 0) + HEADER_BATT_W + 3
    for size in range(18, 12, -1):
        header_font = ImageFont.truetype(FONT_BOLD_PATH, size)
        date_w = _text_width(draw, date_text, header_font)
        time_w = _text_width(draw, time_text, header_font)
        batt_w = _text_width(draw, batt_text, header_font) + glyph_w + 16 if batt_text else 0
        if date_w + batt_w + time_w <= W - 8 - 10:
            break
    draw.text((4, 2), date_text, font=header_font, fill=0)
    time_w = _text_width(draw, time_text, header_font)
    draw.text((W - 4 - time_w, 2), time_text, font=header_font, fill=0)
    if batt_text:
        gap_l, gap_r = 4 + date_w, W - 4 - time_w
        bw = _text_width(draw, batt_text, header_font) + glyph_w
        bx = int((gap_l + gap_r - bw) / 2)
        mid = 3 + header_font.size // 2 + 1
        if on_mains:
            icons.bolt(draw, bx, mid - icons.POWER_GLYPH_H // 2)
            bx += icons.POWER_GLYPH_W + 2
        icons.battery(draw, bx, mid - HEADER_BATT_H // 2, battery["percent"],
                      w=HEADER_BATT_W, h=HEADER_BATT_H)
        draw.text((bx + HEADER_BATT_W + 3, 2), batt_text, font=header_font, fill=0)

    box_w = (W - 6) // 2
    col1_x = 2
    col2_x = col1_x + box_w + 2

    # System strip: CPU + RAM, compact and low-emphasis -- diagnostic
    # figures, not the thing worth a glance from across the room.
    strip_y = 27
    strip_h = 18
    draw.rectangle((col1_x, strip_y, col2_x + box_w, strip_y + strip_h), outline=0)
    draw.line((col2_x - 1, strip_y, col2_x - 1, strip_y + strip_h), fill=0)

    cpu_text = f"CPU {cpu:.0f}%" + (f"  {cpu_temp:.0f}°C" if cpu_temp is not None else "")
    draw_mini_stat(
        draw, col1_x, strip_y, box_w, strip_h,
        lambda x, y: icons.cpu_chip(draw, x + 3, y + 3, size=12),
        cpu_text,
    )

    ram_text = f"RAM {ram_pct:.0f}%  {ram_used_gb:.1f}GB"
    draw_mini_stat(
        draw, col2_x, strip_y, box_w, strip_h,
        lambda x, y: icons.ram_stick(draw, x + 3, y + 3, w=14, h=9),
        ram_text,
    )

    # Hero boxes: weather + network, promoted to the size that matters --
    # the two things actually worth a glance, unlike CPU/RAM above.
    hero_y = strip_y + strip_h + 2
    # -1: the box's bottom border is drawn AT y+h, so leave one pixel of
    # headroom below epd.width-1 (the canvas's last valid row) or that
    # border line falls fully off-canvas and never renders.
    hero_h = epd.width - hero_y - 1

    if weather:
        weather_label = (location_name or "WEATHER")[:12].upper()
        weather_value = f"{weather['temp']:.0f}°C"
        weather_secondary = f"Hum {weather['humidity']:.0f}%"
        weather_icon_fn = lambda x, y: icons.weather_icon(
            draw, weather["code"], x + 16, y + 42, night=dark_mode
        )
    else:
        weather_label = "WEATHER"
        weather_value = "--"
        weather_secondary = "No network" if not net["ip"] else "Unavailable"
        weather_icon_fn = lambda x, y: icons.exclamation(draw, x + 18, y + 42)

    draw_stat_box(
        draw, col1_x, hero_y, box_w, hero_h,
        weather_label, weather_value, weather_secondary, weather_icon_fn,
    )

    if net["ip"]:
        net_value = "WiFi" if net["is_wifi"] else "Wired"
        net_icon_fn = (
            (lambda x, y: icons.wifi(draw, x + 16, y + 44, size=11))
            if net["is_wifi"]
            else (lambda x, y: icons.wired(draw, x + 8, y + 34, size=13))
        )
    elif is_wifi_pentest_active():
        net_value = "Pentest"
        net_icon_fn = lambda x, y: icons.pirate(draw, x + 16, y + 44, size=10)
    else:
        net_value = "Offline"
        net_icon_fn = lambda x, y: icons.offline(draw, x + 16, y + 44, size=9)

    draw_stat_box(
        draw, col2_x, hero_y, box_w, hero_h,
        "NETWORK", net_value, net["ip"] or "", net_icon_fn,
    )

    if dark_mode:
        image = ImageOps.invert(image.convert("L")).convert("1")

    return image


def render_qr_screen(epd, ssid, password, net, dark_mode=False):
    image = Image.new("1", (epd.height, epd.width), 255)
    draw = ImageDraw.Draw(image)
    W, H = epd.height, epd.width

    if ssid and password:
        payload = f"WIFI:T:WPA;S:{ssid};P:{password};;"
        qr = qrcode.QRCode(border=1, box_size=3)
        qr.add_data(payload)
        qr.make(fit=True)
        qr_img = qr.make_image(fill_color="black", back_color="white").convert("1")

        # Full-width header for the SSID -- guarantees room even for a full
        # 32-character WPA SSID, unlike squeezing it beside the QR code.
        header = f"Wi-Fi: {ssid}"
        header_text, header_font = fit_text(draw, header, FONT_BOLD_PATH, 18, 9, W - 12)
        header_w = draw.textlength(header_text, font=header_font)
        draw.text(((W - header_w) / 2, 3), header_text, font=header_font, fill=0)

        qr_size = H - 28
        qr_img = qr_img.resize((qr_size, qr_size))
        qx, qy = (W - qr_size) // 2, 26
        image.paste(qr_img, (qx, qy))

        # Scan hint in the unused left margin -- not everyone recognizes a
        # Wi-Fi QR code on sight. A natural two-word-group phrase reads
        # more professionally than an all-caps word-per-line stack.
        hint_w = qx - 6
        hint_line1, hint_font1 = fit_text(draw, "Scan to join", FONT_REGULAR_PATH, 13, 8, hint_w)
        hint_line2, hint_font2 = fit_text(draw, "Wi-Fi", FONT_REGULAR_PATH, 13, 8, hint_w)
        draw.text((4, qy + qr_size // 2 - 18), hint_line1, font=hint_font1, fill=0)
        draw.text((4, qy + qr_size // 2), hint_line2, font=hint_font2, fill=0)
    elif ssid and not password:
        ssid_text, ssid_font = fit_text(draw, f"Connected to: {ssid}", FONT_REGULAR_PATH, 13, 9, W - 20)
        draw.text((10, H // 2 - 20), ssid_text, font=ssid_font, fill=0)
        # Guest-facing message, not a debug detail -- the technical reason
        # (e.g. a broken sudoers grant) goes to the log via
        # get_wifi_credentials(), never onto this screen: whoever's
        # reading this has no way to act on "check sudoers setup" anyway.
        draw.text((10, H // 2), "Ask your host for", font=FONT_SMALL, fill=0)
        draw.text((10, H // 2 + 16), "the Wi-Fi password", font=FONT_SMALL, fill=0)
    elif net["ip"]:
        # Icon doubled in size here (was 12) -- this is the one screen that
        # explicitly tells the user "you're on Ethernet", so it gets the
        # most prominent rendering of the icon, unlike its compact use in
        # the NETWORK hero box on the status screen.
        # Centred as one icon+text group: the x values used to be hard-coded,
        # which left the whole block sitting left of centre on the panel.
        x_icon, x_text = _centre_block(draw, W, 24, 10,
                                       ["Connected via Ethernet", net["ip"]], FONT_SMALL)
        icons.wired(draw, x_icon, H // 2 - 18, size=24)
        draw.text((x_text, H // 2 - 14), "Connected via Ethernet", font=FONT_SMALL, fill=0)
        draw.text((x_text, H // 2 + 2), net["ip"], font=FONT_SMALL, fill=0)
    else:
        x_icon, x_text = _centre_block(draw, W, 12, 8,
                                       ["No network connection", "(offline)"], FONT_SMALL)
        icons.exclamation(draw, x_icon, H // 2 - 2, size=12)
        draw.text((x_text, H // 2 - 14), "No network connection", font=FONT_SMALL, fill=0)
        draw.text((x_text, H // 2 + 2), "(offline)", font=FONT_SMALL, fill=0)

    if dark_mode:
        image = ImageOps.invert(image.convert("L")).convert("1")

    return image


HEADER_BATT_W, HEADER_BATT_H = 20, 10
SPOTIFY_BATT_W, SPOTIFY_BATT_H = 34, 16


def spotify_battery_xy(W):
    """Top-left of the animated battery on the Spotify screen: right end of
    the "Portal not active" row, room left for "100%" after it. Fixed (not
    measured from the current text) so animation frames can redraw just the
    icon in place."""
    pct_w = int(FONT_SMALL.getlength("100%"))
    return W - 10 - pct_w - 4 - SPOTIFY_BATT_W, 23


def draw_spotify_battery(draw, x, y, battery, frame, color=0):
    icons.battery(draw, x, y, battery_fill(battery, frame), charging=battery["state"] != "battery",
                  w=SPOTIFY_BATT_W, h=SPOTIFY_BATT_H, color=color)


def render_hotspot_screen(epd, hotspot, dark_mode=False, battery=None):
    image = Image.new("1", (epd.height, epd.width), 255)
    draw = ImageDraw.Draw(image)
    W, H = epd.height, epd.width

    header = hotspot["ssid"]
    header_text, header_font = fit_text(draw, header, FONT_BOLD_PATH, 18, 9, W - 12)
    header_w = draw.textlength(header_text, font=header_font)
    draw.text(((W - header_w) / 2, 3), header_text, font=header_font, fill=0)

    if hotspot["active"]:
        icons.antenna(draw, 22, 30, size=14)

        # Reserve the right ~90px for the join QR code (added below).
        qr_reserved = 90 if hotspot.get("password") else 0

        # Device count -- the screen's hero number. Moved up and slightly
        # smaller than the old 40px so a PINET storage row now fits below the
        # board password without crowding the bottom edge.
        count_text, count_font = fit_text(
            draw, str(hotspot["client_count"]), FONT_BOLD_PATH, 34, 18, W - 58 - qr_reserved
        )
        draw.text((50, 18), count_text, font=count_font, fill=0)

        label = "device" if hotspot["client_count"] == 1 else "devices"
        label_text, label_font = fit_text(
            draw, f"{label} connected", FONT_REGULAR_PATH, 12, 8, W - 55 - qr_reserved
        )
        draw.text((50, 55), label_text, font=label_font, fill=0)

        # Three compact info rows in the left column (the QR owns the right
        # ~90px): board password, PINET file-storage free space, and the
        # board's IP. board_password is shown full-width here rather than in
        # the QR's narrow column so a longer password stays readable.
        if hotspot.get("board_password"):
            board_text, board_font = fit_text(
                draw, f"Board: {hotspot['board_password']}",
                FONT_REGULAR_PATH, 13, 8, W - 20 - qr_reserved,
            )
            draw.text((10, 73), board_text, font=board_font, fill=0)

        free_gb = hotspot.get("storage_free_gb")
        total_gb = hotspot.get("storage_total_gb")
        if free_gb is not None and total_gb:
            storage_text, storage_font = fit_text(
                draw, f"Storage: {free_gb:.0f}GB free of {total_gb:.0f}GB",
                FONT_REGULAR_PATH, 12, 8, W - 20 - qr_reserved,
            )
            draw.text((10, 90), storage_text, font=storage_font, fill=0)

        if hotspot["ip"]:
            draw.text((10, 106), hotspot["ip"], font=FONT_SMALL, fill=0)

        # Join QR code -- previously this screen showed the SSID and
        # device count but gave a guest no way to actually join without
        # asking someone for the password; matches the same WIFI: QR
        # convention as the home network's render_qr_screen.
        if hotspot.get("password"):
            payload = f"WIFI:T:WPA;S:{hotspot['ssid']};P:{hotspot['password']};;"
            qr = qrcode.QRCode(border=1, box_size=2)
            qr.add_data(payload)
            qr.make(fit=True)
            qr_img = qr.make_image(fill_color="black", back_color="white").convert("1")
            qr_size = 68
            qr_img = qr_img.resize((qr_size, qr_size))
            qx, qy = W - qr_size - 8, 22
            image.paste(qr_img, (qx, qy))
            caption_text, caption_font = fit_text(
                draw, "scan to join", FONT_REGULAR_PATH, 13, 8, W - qx - 2
            )
            draw.text((qx, qy + qr_size + 2), caption_text, font=caption_font, fill=0)
    else:
        # PINET is down (on-demand default). Keep the "Portal not active"
        # notice, and use the rest of the screen for a Spotify (raspotify)
        # now-playing panel.
        icons.offline(draw, 22, 30, size=8)
        draw.text((36, 22), "Portal not active", font=FONT_SMALL, fill=0)
        if battery:
            bx, by = spotify_battery_xy(W)
            draw_spotify_battery(draw, bx, by, battery, 0, color=0)
            draw.text((bx + SPOTIFY_BATT_W + 4, 22), f"{battery['percent']}%", font=FONT_SMALL, fill=0)
            label = BATTERY_LABELS.get(battery["state"], "")
            draw.text((W - 10 - draw.textlength(label, font=FONT_SMALL), 4), label, font=FONT_SMALL, fill=0)
        draw.line((10, 42, W - 10, 42), fill=0)

        sp = get_spotify_status()
        icons.spotify(draw, 20, 54, size=8)
        draw.text((34, 46), "Spotify", font=FONT_SMALL, fill=0)
        out = (sp or {}).get("output") or ""
        if out:
            out_text, out_font = fit_text(draw, "> " + out, FONT_REGULAR_PATH, 12, 8, W - 96)
            ow = draw.textlength(out_text, font=out_font)
            draw.text((W - 10 - ow, 47), out_text, font=out_font, fill=0)

        state = (sp or {}).get("state", "")
        name = (sp or {}).get("name", "")
        artists = (sp or {}).get("artists", "")
        if sp is None:
            msg, mfont = fit_text(draw, "raspotify not running", FONT_REGULAR_PATH, 13, 9, W - 24)
            draw.text((12, 74), msg, font=mfont, fill=0)
        elif state in ("playing", "paused") and name:
            name_text, name_font = fit_text(draw, name, FONT_BOLD_PATH, 16, 10, W - 24)
            draw.text((12, 66), name_text, font=name_font, fill=0)
            badge = "[playing]" if state == "playing" else ("[paused]" if state == "paused" else "")
            bw = int(draw.textlength(badge, font=FONT_SMALL)) if badge else 0
            art_text, art_font = fit_text(draw, artists, FONT_REGULAR_PATH, 13, 9, W - 30 - bw)
            draw.text((12, 90), art_text, font=art_font, fill=0)
            if badge:
                draw.text((W - 10 - bw, 90), badge, font=FONT_SMALL, fill=0)
        elif state == "playing":
            line1, f1 = fit_text(draw, "Playing", FONT_BOLD_PATH, 16, 10, W - 24)
            draw.text((12, 66), line1, font=f1, fill=0)
            draw.text((12, 90), "PINET", font=FONT_SMALL, fill=0)
        else:
            line1, f1 = fit_text(draw, "Nothing playing", FONT_REGULAR_PATH, 14, 10, W - 24)
            draw.text((12, 70), line1, font=f1, fill=0)
            draw.text((12, 92), "PINET", font=FONT_SMALL, fill=0)

    if dark_mode:
        image = ImageOps.invert(image.convert("L")).convert("1")

    return image


def render_battery_low_screen(epd, seconds_left, battery=None, dark_mode=False):
    """Takes over the carousel while pinet-ups-guard counts down to a power-off
    on a flat battery: what is happening, how long is left, and how to stop it."""
    W, H = epd.height, epd.width
    image = Image.new("1", (W, H), 255)
    draw = ImageDraw.Draw(image)

    def centered(text, font_path, max_size, min_size, y):
        line, font = fit_text(draw, text, font_path, max_size, min_size, W - 12)
        draw.text(((W - draw.textlength(line, font=font)) / 2, y), line, font=font, fill=0)

    bw, bh = 56, 26
    icons.battery(draw, (W - bw) // 2, 6, battery["percent"] if battery else 0, w=bw, h=bh)
    centered("BATTERY LOW", FONT_BOLD_PATH, 22, 12, 38)
    centered(f"Shutting down in {seconds_left} s", FONT_BOLD_PATH, 17, 10, 66)
    centered("Plug in the charger to cancel", FONT_REGULAR_PATH, 14, 9, 94)

    if dark_mode:
        image = ImageOps.invert(image.convert("L")).convert("1")
    return image


def render_kiosk_screen(epd, title, label, dark_mode=False):
    """Replaces the whole carousel while a DSI kiosk is open. The kiosk
    launcher stops the PINET hotspot + board for the duration (frees power
    and CPU for the browser), hence the "PINET paused" line."""
    W, H = epd.height, epd.width
    image = Image.new("1", (W, H), 255)
    draw = ImageDraw.Draw(image)

    def centered(text, font_path, max_size, min_size, y):
        line, font = fit_text(draw, text, font_path, max_size, min_size, W - 12)
        draw.text(((W - draw.textlength(line, font=font)) / 2, y), line, font=font, fill=0)

    centered(title, FONT_BOLD_PATH, 24, 12, 8)
    centered(label, FONT_BOLD_PATH, 34, 14, 42)
    centered("PINET paused", FONT_REGULAR_PATH, 14, 9, 94)

    if dark_mode:
        image = ImageOps.invert(image.convert("L")).convert("1")

    return image


def render_image_screen(epd, image_path, dark_mode=False, voltage=None,
                         under_voltage=None, throttled=None, disk_free_gb=None,
                         disk_used_gb=None, disk_total_gb=None, pentest=False, battery=None):
    """Renders an arbitrary image file for the carousel's third screen
    (currently the DOOM logo): loaded, downscaled to fit the panel
    (aspect-preserved, letterboxed), and dithered to 1-bit so grayscale
    detail (the logo's grunge texture) survives as stipple rather than
    being lost to a hard threshold. Voltage/under-voltage/throttle status
    from get_power_status() is a header row above the logo; used/total/free
    disk space from get_disk_usage() is a separate footer row below it --
    kept on their own rows (not sharing one line) so neither reads as
    subordinate to the other. No rule lines anywhere -- each row's own
    padding reads as separation without a hard line competing with the
    logo's dithered texture."""
    global _logo_missing_warned
    W, H = epd.height, epd.width
    margin = 4
    header_h = 16
    footer_h = 16
    # UPS battery row just above the disk row: the logo gives up 16px for it.
    # Not in pentest mode: its skull and label use their own layout.
    battery = None if pentest else battery
    batt_h = 16 if battery else 0
    image_area_h = H - header_h - footer_h - batt_h
    image_area_y = header_h

    image = Image.new("1", (W, H), 255)
    draw = ImageDraw.Draw(image)

    if pentest:
        # Pentest power mode (wlan1 in monitor mode / kali-power-shed flag): a
        # large skull-and-crossbones plus label replaces the logo AND the disk
        # footer, so the carousel makes the pentest session obvious.
        cx = W // 2
        icons.pirate(draw, cx, image_area_y + 32, size=38)
        label_line, label_font = fit_text(draw, "PENTEST MODE", FONT_BOLD_PATH, 18, 11, W - 2 * margin)
        lw = draw.textlength(label_line, font=label_font)
        draw.text(((W - lw) // 2, H - 19), label_line, font=label_font, fill=0)
    else:
        try:
            src = Image.open(image_path).convert("L")
        except OSError as exc:
            # The logo isn't in git (it only lives on the device), so a fresh
            # clone has no file -- draw a plain text title in its place
            # rather than failing the whole screen. Warned once, not every
            # refresh, so it doesn't flood the journal.
            if not _logo_missing_warned:
                logger.warning("Logo image unavailable (%s), showing text instead", exc)
                _logo_missing_warned = True
            src = None
        if src is not None:
            scale = min((W - 2 * margin) / src.width, (image_area_h - 2 * margin) / src.height)
            scaled_w, scaled_h = max(1, round(src.width * scale)), max(1, round(src.height * scale))
            src = src.resize((scaled_w, scaled_h), Image.LANCZOS).convert("1")
            image.paste(src, ((W - scaled_w) // 2, image_area_y + (image_area_h - scaled_h) // 2))
        else:
            title, title_font = fit_text(draw, "DOOM", FONT_BOLD_PATH, 56, 16, W - 2 * margin)
            left, top, right, bottom = draw.textbbox((0, 0), title, font=title_font)
            draw.text(
                ((W - (right - left)) // 2 - left, image_area_y + (image_area_h - top - bottom) // 2),
                title, font=title_font, fill=0,
            )

    volt_text = f"{voltage:.2f}V" if voltage is not None else "V: n/a"
    problem = bool(under_voltage) or bool(throttled)
    if problem:
        icons.exclamation(draw, 12, header_h // 2, size=8)
        status_text = "LOW VOLTAGE" if under_voltage else "THROTTLED"
        text_x = 22
    else:
        status_text = "OK"
        text_x = 6
    draw.text((text_x, 2), f"{volt_text}  {status_text}", font=FONT_SMALL, fill=0)

    if battery:
        # Charge left out of the pack's capacity, and whether it is charging.
        y = header_h + image_area_h + 2
        text = f"{battery['percent']}%  ~{battery['mah']}/{battery['capacity_mah']}mAh  " \
               f"{BATTERY_LABELS.get(battery['state'], '')}"
        on_mains = battery["state"] != "battery"
        icon_w = (icons.POWER_GLYPH_W + 2 if on_mains else 0) + HEADER_BATT_W + 4
        line, font = fit_text(draw, text, FONT_REGULAR_PATH, 13, 8, W - 2 * margin - icon_w)
        x = int((W - icon_w - draw.textlength(line, font=font)) / 2)
        if on_mains:
            icons.bolt(draw, x, y + 1)
            x += icons.POWER_GLYPH_W + 2
        icons.battery(draw, x, y + 2, battery["percent"], w=HEADER_BATT_W, h=HEADER_BATT_H)
        draw.text((x + HEADER_BATT_W + 4, y - 1), line, font=font, fill=0)

    if not pentest:
        if disk_used_gb is not None and disk_total_gb is not None and disk_free_gb is not None:
            disk_text = f"{disk_used_gb:.1f}/{disk_total_gb:.1f}GB used · {disk_free_gb:.1f}GB free"
        else:
            disk_text = "disk: n/a"
        disk_line, disk_font = fit_text(draw, disk_text, FONT_REGULAR_PATH, 13, 8, W - 2 * margin)
        draw.text((6, header_h + image_area_h + batt_h + 2), disk_line, font=disk_font, fill=0)

    if dark_mode:
        image = ImageOps.invert(image.convert("L")).convert("1")

    return image


def main():
    # Imported here, not at module level: the waveshare_epd package claims GPIO
    # pins as a side effect of import, so keeping it out of the module scope
    # lets render()/render_qr_screen() be imported and tested (e.g. for preview
    # rendering) without touching hardware or conflicting with a running service.
    from waveshare_epd import epd2in13_V4

    cfg = load_config()
    refresh_minutes = cfg.getint("refresh_minutes", fallback=5)
    # Each carousel phase can dwell for a different length of time (e.g. the
    # QR screen doesn't need as long as the status screen) -- order matches
    # PHASE_NAMES / the phase dispatch below.
    phase_durations = [
        cfg.getfloat("status_seconds", fallback=180),
        cfg.getfloat("qr_seconds", fallback=30),
        cfg.getfloat("doom_seconds", fallback=180),
        cfg.getfloat("hotspot_seconds", fallback=180),
    ]
    cycle_total = sum(phase_durations)
    network_poll_seconds = cfg.getint("network_poll_seconds", fallback=5)
    # Seconds per frame of the Spotify screen's battery animation (partial
    # refreshes of just that icon); 0 turns the animation off.
    battery_anim_seconds = cfg.getfloat("battery_anim_seconds", fallback=2)
    # How often the UPS HAT is read between refreshes while a battery is on
    # screen; a charger plugged in or pulled redraws the screen (partial
    # refresh) within about two of these.
    battery_poll_seconds = cfg.getfloat("battery_poll_seconds", fallback=2)
    # Whether location comes from IP geolocation (blank config) rather than a
    # fixed configured lat/lon -- only the former needs re-resolving when the
    # network changes, since ip-api.com geolocates the request's own public
    # IP: switching networks (e.g. home Wi-Fi -> a phone hotspot) can change
    # the egress point and therefore the resolved city, even though nothing
    # about a fixed configured location would ever change.
    has_fixed_location = bool(
        cfg.get("latitude", fallback="").strip() and cfg.get("longitude", fallback="").strip()
    )
    flip_180 = cfg.getboolean("flip_180", fallback=False)
    lat, lon, location_name = get_location(cfg)
    logger.info("Location for weather: lat=%s lon=%s name=%s", lat, lon, location_name)

    epd = epd2in13_V4.EPD()
    # monotonic, not time.time(): a Pi with no RTC can have a wrong wall clock
    # for the first several seconds after boot (then jump when NTP syncs),
    # which would throw off a wall-clock-anchored carousel right when this
    # matters most. monotonic() only ever counts forward from process start,
    # immune to wall-clock corrections.
    start_time = time.monotonic()
    # Bytes of the last frame actually pushed to the panel -- lets a
    # redraw be skipped whenever the new frame is pixel-identical to what
    # is already on screen (e.g. the DOOM screen's power/disk readout, or
    # the hotspot screen's device count, often hasn't changed between one
    # refresh_minutes tick and the next). Every e-ink refresh is a visible
    # full-panel flash and real wear; PIL's rendering is deterministic for
    # identical inputs, so a plain bytes comparison is exact, not a
    # heuristic.
    last_image_bytes = None
    # Last successful weather reading, reused when a fetch transiently
    # fails (Open-Meteo 503s, brief DNS/network blips) so the screen does
    # not flip to "Unavailable" for a cycle -- only Unavailable if weather
    # has never succeeded this run.
    last_weather = None
    # Which carousel cycle (0, 1, 2, ...) last got a full-quality refresh --
    # displayPartial() alone lets ghosting accumulate over successive
    # updates, so one full refresh per full pass through the carousel
    # resets it. None so the very first frame always gets a full refresh.
    last_full_refresh_cycle = None
    last_kiosk_app = None
    # Under-voltage/throttle debounce: a one-time spike (a single reading) is
    # ignored; the on-screen warning only appears once the live bit has been
    # set on this many consecutive reads. (get_power_status already excludes
    # the sticky "has occurred since boot" bits.)
    uv_min_readings = cfg.getint("undervoltage_min_readings", fallback=3)
    uv_streak = 0
    thr_streak = 0

    # systemd stops the service with SIGTERM, whose default action kills the
    # process on the spot -- the `finally:` below never ran, so the panel was
    # never put to sleep nor its GPIO released. Raising SystemExit routes it
    # through the same cleanup (SystemExit isn't an Exception, so the
    # per-frame handler in the loop doesn't swallow it).
    def _on_sigterm(signum, frame):
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, _on_sigterm)
    clear_on_exit = True

    try:
        while True:
            # Relative to start_time, not raw wall-clock: anchoring to absolute
            # time made the first screen after every restart a coin flip -- e.g.
            # a restart landing just after a phase boundary showed the QR screen
            # for up to a full phase duration before ever reaching the status
            # screen. Anchoring to start_time guarantees phase=0 (status) first.
            # Hotspot phase restored to the rotation (2026-09-06) -- it had
            # been dropped pending the Pi's under-voltage investigation,
            # but that investigation is ongoing indefinitely with no fix
            # in sight, and there's no reason a guest-facing feature (the
            # PINET join screen) should stay hidden the whole time.
            #
            # Each phase can have its own dwell time (phase_durations, e.g. a
            # short QR phase and a longer status phase), so the phase can't be
            # found with a single modulo the way a uniform carousel could --
            # walk the cumulative durations within one cycle instead, and keep
            # how much time is left in the current phase so the wait step
            # below never sleeps past a phase boundary.
            # Clamped strictly below cycle_total so the loop below is
            # guaranteed to `break` (and phase_start/phase to correspond to
            # the same iteration) rather than needing a fallback branch for
            # a float-precision edge case at the exact cycle boundary.
            elapsed_in_cycle = min((time.monotonic() - start_time) % cycle_total, cycle_total - 0.001)
            phase = 0
            phase_start = 0.0
            for i, dur in enumerate(phase_durations):
                if elapsed_in_cycle < phase_start + dur:
                    phase = i
                    break
                phase_start += dur
            remaining_in_phase = (phase_start + phase_durations[phase]) - elapsed_in_cycle

            dark_mode = is_dark_mode(cfg)
            volt_now, uv_now, thr_now = get_power_status()
            uv_streak = uv_streak + 1 if uv_now else 0
            thr_streak = thr_streak + 1 if thr_now else 0
            uv_show = uv_streak >= uv_min_readings
            thr_show = thr_streak >= uv_min_readings
            kiosk_app = get_kiosk_mode()
            # A low-battery countdown outranks everything, kiosks included.
            ups_left = get_ups_countdown()
            takeover = ("ups",) if ups_left is not None else kiosk_app
            if takeover != last_kiosk_app:
                # Entering/leaving kiosk mode (or the low-battery screen) swaps
                # the whole layout; force a full refresh so the old screen
                # doesn't ghost under the new.
                last_full_refresh_cycle = None
                last_kiosk_app = takeover

            # The frame last rendered (before flip_180) when the battery on the
            # Spotify screen should animate during the wait below, else None.
            anim_base = None
            # The battery reading drawn on this frame; None if the screen
            # shows no battery (then its state isn't watched below).
            battery = None
            try:
                if ups_left is not None:
                    logger.info("Battery low: power-off in %ss", ups_left)
                    battery = get_battery()
                    image = render_battery_low_screen(epd, ups_left, battery, dark_mode)
                elif kiosk_app:
                    logger.info("Kiosk mode on (%s / %s)", *kiosk_app)
                    image = render_kiosk_screen(epd, *kiosk_app, dark_mode=dark_mode)
                elif phase == 0:
                    logger.info("Carousel phase=0 (status)")
                    cpu, ram_pct, ram_used_gb, cpu_temp = get_system_stats()
                    # If location never resolved (network/DNS often isn't ready
                    # right after boot -- more so now that boot no longer waits
                    # for the network), keep retrying here so weather isn't dead
                    # for the whole session, not only when the network changes.
                    if (lat is None or lon is None) and not has_fixed_location:
                        lat, lon, location_name = get_location(cfg)
                        if lat is not None:
                            logger.info(
                                "Location resolved on retry: lat=%s lon=%s name=%s",
                                lat, lon, location_name,
                            )
                    new_weather = get_weather(lat, lon)
                    if new_weather:
                        weather = last_weather = new_weather
                    else:
                        # Transient failure (503 / blip): reuse the last good
                        # reading; None only if weather has never succeeded.
                        weather = last_weather
                    net = get_network_status()
                    battery = get_battery()
                    image = render(
                        epd, cpu, ram_pct, ram_used_gb, cpu_temp, weather, net,
                        location_name, dark_mode, battery=battery,
                    )
                elif phase == 1:
                    logger.info("Carousel phase=1 (qr)")
                    ssid, password = get_wifi_credentials()
                    net = get_network_status()
                    image = render_qr_screen(epd, ssid, password, net, dark_mode)
                elif phase == 2:
                    logger.info("Carousel phase=2 (doom)")
                    disk_free_gb, disk_used_gb, disk_total_gb = get_disk_usage()
                    battery = get_battery()
                    image = render_image_screen(
                        epd, DOOM_LOGO_PATH, dark_mode,
                        voltage=volt_now, under_voltage=uv_show, throttled=thr_show,
                        disk_free_gb=disk_free_gb, disk_used_gb=disk_used_gb, disk_total_gb=disk_total_gb,
                        pentest=is_wifi_pentest_active(), battery=battery,
                    )
                else:
                    logger.info("Carousel phase=3 (hotspot)")
                    hotspot = get_hotspot_status()
                    battery = get_battery()
                    image = render_hotspot_screen(epd, hotspot, dark_mode, battery=battery)
                    if hotspot["active"]:
                        battery = None   # the PINET join screen shows no battery
                    elif battery and battery_anim_seconds > 0:
                        anim_base = image

                if flip_180:
                    image = image.rotate(180)

                image_bytes = image.tobytes()
                if image_bytes != last_image_bytes:
                    buf = epd.getbuffer(image)
                    cycle_number = int((time.monotonic() - start_time) // cycle_total)
                    if cycle_number != last_full_refresh_cycle:
                        # Full refresh: this is the one that visibly flashes
                        # black/white (the panel's own ghost-clearing waveform),
                        # and also (re-)establishes the base image
                        # displayPartial() diffs against below. Deliberately
                        # limited to once per full carousel cycle instead of
                        # every refresh.
                        epd.init()
                        epd.display(buf)
                        epd.displayPartBaseImage(buf)
                        last_full_refresh_cycle = cycle_number
                    else:
                        # Partial refresh: updates only the changed pixels
                        # directly, no flash -- this is what makes a mode
                        # change (e.g. into dark mode) show up immediately
                        # instead of flashing white first.
                        epd.displayPartial(buf)
                    # Deliberately no epd.sleep() anywhere in this loop: it
                    # closes the SPI device and cuts GPIO power outright
                    # (waveshare_epd's module_exit()), and displayPartial()
                    # never reopens it -- only init()/init_fast() do, and
                    # init() does a SWRESET that would also break the
                    # base-image continuity displayPartial() diffs against.
                    # There's no way to sleep between a full refresh and the
                    # partial refreshes that follow it in the same cycle
                    # without breaking the next displayPartial() call --
                    # confirmed by two live crash-loops (Bad file descriptor)
                    # before landing on this. The panel driver (and its 5V
                    # rail) now stays powered for the life of the process;
                    # epd.sleep() still runs once in the `finally:` block
                    # below on actual shutdown/interrupt.
                    last_image_bytes = image_bytes
                else:
                    logger.info("Frame unchanged, skipping e-ink refresh")
            except Exception:
                anim_base = None
                # One bad frame (a render bug, an SPI hiccup, a missing asset)
                # must not take the whole dashboard down: before this, any
                # exception reached the `finally:` below, which blanked the
                # panel and exited, and systemd restarted it into the same
                # failure every cycle. Leave the last good frame on screen and
                # carry on to the normal wait below (so this is not a hot
                # loop). A failure part-way through a panel update can leave
                # displayPartial()'s base image out of step with the panel, so
                # force the next frame to be a full refresh.
                logger.exception("Failed to render/display phase %s, keeping last frame", phase)
                last_full_refresh_cycle = None

            # Wait for the next scheduled refresh, but poll the network and
            # wake up early if it changes (e.g. cable unplugged, Wi-Fi
            # switched) so the screen reflects it immediately instead of
            # waiting out the full interval. Capped to remaining_in_phase so
            # a phase shorter than refresh_minutes (e.g. a 30s QR phase with
            # a 60s refresh) still hands off on time instead of overshooting
            # into the next phase's dwell window.
            last_fingerprint = get_network_fingerprint()
            wait_seconds = max(1, min(refresh_minutes * 60, remaining_in_phase))
            elapsed = 0
            next_poll = network_poll_seconds
            next_frame = battery_anim_seconds
            next_batt = battery_poll_seconds
            tick = min((t for t in (
                network_poll_seconds,
                battery_poll_seconds if battery is not None else 0,
                battery_anim_seconds if anim_base else 0,
                UPS_COUNTDOWN_REFRESH if ups_left is not None else 0,
            ) if t > 0), default=5)   # every interval set to 0: still tick, don't crash
            frame = 0
            # Consecutive polls that saw a different power state from the one
            # on screen. Two in a row, so a current hovering at the
            # charging threshold can't flicker the panel.
            state_changes = 0
            while elapsed < wait_seconds:
                step = min(tick, wait_seconds - elapsed)
                time.sleep(step)
                elapsed += step
                # Checked every tick (a file read): a low-battery countdown
                # starting or being cancelled shows at once, and while it
                # runs the seconds left are redrawn every UPS_COUNTDOWN_REFRESH.
                if (get_ups_countdown() is None) != (ups_left is None):
                    break
                if ups_left is not None and elapsed >= UPS_COUNTDOWN_REFRESH:
                    break
                if battery is not None and elapsed >= next_batt:
                    next_batt = elapsed + battery_poll_seconds
                    now_batt = get_battery()
                    # Only plugging in or pulling the charger redraws at once;
                    # charging <-> charged waits for the normal refresh, so a
                    # current hovering at the threshold can't flicker the panel.
                    if now_batt and (now_batt["state"] == "battery") != (battery["state"] == "battery"):
                        state_changes += 1
                        if state_changes >= 2:
                            # Charger plugged in or pulled: re-render now.
                            # Within a cycle that is a partial refresh, so the
                            # new state shows without a flash.
                            logger.info("Power %s -> %s, refreshing early",
                                        battery["state"], now_batt["state"])
                            break
                    else:
                        state_changes = 0
                if anim_base and elapsed >= next_frame:
                    # Only the battery icon changes: a partial refresh of an
                    # otherwise identical frame, so no flash. In dark mode the
                    # frame is already inverted, hence the swapped colours.
                    next_frame = elapsed + battery_anim_seconds
                    frame += 1
                    try:
                        anim = anim_base.copy()
                        bx, by = spotify_battery_xy(anim.width)
                        draw_spotify_battery(ImageDraw.Draw(anim), bx, by, battery, frame,
                                             color=255 if dark_mode else 0)
                        if flip_180:
                            anim = anim.rotate(180)
                        anim_bytes = anim.tobytes()
                        if anim_bytes != last_image_bytes:   # a still icon costs no refresh
                            epd.displayPartial(epd.getbuffer(anim))
                            last_image_bytes = anim_bytes
                    except Exception:
                        logger.exception("Battery animation frame failed, stopping it")
                        anim_base = None
                        last_full_refresh_cycle = None
                if elapsed < next_poll:
                    continue
                next_poll = elapsed + network_poll_seconds
                if get_kiosk_mode() != kiosk_app:
                    logger.info("Kiosk mode changed, refreshing early")
                    break
                current_fingerprint = get_network_fingerprint()
                if current_fingerprint != last_fingerprint:
                    logger.info(
                        "Network changed %s -> %s, refreshing early",
                        last_fingerprint, current_fingerprint,
                    )
                    if not has_fixed_location:
                        lat, lon, location_name = get_location(cfg)
                        logger.info(
                            "Re-resolved location after network change: lat=%s lon=%s name=%s",
                            lat, lon, location_name,
                        )
                    break
    except KeyboardInterrupt:
        logger.info("Interrupted, clearing screen and exiting")
    except SystemExit:
        # Service stop (incl. shutdown/reboot): sleep the panel but don't
        # Clear() it -- a white flash here would be immediately overdrawn by
        # pi-eink-shutdown-splash.service (ordered to run after this exits),
        # and on a plain `systemctl stop` the last frame beats a blank panel.
        clear_on_exit = False
        logger.info("Stopped (SIGTERM), putting panel to sleep and exiting")
    finally:
        try:
            # init() is only a controller reset (no refresh, so no flash);
            # it's needed so sleep() has an open SPI device to talk to.
            epd.init()
            if clear_on_exit:
                epd.Clear(0xFF)
            epd.sleep()
            epd2in13_V4.epdconfig.module_exit(cleanup=True)
        except Exception as exc:
            logger.warning("Cleanup failed: %s", exc)


if __name__ == "__main__":
    main()
