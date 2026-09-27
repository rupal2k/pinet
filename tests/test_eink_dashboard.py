"""eink-dashboard/src/dashboard.py, imported whole with PIL/psutil/requests/
qrcode/icons stubbed. main() is run for real against a fake clock and a fake
Waveshare EPD; data collection and rendering are replaced by recorders.
"""
import configparser
import logging
import os
import shutil
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from _support import FakeClock, FakeDraw, dashboard_stubs, load_script, make_module, repo_path, stub_modules

DASH_PATH = repo_path("eink-dashboard", "src", "dashboard.py")


def load_dashboard():
    dash = load_script(DASH_PATH, "pinet_dashboard_under_test", dashboard_stubs())
    dash.logger.setLevel(logging.CRITICAL)
    return dash


def section(text="", name="dashboard"):
    cp = configparser.ConfigParser()
    cp.read_string(f"[{name}]\n{text}")
    return cp[name]


def fixed_now(dash, hour, minute):
    class FakeDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 9, 19, hour, minute)
    dash.datetime = FakeDatetime


class TmpDirCase(unittest.TestCase):
    def setUp(self):
        self.dash = load_dashboard()
        self.tmp = Path(tempfile.mkdtemp(prefix="pinet-dash-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)


class DarkMode(TmpDirCase):
    def check(self, cfg_text, hour, minute):
        fixed_now(self.dash, hour, minute)
        return self.dash.is_dark_mode(section(cfg_text))

    def test_fractional_evening_start(self):
        cfg = "dark_mode_start_hour = 17.5\ndark_mode_end_hour = 5.5\n"
        self.assertFalse(self.check(cfg, 17, 29))
        self.assertTrue(self.check(cfg, 17, 30))
        self.assertTrue(self.check(cfg, 23, 59))

    def test_wraps_midnight(self):
        cfg = "dark_mode_start_hour = 17.5\ndark_mode_end_hour = 5.5\n"
        self.assertTrue(self.check(cfg, 0, 0))
        self.assertTrue(self.check(cfg, 5, 29))
        self.assertFalse(self.check(cfg, 5, 30))
        self.assertFalse(self.check(cfg, 12, 0))

    def test_non_wrapping_range(self):
        cfg = "dark_mode_start_hour = 1\ndark_mode_end_hour = 4\n"
        self.assertTrue(self.check(cfg, 2, 0))
        self.assertFalse(self.check(cfg, 4, 0))
        self.assertFalse(self.check(cfg, 0, 59))

    def test_equal_bounds_disable_dark_mode(self):
        self.assertFalse(self.check("dark_mode_start_hour = 7\ndark_mode_end_hour = 7\n", 7, 0))

    def test_fallback_hours_20_to_6(self):
        self.assertTrue(self.check("", 21, 0))
        self.assertTrue(self.check("", 5, 59))
        self.assertFalse(self.check("", 6, 0))
        self.assertFalse(self.check("", 19, 59))


class Config(TmpDirCase):
    def test_shipped_config_parses(self):
        cfg = self.dash.load_config()
        self.assertEqual(cfg.getfloat("dark_mode_start_hour"), 17.5)
        self.assertEqual(cfg.getfloat("dark_mode_end_hour"), 5.5)
        self.assertTrue(cfg.getboolean("flip_180"))
        self.assertEqual(
            [cfg.getfloat(k) for k in ("status_seconds", "qr_seconds", "doom_seconds", "hotspot_seconds")],
            [180, 30, 180, 180])

    def test_missing_config_gives_empty_section_with_fallbacks(self):
        self.dash.CONFIG_PATH = self.tmp / "absent.ini"
        cfg = self.dash.load_config()
        self.assertEqual(cfg.name, "dashboard")
        self.assertEqual(cfg.getint("refresh_minutes", fallback=5), 5)

    def test_config_without_dashboard_section(self):
        p = self.tmp / "c.ini"
        p.write_text("[other]\nx = 1\n")
        self.dash.CONFIG_PATH = p
        self.assertEqual(dict(self.dash.load_config()), {})


class Passwords(TmpDirCase):
    def conf(self, text):
        p = self.tmp / "hostapd.conf"
        p.write_text(text)
        return str(p)

    def test_passphrase_read_from_hostapd_conf(self):
        path = self.conf("interface=wlan0\nssid=PINET\nwpa_passphrase=hunter2hunter2\nwpa=2\n")
        self.assertEqual(self.dash.get_hotspot_passphrase(path), "hunter2hunter2")

    def test_passphrase_missing_file_or_key(self):
        self.assertIsNone(self.dash.get_hotspot_passphrase(str(self.tmp / "nope")))
        self.assertIsNone(self.dash.get_hotspot_passphrase(self.conf("ssid=PINET\n")))

    # QA-4: .strip() alters passphrases with leading/trailing spaces; hostapd uses the value as-is.
    @unittest.expectedFailure
    def test_passphrase_whitespace_preserved(self):
        path = self.conf("wpa_passphrase= pass word \n")
        self.assertEqual(self.dash.get_hotspot_passphrase(path), " pass word ")

    # QA-4b: first wpa_passphrase= wins, but hostapd applies the last one, so the QR won't match.
    @unittest.expectedFailure
    def test_last_wpa_passphrase_wins(self):
        path = self.conf("wpa_passphrase=first111\nwpa_passphrase=second22\n")
        self.assertEqual(self.dash.get_hotspot_passphrase(path), "second22")

    def board_files(self, guest=None, admin="adminpw"):
        g, a = self.tmp / "guest.txt", self.tmp / "admin.txt"
        if guest is not None:
            g.write_text(guest)
        if admin is not None:
            a.write_text(admin)
        return str(g), str(a)

    def test_guest_password_shown(self):
        g, _a = self.board_files(guest="guestpw\n")
        self.assertEqual(self.dash.get_board_password(g), "guestpw")

    def test_never_falls_back_to_admin_password(self):
        # The admin password can delete uploads, so it must never reach the
        # e-ink panel. With no usable guest password the Board row is dropped.
        g, _a = self.board_files(guest=None)
        self.assertIsNone(self.dash.get_board_password(g))
        g, _a = self.board_files(guest="  \n")
        self.assertIsNone(self.dash.get_board_password(g))
        self.assertIsNone(self.dash.get_board_password(str(self.tmp / "no-guest")))

    # QA-3 (fixed on this branch): an unreadable guest file used to fall through
    # to the ADMIN password on the public e-ink. It now yields nothing at all.
    def test_unreadable_guest_file_does_not_expose_admin(self):
        g, a = self.board_files(guest="guestpw\n")
        os.chmod(g, 0)
        if os.access(g, os.R_OK):  # running as root: make it unreadable another way
            os.unlink(g)
            os.mkdir(g)
        self.assertIsNone(self.dash.get_board_password(g))


class KioskFlag(TmpDirCase):
    def mode(self, text=None):
        flag = self.tmp / "kiosk-mode"
        if text is not None:
            flag.write_text(text)
        self.dash.KIOSK_FLAG = flag
        return self.dash.get_kiosk_mode()

    def test_absent_flag(self):
        self.assertIsNone(self.mode(None))

    def test_title_and_label(self):
        self.assertEqual(self.mode("CAMERA MODE ON\nEzykam\n"), ("CAMERA MODE ON", "Ezykam"))
        self.assertEqual(self.mode("\n  T  \n\nL\n"), ("T", "L"))

    def test_partial_flags_get_defaults(self):
        self.assertEqual(self.mode("Camera\n"), ("KIOSK MODE ON", "Camera"))
        self.assertEqual(self.mode(""), ("KIOSK MODE ON", "Kiosk"))


class PowerStatus(TmpDirCase):
    def setUp(self):
        super().setUp()
        self.dash.PWR_LED = self.tmp / "no-led"

    def run_with(self, volts, throttled):
        def fake_run(cmd, **kw):
            if cmd[-1] == "core":
                out = volts
            else:
                out = throttled
            if isinstance(out, Exception):
                raise out
            return SimpleNamespace(stdout=out, returncode=0)
        self.dash.subprocess = SimpleNamespace(run=fake_run)
        return self.dash.get_power_status()

    def test_live_bits(self):
        self.assertEqual(self.run_with("volt=1.2000V\n", "throttled=0x5\n"), (1.2, True, True))
        self.assertEqual(self.run_with("volt=0.8563V\n", "throttled=0x1\n"), (0.8563, True, False))

    def test_sticky_history_bits_ignored(self):
        self.assertEqual(self.run_with("volt=1.2V\n", "throttled=0x50000\n"), (1.2, False, False))

    def test_pwr_led_catches_what_avoid_warnings_hides(self):
        led = self.tmp
        (led / "trigger").write_text("none [input] default-on\n")
        self.dash.PWR_LED = led
        (led / "brightness").write_text("0\n")
        self.assertTrue(self.dash.pwr_led_says_low())
        (led / "brightness").write_text("255\n")
        self.assertFalse(self.dash.pwr_led_says_low())
        (led / "trigger").write_text("[none] input default-on\n")   # LED repurposed: no signal
        (led / "brightness").write_text("0\n")
        self.assertFalse(self.dash.pwr_led_says_low())

    def test_led_marks_under_voltage_even_with_flags_zeroed(self):
        led = self.tmp
        (led / "trigger").write_text("[input]\n")
        (led / "brightness").write_text("0\n")
        self.dash.PWR_LED = led
        self.assertEqual(self.run_with("volt=1.2V\n", "throttled=0x0\n"), (1.2, True, False))

    def test_no_vcgencmd(self):
        self.assertEqual(self.run_with(FileNotFoundError(), FileNotFoundError()), (None, None, None))
        self.assertEqual(self.run_with("garbage", ""), (None, None, None))


class FitText(TmpDirCase):
    # FakeDraw: width = len(text) * font size
    def test_fits_at_max_size(self):
        text, font = self.dash.fit_text(FakeDraw(), "abc", "f.ttf", 10, 6, 30)
        self.assertEqual((text, font.size), ("abc", 10))

    def test_shrinks_before_truncating(self):
        text, font = self.dash.fit_text(FakeDraw(), "abcdef", "f.ttf", 10, 6, 40)
        self.assertEqual((text, font.size), ("abcdef", 6))

    def test_truncates_with_dots_at_min_size(self):
        text, font = self.dash.fit_text(FakeDraw(), "abcdefghij", "f.ttf", 10, 10, 50)
        self.assertEqual((text, font.size), ("abc..", 10))

    # QA-5: when even "x.." is too wide, fit_text returns text wider than max_width.
    @unittest.expectedFailure
    def test_result_never_wider_than_max_width(self):
        d = FakeDraw()
        text, font = self.dash.fit_text(d, "abcdef", "f.ttf", 10, 10, 25)
        self.assertLessEqual(self.dash._text_width(d, text, font), 25)


# ---------------------------------------------------------------------------
# main() on a fake clock / fake EPD
# ---------------------------------------------------------------------------

class Battery(TmpDirCase):
    def reader(self, body):
        path = self.tmp / "pinet-battery"
        path.write_text("BUS = 1\nSMOOTH = 6\n" + body)
        self.dash.BATTERY_READER = str(path)
        self.dash._battery = None
        self.dash._battery_missing_since = None
        self.dash._rest_volts = []
        self.closed = []
        smbus = make_module("smbus2", SMBus=lambda n: SimpleNamespace(close=lambda: self.closed.append(n)))
        return stub_modules({"smbus2": smbus})

    def test_uses_the_taskbar_reader_in_process(self):
        body = ("def find(bus): return 0x43\n"
                "def read(bus, addr): return 3.75, 2.2\n"
                "def rest_volts(v, a): return v\n"
                "def percent(v): return 62\n"
                "def remaining_mah(p): return 5210\n"
                "CAPACITY_MAH = 8400\n"
                "def power_state(a): return 'charging'\n")
        with self.reader(body):
            self.assertEqual(self.dash.get_battery(), {"percent": 62, "state": "charging", "charging": True,
                                                       "mah": 5210, "capacity_mah": 8400})
            self.assertEqual(self.dash.get_battery()["state"], "charging")  # bus kept open

    def test_no_hat_is_none(self):
        with self.reader("def find(bus): return None\n"):
            self.assertIsNone(self.dash.get_battery())

    def test_percent_is_averaged_like_the_taskbar(self):
        body = ("volts = iter([3.70, 3.80])\n"
                "def find(bus): return 0x43\n"
                "def read(bus, addr): return next(volts), 0.0\n"
                "def rest_volts(v, a): return v\n"
                "def percent(v): return round(v * 100)\n"
                "def remaining_mah(p): return 0\n"
                "def power_state(a): return 'full'\n"
                "CAPACITY_MAH = 8400\n")
        with self.reader(body):
            self.assertEqual(self.dash.get_battery()["percent"], 370)
            self.assertEqual(self.dash.get_battery()["percent"], 375)   # mean of 3.70 and 3.80

    def test_a_failed_read_closes_the_bus(self):
        body = ("def find(bus): return 0x43\n"
                "def read(bus, addr): raise OSError('i2c gone')\n")
        with self.reader(body):
            self.assertIsNone(self.dash.get_battery())
        self.assertEqual(self.closed, [1])

    def test_no_hat_is_not_searched_for_again_straight_away(self):
        with self.reader("calls = []\ndef find(bus):\n    calls.append(1)\n    return None\n"):
            self.assertIsNone(self.dash.get_battery())
            self.assertIsNone(self.dash.get_battery())
            self.assertEqual(len(self.closed), 1)          # searched once, not twice
            self.dash._battery_missing_since -= self.dash.BATTERY_RETRY_SECONDS
            self.assertIsNone(self.dash.get_battery())
            self.assertEqual(len(self.closed), 2)          # and again after the wait

    def test_missing_reader_is_none(self):
        self.dash.BATTERY_READER = str(self.tmp / "nope")
        self.dash._battery = None
        self.assertIsNone(self.dash.get_battery())

    def test_charging_sweeps_from_the_level_to_full(self):
        b = {"percent": 60, "state": "charging", "charging": True}
        self.assertEqual([self.dash.battery_fill(b, f) for f in range(6)], [60, 70, 80, 90, 100, 60])
        b = {"percent": 100, "state": "charging", "charging": True}
        self.assertEqual({self.dash.battery_fill(b, f) for f in range(5)}, {100})

    def test_on_battery_it_sits_still_unless_low(self):
        b = {"percent": 75, "state": "battery", "charging": False}
        self.assertEqual({self.dash.battery_fill(b, f) for f in range(4)}, {75})
        b = {"percent": 12, "state": "battery", "charging": False}
        self.assertEqual([self.dash.battery_fill(b, f) for f in range(4)], [12, 0, 12, 0])
        b = {"percent": 12, "state": "full", "charging": False}
        self.assertEqual({self.dash.battery_fill(b, f) for f in range(4)}, {12})


class UpsCountdown(TmpDirCase):
    def test_reads_seconds_left_from_the_guard_flag(self):
        flag = self.tmp / "pinet-ups-low"
        self.dash.UPS_LOW_FLAG = flag
        self.assertIsNone(self.dash.get_ups_countdown())
        flag.write_text(f"{self.dash.time.time() + 42:.0f}\n")
        self.assertIn(self.dash.get_ups_countdown(), (41, 42))
        flag.write_text(f"{self.dash.time.time() - 5:.0f}\n")
        self.assertEqual(self.dash.get_ups_countdown(), 0)      # just overdue, never negative
        flag.write_text("0\n")
        self.assertIsNone(self.dash.get_ups_countdown())        # long overdue: guard gone
        flag.write_text("garbage")
        self.assertIsNone(self.dash.get_ups_countdown())


class FakeEPD:
    def __init__(self, log):
        self.log = log

    def init(self):
        self.log.append("init")

    def display(self, buf):
        self.log.append("display")

    def displayPartBaseImage(self, buf):
        self.log.append("base")

    def displayPartial(self, buf):
        self.log.append("partial")

    def getbuffer(self, image):
        return image.tobytes()

    def Clear(self, color):
        self.log.append("clear")

    def sleep(self):
        self.log.append("sleep")


class FakeImage:
    counter = 0

    def __init__(self):
        FakeImage.counter += 1
        self.n = FakeImage.counter

    def tobytes(self):
        return str(self.n).encode()  # every frame differs

    width = 250

    def rotate(self, deg):
        return self

    def copy(self):
        return FakeImage()


class MainLoop(TmpDirCase):
    def run_main(self, cfg_text, seconds, power=None, kiosk=None, battery=None, hotspot=None, ups=None):
        dash = self.dash
        clock = FakeClock(stop_after=seconds)
        epd_log, frames = [], []
        dash.time = clock
        dash.load_config = lambda: section(cfg_text)
        dash.get_location = lambda cfg: (51.5, -0.1, "Here")
        dash.is_dark_mode = lambda cfg: False
        power_iter = iter(power or [])
        dash.get_power_status = lambda: next(power_iter, (1.2, False, False))
        dash.get_kiosk_mode = kiosk or (lambda: None)
        dash.get_system_stats = lambda: (1, 2, 0.5, 40)
        dash.get_weather = lambda lat, lon: {"t": 1}
        dash.get_network_status = lambda: {"online": True}
        dash.get_wifi_credentials = lambda: ("Home", "pw")
        dash.get_disk_usage = lambda path="/": (1, 2, 3)
        dash.is_wifi_pentest_active = lambda: False
        dash.get_hotspot_status = lambda: hotspot or {"active": True}
        dash.get_network_fingerprint = lambda: "fp"
        dash.get_battery = battery if callable(battery) else (lambda: battery)
        dash.get_ups_countdown = ups or (lambda: None)
        dash.icons.battery = lambda *a, **kw: None
        dash.spotify_battery_xy = lambda W: (0, 0)
        dash.draw_spotify_battery = lambda *a, **kw: None
        dash.ImageDraw.Draw = lambda image: None

        def recorder(name):
            def render(*a, **kw):
                frames.append((clock.elapsed, name, kw))
                return FakeImage()
            return render
        dash.render = recorder("status")
        dash.render_qr_screen = recorder("qr")
        dash.render_image_screen = recorder("doom")
        dash.render_hotspot_screen = recorder("hotspot")
        dash.render_kiosk_screen = recorder("kiosk")
        dash.render_battery_low_screen = recorder("ups")

        epd_mod = make_module("waveshare_epd.epd2in13_V4",
                              EPD=lambda: FakeEPD(epd_log),
                              epdconfig=SimpleNamespace(module_exit=lambda cleanup=False: epd_log.append("exit")))
        pkg = make_module("waveshare_epd", epd2in13_V4=epd_mod)
        with stub_modules({"waveshare_epd": pkg, "waveshare_epd.epd2in13_V4": epd_mod}):
            dash.main()
        return frames, epd_log

    DEFAULT = "refresh_minutes = 1\n"

    def test_first_screen_is_status_and_phase_order(self):
        frames, _ = self.run_main(self.DEFAULT, 600)
        starts = []
        for t, name, _ in frames:
            if not starts or starts[-1][1] != name:
                starts.append((t, name))
        self.assertEqual(starts, [(0, "status"), (180, "qr"), (210, "doom"), (390, "hotspot"), (570, "status")])

    def test_phase_never_overshoots_its_dwell(self):
        frames, _ = self.run_main(self.DEFAULT, 560)
        self.assertEqual([t for t, n, _ in frames if n == "qr"], [180])
        self.assertEqual([t for t, n, _ in frames if n == "status"], [0, 60, 120])

    def test_one_full_refresh_per_cycle(self):
        _, log = self.run_main(self.DEFAULT, 570 * 2 + 30)
        body = log[:-4]  # drop shutdown: init, clear, sleep, exit
        self.assertEqual(body.count("display"), 3)  # cycles 0, 1, 2
        self.assertEqual(log[-4:], ["init", "clear", "sleep", "exit"])
        self.assertGreater(body.count("partial"), 10)

    def test_kiosk_change_forces_full_refresh(self):
        state = {"n": 0}

        def kiosk():
            state["n"] += 1
            return ("CAMERA MODE ON", "Ezykam") if state["n"] > 3 else None
        frames, log = self.run_main(self.DEFAULT, 100, kiosk=kiosk)
        self.assertIn("kiosk", [n for _, n, _ in frames])
        self.assertEqual(log.count("display"), 2)  # first frame + entering kiosk

    def test_under_voltage_debounced_three_readings(self):
        cfg = "refresh_minutes = 1\nstatus_seconds = 0\nqr_seconds = 0\ndoom_seconds = 600\nhotspot_seconds = 0\n"
        seq = [(1.2, True, False), (1.2, True, False), (1.2, False, False),
               (1.2, True, True), (1.2, True, True), (1.2, True, True)]
        frames, _ = self.run_main(cfg, 330, power=seq)
        shown = [(kw["under_voltage"], kw["throttled"]) for _, n, kw in frames if n == "doom"]
        self.assertEqual(shown, [(False, False)] * 5 + [(True, True)])

    STATUS_ONLY = "refresh_minutes = 1\nstatus_seconds = 600\nqr_seconds = 0\ndoom_seconds = 0\nhotspot_seconds = 0\n"
    HOTSPOT_ONLY = "refresh_minutes = 1\nstatus_seconds = 0\nqr_seconds = 0\ndoom_seconds = 0\nhotspot_seconds = 600\n"

    def test_battery_animates_on_the_spotify_screen(self):
        batt = {"percent": 40, "state": "charging", "charging": True}
        frames, log = self.run_main(self.HOTSPOT_ONLY, 60, battery=batt, hotspot={"active": False})
        self.assertEqual([kw["battery"] for _, n, kw in frames if n == "hotspot"], [batt, batt])
        self.assertEqual(log.count("display"), 1)          # never a flash per frame
        self.assertGreaterEqual(log.count("partial"), 25)  # a frame every 2s

    def test_a_charger_change_on_the_spotify_screen_redraws_it(self):
        readings = iter([{"percent": 60, "state": "charging", "charging": True}] * 3
                        + [{"percent": 60, "state": "battery", "charging": False}] * 50)
        frames, log = self.run_main(self.HOTSPOT_ONLY, 30, battery=lambda: next(readings),
                                    hotspot={"active": False})
        drawn = [(t, kw["battery"]["state"]) for t, n, kw in frames if n == "hotspot"]
        self.assertEqual(drawn, [(0, "charging"), (8, "battery")])
        self.assertEqual(log.count("display"), 1)

    def test_no_animation_while_pinet_is_up_or_without_a_hat(self):
        for batt, hs in (({"percent": 40, "state": "charging", "charging": True}, {"active": True}), (None, {"active": False})):
            _, log = self.run_main(self.HOTSPOT_ONLY, 60, battery=batt, hotspot=hs)
            self.assertLessEqual(log.count("partial"), 1, (batt, hs))

    def test_power_state_change_refreshes_early(self):
        readings = iter([{"percent": 60, "state": "battery", "charging": False}] * 3
                        + [{"percent": 60, "state": "charging", "charging": True}] * 50)
        frames, log = self.run_main(self.STATUS_ONLY, 60, battery=lambda: next(readings))
        times = [t for t, n, _ in frames if n == "status"]
        self.assertEqual(times[:2], [0, 8])   # 2s polls: flip seen at 6s, confirmed at 8s
        self.assertEqual(log.count("display"), 1)  # the early redraw is a partial

    def test_a_one_off_blip_does_not_refresh(self):
        seq = [{"percent": 60, "state": "battery", "charging": False}] * 50
        seq[2] = {"percent": 60, "state": "full", "charging": False}
        readings = iter(seq)
        frames, _ = self.run_main(self.STATUS_ONLY, 59, battery=lambda: next(readings))
        self.assertEqual([t for t, n, _ in frames if n == "status"], [0])

    def test_low_battery_countdown_takes_over_and_leaves_again(self):
        def ups():
            t = self.dash.time.monotonic() - 1000
            return max(0, 60 - int(t)) if 20 <= t < 45 else None
        frames, log = self.run_main(self.DEFAULT, 90, ups=ups,
                                    kiosk=lambda: ("CAMERA MODE ON", "Ezykam"))
        names = [n for _, n, _ in frames]
        first_ups = names.index("ups")
        self.assertEqual(names[:first_ups], ["kiosk"])          # outranks a kiosk
        self.assertGreaterEqual(names.count("ups"), 4)          # redrawn as it counts
        self.assertEqual(names[-1], "kiosk")                    # cancelled -> back
        self.assertEqual(log.count("display"), 3)               # full refresh in and out only

    def test_every_poll_interval_zero_does_not_crash(self):
        cfg = self.DEFAULT + "network_poll_seconds = 0\n"
        frames, _ = self.run_main(cfg, 30)
        self.assertTrue(frames)

    def test_animation_can_be_turned_off(self):
        cfg = self.HOTSPOT_ONLY + "battery_anim_seconds = 0\n"
        _, log = self.run_main(cfg, 60, battery={"percent": 40, "state": "charging", "charging": True}, hotspot={"active": False})
        self.assertLessEqual(log.count("partial"), 1)

    # QA-6: all *_seconds = 0 -> ZeroDivisionError (float modulo) in main(); the service crash-loops.
    @unittest.expectedFailure
    def test_all_phases_zero_does_not_crash(self):
        cfg = "status_seconds = 0\nqr_seconds = 0\ndoom_seconds = 0\nhotspot_seconds = 0\n"
        try:
            self.run_main(cfg, 60)
        except ZeroDivisionError as exc:
            self.fail(f"main() crashed: {exc!r}")


if __name__ == "__main__":
    unittest.main()
