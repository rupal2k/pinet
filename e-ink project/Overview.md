---
tags: [project, raspberry-pi, e-ink, active]
---

# Pi e-Ink Status Dashboard

A Raspberry Pi drives a Waveshare 2.13" e-Paper HAT (V4) as an always-on status
panel: date/time, CPU/RAM/temperature, weather, and network status, cycling
every `carousel_minutes` through four screens — the status screen, a Wi-Fi
QR-login screen, a DOOM-logo screen doubling as a power/disk health glance
(started as a bug-mascot screen in fix #10, replaced with the current
version across fix #11 and the 2026-09-06 evening session, fix #12), and a
PINET hotspot join screen (restored to the rotation in fix #11 after being
temporarily dropped).

> [!info] This Pi now does far more than the e-ink dashboard.
> It has grown into a five-subsystem appliance (status panel, PINET offline
> network + portal, DSI touchscreen photo-frame/kiosks, Kali Wi-Fi toolbox,
> Bluetooth music). For the whole-device description and everything it's
> capable of, start at **[[Device Overview]]**.

## Where it lives

| Fact | Value |
|---|---|
| Host | `raspberrypi`, user `rupal` |
| Hardware | Raspberry Pi 3 Model B Rev 1.2 (Wi-Fi radio is 2.4GHz-only — no 5GHz) |
| OS | Debian 13 "trixie", kernel `6.18.34+rpt-rpi-v8` (64-bit) |
| Reachable at | `192.168.29.125` (Wi-Fi, via the TP-Link `wlan1` adapter, SSID `SPECTRE5G`) or `192.168.29.166` (Ethernet) on the home network — either works over SSH/SFTP. `wlan0` (onboard chip) is no longer a client interface at all — it's dedicated to hosting the `PINET` hotspot, see [[pinet-captive-portal]]. Also seen on a phone-hotspot Wi-Fi profile (`Rupal's Android phone`) when away from home; IP varies by network. Treat all IPs as DHCP and re-check if unreachable — this table goes stale faster than it gets updated; the assistant's own auto-memory notes are usually the freshest source if this looks wrong. |
| Project path (on the Pi) | `~/pi-eink-dashboard/` |
| Panel | Waveshare 2.13inch e-Paper HAT (V4), 250×122px, 1-bit (black/white) |
| Service | `pi-eink-dashboard.service` (systemd, auto-starts on boot) — see [[systemd service]] |
| Timezone | `Asia/Kolkata` (matches the configured weather location, Guwahati) |

## Architecture

```
config/config.ini  ──┐
                      ├─► src/dashboard.py (main loop) ─► icons.py (drawing primitives)
scripts/install.sh ───┘         │
                                 ├─ render()               → status screen (CPU/RAM/weather/network)
                                 ├─ render_qr_screen()      → Wi-Fi QR / "connected via Ethernet" screen
                                 ├─ render_image_screen()   → DOOM logo + power/disk health (header+footer)
                                 └─ render_hotspot_screen() → PINET join QR + board password
```

`dashboard.py` runs one infinite loop (`main()`) under systemd: every
`carousel_minutes` it cycles through the four screens above (phase `% 4`),
and within each screen's dwell time it polls the network every
`network_poll_seconds` so a cable plug/unplug or Wi-Fi switch updates the
display early instead of waiting out the full `refresh_minutes` interval.
Font is Roboto project-wide as of 2026-09-06 evening (was DejaVu Sans).

## Module notes

- [[dashboard.py]] — the main script: config/location/weather, system stats,
  network detection, screen rendering, main loop.
- [[icons.py]] — every icon drawn on the panel, hand-built from PIL
  primitives (no image assets).
- [[config.ini]] — every setting, what it controls, and its default.
- [[systemd service]] — the background service definition and how it's
  installed.
- `src/shutdown_splash.py` + `systemd/pi-eink-shutdown-splash.service`
  (added 2026-09-06 evening) — shows the DOOM logo, forced dark mode, on
  the panel during shutdown/reboot and leaves it there (e-ink holds its
  last image with no power). `RemainAfterExit=yes` oneshot unit whose
  `ExecStop` does the work, ordered `Before=pi-eink-dashboard.service`
  so it only touches the panel after the live dashboard has released it.
  See [[fixes session log]] for how this was tested without a real reboot.
- [[deploy and install scripts]] — `scripts/install.sh` (the real installer)
  vs. two **stale** bundler scripts that must not be run.
- [[test and preview scripts]] — the non-hardware scripts used to render and
  QA screens/icons without touching the e-ink panel.
- [[fixes session log]] — chronological record of every bug found and fixed
  in this project so far, with root cause and verification for each.
- [[power and undervoltage]] — ongoing investigation into a persistent
  under-voltage/throttling condition (2026-09-06), four chargers ruled
  out, no software-readable current draw on this board.
- [[pinet-captive-portal]] — PINET's web-facing side, as of the
  2026-09-06 evening rebuild split into two independent services:
  `pinet-portal` (password-gated internet-bridge toggle only, port 8090)
  and `pinet-board` (anonymous chat + up to 1GB file sharing, port 80,
  built by a separate concurrent session). Dedicated portal password, not
  root's; narrowly-scoped sudoers rule; a real `CapabilityBoundingSet`
  sudo bug found and fixed in QA; both UIs self-host Roboto.
- [[pinet-board]] — the PINET portal as it runs today (message board, file
  sharing, guest/admin roles, phone-upload note).
- [[dsi photo frame]] — the 7" touchscreen: slideshow, sleep/double-tap wake,
  camera/Ezykam/portal kiosks, pi-power-manager, install guard, theme, boot
  splash (added 2026-09-15).
- [[linkedin post]] — the LinkedIn post written about the project.

## Adding a DSI display alongside the e-ink panel (DONE 2026-09-14/15)

**Built** -- the official 7" touchscreen is now a photo frame with on-demand
camera/web kiosks and a power manager. Everything about the live system is in
[[dsi photo frame]]; the planning notes below are kept for history.

Asked whether a DSI display (e.g. the official touchscreen) could be added
to the same Pi without conflicting with the e-ink setup. Should work fine.

**Confirmed use case (2026-09-06 evening)**: a digital photo frame — a
second, separate display running its own photo-slideshow app, coexisting
with this e-ink dashboard rather than replacing it. This is a new,
separate project when it starts, not a change to `dashboard.py`. No
panel has been chosen yet.

- **No interface conflict**: the Waveshare HAT talks over SPI + a few GPIO
  pins on the 40-pin header; DSI uses the Pi's dedicated DSI ribbon
  connector — a completely separate physical port and kernel driver path.
  Enabling both in `config.txt` (`dtparam=spi=on` plus a DSI overlay) is
  independent, no known conflict.
- **No software conflict either**: [[dashboard.py]] never touches the Pi's
  framebuffer/desktop output — it draws with PIL and pushes bytes straight
  over SPI to the e-ink panel. A DSI screen showing a normal desktop (or
  anything else) would be fully independent; the dashboard script wouldn't
  need any changes to coexist with it.
- **Check before wiring up**: physical clearance — confirm the e-Paper HAT's
  PCB doesn't overlap the DSI connector's position on this specific Pi 3B
  (the HAT sits on the GPIO header; the DSI port is a separate edge
  connector, so this is usually fine but wasn't physically verified).
- **Power (researched 2026-09-06, was a concern, checked with real numbers)**:
  not actually tight. Official Pi 3B recommendation is a 5V/2.5A supply
  (~1.3A for the board, ~1.2A reserved for USB). The official 7" DSI
  touchscreen draws ~450–550mA (mostly backlight) — measured combined with a
  Pi 3B: ~750mA idle with Wi-Fi connected, with startup bursts over 1100mA.
  The e-Paper HAT is a non-issue: e-paper displays in this family sleep at
  2–5 μA and only spike (tens of mA) for the ~1–2s refresh pulse. Worst case
  (backlight + Wi-Fi + a refresh landing at the same instant) stays
  comfortably under 1.2A against the 2.5A rating — roughly 2x headroom. The
  real-world risk with a Pi 3B "under-voltage" warning is almost always
  cable/supply **quality** (a thin/long micro-USB cable causing voltage drop
  under load), not the rated amperage — use the genuine official supply (or
  equivalent) with a short, good-gauge cable. Reassess if adding other USB
  peripherals later (they share the same 1.2A USB budget the touchscreen
  doesn't touch, since it's normally GPIO/5V-rail powered, not USB).
  Sources: [Raspberry Pi 3 Power Supply - 2.5A](https://www.canakit.com/raspberry-pi-adapter-power-supply-2-5a.html),
  [Powering the Raspberry Pi 3 - DigiKey](https://forum.digikey.com/t/powering-the-raspberry-pi-3/254),
  [Official RPI 7'' touchscreen power requirements](https://community.element14.com/products/raspberry-pi/f/forum/11117/official-rpi-7-touch-screen-power-requirements),
  [1.54inch e-Paper Datasheet - Waveshare](https://www.waveshare.com/w/upload/7/77/1.54inch_e-Paper_Datasheet.pdf)
  (same driver-IC family/power profile as the 2.13inch HAT this project uses).

## Housekeeping (resolved 2026-09-06)

The stale nested duplicate checkout (`~/pi-eink-dashboard/pi-eink-dashboard/`)
and the broken `src/test_render.py` were both already gone from the Pi by the
time this was checked (no longer present — likely cleaned up manually between
sessions). `config.ini`'s `refresh_minutes`/`carousel_minutes` were raised
from the testing value `1` back to the code default `5` — see [[config.ini]].

## 2026-09-12 session (pointer)

Later work not part of the original 2026-09-06 build. Recorded across the topic
notes; start at [[fixes session log]] (2026-09-12 session) for the full log:
- **Persistent journald** finally fixed (RPi vendor drop-in was forcing
  volatile) -- see [[systemd service]]; this also let the first real
  under-voltage brownout reset be captured, see [[power and undervoltage]].
- **PINET board**: in-browser file viewing (`/view`) + responsive tabbed UI --
  see [[pinet-board]].
- **Power/boot optimization**: disabled unused services + staggered boot
  (cloud-init/wait-online off, lightdm/wayvnc delayed) to reduce the boot
  brownout spike, while keeping the GUI -- see [[power and undervoltage]] and
  [[systemd service]]. Lesson learned: don't force reboots on this Pi.

## 2026-09-15 session (pointer)

Start at [[fixes session log]] entries 21-28 and the new [[dsi photo frame]] note:
- **DSI slideshow**: photos fitted to the screen (never cropped) over a blurred
  background; small-window bug fixed; screen now re-sleeps after a double-tap wake.
- **Cleanup**: temp files, old backups, `~/e-Paper`, Firefox, Docker and 19
  orphaned packages removed -- SD card 73% → 43%. No desktop browser remains;
  the PINET Portal shortcut opens a Qt web window.
- **QA audit** of every function, live: passes; fixes for Bluetooth shedding
  and a dead taskbar launcher; **firewall** now blocks SSH/VNC from PINET guests.
- **PINET portal**: note for phone uploads (use a browser, mobile data off)
  -- see [[pinet-board]].
- **LinkedIn post** about the project: [[linkedin post]].
- Currently on home Wi-Fi `SPECTRE24` via wlan1 (it moves between SPECTRE24/5G).
