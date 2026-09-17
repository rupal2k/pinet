---
tags: [project, raspberry-pi, e-ink, module]
---

# `src/dashboard.py`

The main script. Runs continuously under [[systemd service]]; imports
[[icons.py]] for all drawing primitives. Reads settings from [[config.ini]].

**Font**: `FONT_REGULAR_PATH`/`FONT_BOLD_PATH`/`FONT_SMALL` use Roboto
(`/usr/share/fonts/truetype/roboto/unhinted/RobotoTTF/`, via
`apt install fonts-roboto`) as of 2026-09-06 evening — was DejaVu Sans.
Low-risk swap since nearly every text draw goes through `fit_text()`
(dynamic shrink-to-fit) rather than assuming exact glyph metrics. Matched
by the same font, self-hosted, on both PINET web portals — see
[[pinet-captive-portal]].

## Config / location / weather

- **`load_config()`** — reads `config/config.ini` via `configparser`, returns
  the `[dashboard]` section (empty dict-like if missing, so every setting
  below has a code-level fallback too).
- **`is_dark_mode(cfg)`** — true when the current local hour falls inside
  `dark_mode_start_hour`..`dark_mode_end_hour` (wraps past midnight, e.g.
  20→6 means 8PM–6AM). Both screens invert to white-on-black when true.
- **`reverse_geocode(lat, lon)`** — lat/lon → city name via
  bigdatacloud.net's free reverse-geocode API (no key). Used only to label
  the weather tile (e.g. "GUWAHATI").
- **`get_location(cfg)`** — if `latitude`/`longitude` are set in config, uses
  those (and reverse-geocodes a name). Otherwise falls back to IP-based
  geolocation via `ip-api.com`. Returns `(lat, lon, name)`, all `None` on
  total failure. In IP-geolocation mode this resolves the *requesting* public
  IP's location -- so `main()` now re-calls it whenever the network fingerprint
  changes (see [[fixes session log]] fix #10), since switching networks (e.g.
  home Wi-Fi to a phone hotspot) can change the egress point and therefore the
  resolved city. Skipped when `latitude`/`longitude` are explicitly configured
  (a fixed location never needs re-resolving).
- **`get_weather(lat, lon)`** — current temp/humidity/WMO weather code from
  Open-Meteo (no key). Returns `None` on any failure (offline, API down,
  etc.) — the caller shows a "!" placeholder tile in that case.

## System stats

- **`get_system_stats()`** — CPU % (`psutil.cpu_percent`), RAM % and GB used,
  and CPU temp (`psutil.sensors_temperatures()["cpu_thermal"]`, `None` if
  unavailable, e.g. off-Pi testing).
- **`get_power_status()`** (added 2026-09-06, see [[power and undervoltage]])
  — core voltage (`vcgencmd measure_volts core`) and *current* (not
  historical) under-voltage/throttle flags from `vcgencmd get_throttled`,
  reading only bits 0/2 so a recovered Pi doesn't look permanently broken
  from the sticky history bits. All `None` off-Pi. Feeds the DOOM-logo
  screen's header row, see `render_image_screen` below.
- **`get_disk_usage(path="/")`** (added 2026-09-06 evening) —
  `psutil.disk_usage(path)` converted to GB, returns
  `(free_gb, used_gb, total_gb)`, all `None` on failure. Feeds the same
  screen's footer row.

## Network detection

This is the part that had the most bugs — see [[fixes session log]] for the
full story of each one.

- **`get_ip_address()`** — opens a UDP socket toward `8.8.8.8:80` (no packet
  actually sent) purely to read back `getsockname()`, i.e. the local IP the
  kernel would use for real outbound traffic. Returns `None` if there's no
  route at all (fully offline).
- **`get_wifi_ssid()`** — `iwgetid -r`. Returns the SSID `wlan0` is
  *associated* to, **or `None` if wlan0 isn't associated to anything** —
  this does **not** mean Wi-Fi is the active connection, just that the
  radio has joined a network. This distinction is the root cause fixed
  below.
- **`get_active_interface(ip)`** — the actual fix: matches `ip` (from
  `get_ip_address()`, i.e. the real outbound address) against
  `psutil.net_if_addrs()` to find which interface **owns** that address.
  This is the interface really carrying traffic, regardless of what else is
  associated in the background.
- **`_is_wifi(iface, ssid)`** — the single source of truth for "is this
  Wi-Fi": if an active interface was resolved, checks its name
  (`wl*`/`ww*` = Wi-Fi); only falls back to the raw SSID-association check
  if the interface couldn't be resolved at all.
- **`get_network_status()`** — `{"ip": ..., "is_wifi": ...}` combining the
  above. Drives the status screen's NETWORK tile.
- **`get_network_fingerprint()`** — cheap `(ip, is_wifi)` tuple, recomputed
  every `network_poll_seconds` inside the main loop's wait window to detect
  a network change (cable plugged/unplugged, Wi-Fi switched) and trigger an
  early redraw instead of waiting the full `refresh_minutes`.
- **`get_wifi_credentials()`** — `(ssid, password)` for the QR screen, or
  `(None, None)` if not actually on Wi-Fi (checked via `_is_wifi`, same fix
  as above — previously this kept returning Wi-Fi credentials/QR even while
  connected over Ethernet, as long as `wlan0` stayed associated in the
  background). Password is read via
  `sudo -n nmcli -s -g 802-11-wireless-security.psk connection show <ssid>`
  — requires passwordless sudo for that exact `nmcli` invocation (see the
  sudoers note the QR screen itself shows if this fails).

## Text layout

- **`_text_width(draw, text, font)`** — helper, `textbbox` width.
- **`fit_text(draw, text, font_path, max_size, min_size, max_width)`** —
  shrinks font size step-by-step until the text fits `max_width`; only as a
  last resort truncates with `..`. Used for every piece of text on the
  panel (stat-box labels/values, the header clock, the QR SSID header) so
  nothing silently clips off the edge of the 250px-wide canvas.

## Rendering

Redesigned (this session) from a uniform 2×2 grid of four identically-sized
boxes into a deliberate two-tier hierarchy: CPU/RAM are diagnostic figures
demoted to a compact single-line strip, while weather and network — the two
things actually worth a glance from across the room — get large "hero"
boxes with much bigger value text. See [[fixes session log]] for the
reasoning (a uniform card grid regardless of information priority is a
generic pattern worth avoiding, not a deliberate choice).

- **`draw_mini_stat(draw, x, y, w, h, icon_fn, text)`** — the compact,
  low-emphasis tile: icon + one line of text, vertically centered. Used
  only for CPU and RAM, side by side in a single thin bordered strip.
- **`draw_stat_box(draw, x, y, w, h, label, value, secondary, icon_fn)`** —
  the hero tile: bordered rectangle, icon top-left, quiet label, then a
  large bold value (`fit_text` up to 26pt) and secondary text pinned near
  the bottom. Used only for weather and network, each getting roughly
  4× the vertical space CPU/RAM get.
- **`render(epd, cpu, ram_pct, ram_used_gb, cpu_temp, weather, net, location_name, dark_mode)`**
  — the main status screen. Canvas is drawn *rotated* (`epd.height ×
  epd.width`, i.e. landscape) because the panel is physically portrait —
  standard Waveshare convention, `epd.getbuffer()` handles the rotation
  back at display time. Layout, top to bottom: a header with the date
  left-aligned and the 12-hour clock right-aligned (own font-size search,
  13–18pt, picks the largest size where both strings plus a 10px gap fit
  the panel width) — replaced an earlier single centered string with a
  manually-tuned triple-space gap, which wasted the panel's edges instead of
  using the full width; a thin CPU+RAM strip (`draw_mini_stat` ×2,
  separated by a vertical divider); then weather/network as two large hero
  boxes (`draw_stat_box` ×2) filling the rest of the panel. The weather box
  falls back to a "`--`" value (deliberately *not* another "!" — the
  exclamation icon already carries that meaning; pairing it with a literal
  "!" as the giant hero value read as two stacked exclamation marks once
  blown up to hero size) with "No network"/"Unavailable" as the reason,
  when `get_weather()` returned `None`. Temperature values (weather and CPU)
  now render with a proper `°` degree sign instead of a bare "C". The
  weather icon is night-aware: `weather_icon(..., night=dark_mode)` swaps
  the sun for a crescent [[icons.py|moon]] on clear/mainly-clear codes while
  `dark_mode` is active, since a sun icon at 2 AM read as wrong regardless of
  the actual weather. The network box shows WiFi/Wired/Offline with the
  matching icon from [[icons.py]]. `dark_mode` inverts the whole image at
  the end (`ImageOps.invert`).
- **`render_qr_screen(epd, ssid, password, net, dark_mode)`** — the second
  carousel screen. Four cases, in priority order:
  1. `ssid and password` → QR code encoding `WIFI:T:WPA;S:...;P:...;;` (scans
     directly as a Wi-Fi join code) plus a header showing the SSID
     (`fit_text` down to 9pt so even a full 32-char WPA SSID fits).
  2. `ssid and not password` → "Connected to: SSID" + "Password unavailable
     (check sudoers setup)" — the `sudo nmcli` lookup failed.
  3. `not ssid and net["ip"]` → **"Connected via Ethernet" + the IP** — the
     fix for the Ethernet case: previously this branch didn't exist and the
     screen showed the generic "no Wi-Fi" message even while wired.
  4. Otherwise → "No network connection (offline)".
- **`render_image_screen(epd, image_path, dark_mode, voltage, under_voltage,
  throttled, disk_free_gb, disk_used_gb, disk_total_gb)`** — the third
  carousel screen. Started life as `render_ascii_art_screen` (a pixel-art
  bug mascot, fix #10) but was replaced with an arbitrary-image renderer
  showing `DOOM_LOGO_PATH` (a grunge-texture PNG downscaled/letterboxed,
  dithered to 1-bit so grayscale survives as stipple rather than a hard
  threshold). As of the 2026-09-06 evening session it also doubles as a
  hardware-health glance: a **header row above the logo** shows
  voltage/under-voltage/throttle status from `get_power_status()` (with
  `icons.exclamation` when there's a problem), and a **separate footer row
  below the logo** shows `"{used}/{total}GB used · {free}GB free"` from
  `get_disk_usage()`, run through `fit_text()` since that string has less
  width margin than most. Deliberately two rows, not one shared line (tried
  sharing first, changed on feedback — one line made one reading feel
  subordinate to the other), and **no rule lines** anywhere on this screen
  (whitespace-only separation on both sides of the logo — also an explicit,
  repeated instruction). The logo's own image area size is unaffected by
  any of this; only the header/footer strips around it changed. See
  [[fixes session log]] fix #12 for the full history and every
  intermediate layout that was tried and reverted.
- **`render_hotspot_screen(epd, hotspot, dark_mode)`** — the fourth
  carousel screen (`get_hotspot_status()` → SSID, live client count via
  `iw dev wlan0 station dump`, join QR from `get_hotspot_passphrase()`
  reading `hostapd.conf` directly, and — as of the evening session's
  PINET rebuild — a `board_password` row showing the current
  `pinet-board` login in plaintext for guests, see
  [[pinet-captive-portal]]). Active-hotspot icon is `icons.antenna()`
  (added 2026-09-06 evening, replacing `icons.wifi()` — a visible mast
  reads as "broadcast antenna" rather than "phone signal bars"; the main
  status screen's own Wi-Fi-client icon in `render()` legitimately means
  Wi-Fi-as-client and was left on `icons.wifi()`).

## Main loop

- **`main()`** — imports `waveshare_epd.epd2in13_V4` *inside* the function
  (not at module scope) specifically so `render()`/`render_qr_screen()` can
  be imported and exercised off-Pi / without hardware (see
  [[test and preview scripts]]) — importing the Waveshare package claims
  GPIO pins as a side effect.
  - Reads `refresh_minutes`, `carousel_minutes`, `network_poll_seconds` from
    config; resolves location once at startup.
  - Loop: `phase = int((time.monotonic() - start_time) // (carousel_minutes*60)) % 4`
    — `0` = status screen, `1` = QR screen, `2` = DOOM-logo/power/disk
    screen (`render_image_screen`, historically named "ascii" in the log
    lines even though it's no longer ASCII art), `3` = hotspot screen
    (`render_hotspot_screen`, restored to the rotation in fix #11).
    `start_time = time.monotonic()` captured once before the loop. Renders, pushes to the panel
    (`epd.init()` → `display()` → `sleep()`, the standard low-power
    Waveshare pattern), then waits `refresh_minutes`, polling the network
    fingerprint every `network_poll_seconds` and breaking early on change.
    See [[fixes session log]] fix #9 for why this is anchored to
    `start_time`/`monotonic()` rather than raw wall-clock `time.time()`.
  - On `KeyboardInterrupt` or any exit, clears the panel to white and calls
    `epdconfig.module_exit(cleanup=True)` in `finally` so GPIO is released
    cleanly.

---

## Update 2026-09-12 -- `get_board_password()` now shows the GUEST password

Since [[pinet-board]] gained admin/guest roles (admin can delete uploads),
`get_board_password()` was changed to read
`/etc/pinet-board/guest_password_plaintext.txt` (guest tier) instead of the
admin `board_password_plaintext.txt`, with the admin file as a fallback only if
no guest password is set. Rationale: the hotspot screen is physically visible to
anyone near the Pi, so it must not expose the delete-capable admin password.
Commit `00c5be0`. See [[fixes session log]] entry 18.

---

## Update 2026-09-12 (later) -- hotspot storage row + weather resilience

- `render_hotspot_screen` now shows a `Storage: N GB free of M GB` row for
  `/mnt/pinet-media` (PINET upload drive); `get_hotspot_status()` carries
  `storage_free_gb`/`storage_total_gb` via `get_disk_usage()`. Layout repacked
  (device count 40->34px, moved up) to fit it. Commit `6766772`. See
  [[fixes session log]] entry 19.
- Weather no longer gets stuck "Unavailable": `get_location()` is retried in the
  status phase whenever lat/lon is unresolved (fixes the boot-time
  DNS-not-ready case, worsened by disabling wait-online), and the last good
  weather is cached and reused over transient Open-Meteo failures. Commit
  `e950bf8`. See [[fixes session log]] entry 20 and [[power and undervoltage]].


**Validated across a reboot (2026-09-12)**: the weather fix (entry 20) was
confirmed on a real boot. The dashboard journal shows the exact fail-then-recover
path: `14:02:37 IP geolocation failed -> lat=None` (network not ready at boot),
then `14:04:02 Location resolved on retry: ... Guwahati` -- proving the status-
phase retry recovers weather on its own (~90s), where the old code would have
left it "Unavailable" until the next restart. Clean single boot, 0 failed units,
throttled=0x0.


---

## Update 2026-09-17 -- Spotify now-playing panel on the hotspot screen

When PINET is down (the on-demand default), `render_hotspot_screen`'s `else`
(inactive) branch now keeps the "Hotspot inactive" notice and adds a Spotify
panel: the `icons.spotify` glyph + "Spotify" + "> <output sink>", then the bold
track name + artist + `[playing]`/`[paused]`, or "Nothing playing /
raspotify (raspberrypi)" when idle, or "raspotify not running" when the service
is down. New `get_spotify_status()` reads `/run/user/1000/raspotify-nowplaying`
(written by the librespot `--onevent` hook `raspotify-nowplaying-hook` -- see
[[fixes session log]] entries 41 and 33) and returns `None` when raspotify isn't
running. Commit `58044df`. Verified by rendering every state (play / pause /
idle / off, light + dark) at real 250x122 and viewing the PNGs; the arrow glyph
is missing from Roboto (tofu) so the output line uses `>`.


---

## Update 2026-09-17 (later) -- Spotify live play-state + under-voltage debounce

- `get_spotify_status()` now takes play/idle from the live PipeWire librespot
  node (`_librespot_live_state()` via `pw-dump`, `state==running` -> playing),
  not just the `--onevent` file, so audio already playing when the hook started
  shows as Playing (a new no-title render case) instead of "Nothing playing". The
  dashboard is `User=rupal`, so pw-dump reaches the user PipeWire with
  `XDG_RUNTIME_DIR`. Device label is now "PINET" (`LIBRESPOT_NAME=PINET`).
- **Under-voltage debounce**: `main()` samples `get_power_status()` every loop
  iteration and keeps consecutive streaks; phase-2 shows LOW VOLTAGE/THROTTLED
  only after `undervoltage_min_readings` (config, default 3) consecutive active
  reads, so a one-time spike is ignored (the chronic condition still shows).
  Commit `bf368a1`. See [[power and undervoltage]] and [[fixes session log]]
  entries 42-43.

**Spotify title (2026-09-17):** the panel's track name comes from the librespot
`--onevent` hook, which resolves it from `TRACK_ID` via Spotify oEmbed (this
librespot build omits `NAME`). `render_hotspot_screen` shows the name only while
`state` is playing/paused. See [[fixes session log]] entry 45.
