---
tags: [project, raspberry-pi, e-ink, module]
---

# Test / preview scripts (`src/`)

None of these touch the e-ink hardware (`main()` in [[dashboard.py]] only
imports the Waveshare GPIO package inside itself for exactly this reason) —
all use a `FakeEPD` stand-in (`width=122, height=250`, matching the real
panel's dimensions) and save PNGs instead of calling `epd.display()`.

## `preview_render.py` — full live-data render

Loads real config/location/weather/network/system-stats and renders both
screens:
- `render()` in light **and** dark mode → `preview_light.png`,
  `preview_dark.png`.
- `render_qr_screen()` with **fake** placeholder credentials
  (`"fake-placeholder-pw"` — the real password is only ever read by the
  live systemd service, never by this script) for a short SSID and a
  worst-case 32-character WPA-max-length SSID, each in light/dark →
  `preview_qr_short_{light,dark}.png`,
  `preview_qr_longest_possible_ssid_32chars32_{light,dark}.png`.
- Also prints (but doesn't render) whether real Wi-Fi credentials were
  found, for a quick sanity check.

This is the main "does it still look right" tool after any change to
[[dashboard.py]] or [[icons.py]] — run it, `scp` back the PNGs, eyeball them.

## `offline_test.py` — fallback-state rendering without disconnecting anything

Renders the states that are awkward to trigger for real without actually
breaking your network:
- `render()` with a synthetic `{"ip": None, "is_wifi": False}` →
  `preview_no_network.png` (fully offline weather/network tiles).
- `render_qr_screen()` with no SSID/password and that same offline `net` →
  `preview_qr_no_wifi.png`.
- `render_qr_screen()` with no SSID/password but a synthetic wired `net`
  (`{"ip": "192.168.29.166", "is_wifi": False}`) → `preview_qr_wired.png`
  — added alongside the Ethernet-QR-screen fix (see
  [[fixes session log]]) to cover that case without needing a cable handy.

## `icon_gallery.py` — every icon in one labeled grid

Renders `calendar, clock, cpu_chip, ram_stick, wifi, wired, offline, sun,
cloud, rain, snow, fog, thunder` each in its own labeled cell →
`icon_gallery.png`. The fastest way to QA an [[icons.py]] change before
bothering with a full dashboard render.

## `wave_test.py` — standalone `seigaiha` watermark test

Renders just the decorative wave pattern (`icons.seigaiha`) at header scale
→ `wave_test.png`. Unrelated to the icon restyle (`seigaiha` is decorative,
out of that scope — see [[icons.py]]).

## `test_render.py` — ⚠️ broken, not runnable

Truncated mid-statement (e.g. `dashboard.get_locat`, `epd.getbuffer` never
closed) — looks like a debug script that was cut off and never fixed.
Not referenced by anything. `preview_render.py` covers the same ground and
actually works; treat this one as dead code.


## `pi-diagnostic` -- whole-device health/QA (2026-09-17)

`/usr/local/bin/pi-diagnostic [all|eink|network|dsi]` (default `all`). Not a
`src/` preview -- a system diagnostic that drives the real services. **eink**
(read-only): service active + NRestarts=0, carousel liveness from
`Carousel phase=` journal lines, the `epd.sleep()`-exactly-once-in-code
invariant, `displayPartial` present, no tracebacks. **network** (read-only):
uplink/route/internet/DNS, PINET on-demand state (INFO, not a failure),
nftables, raspotify + the `--onevent` hook. **dsi** (invasive, self-restoring):
the former `dsi-qa-check` -- opaque lock blocks the desktop (grim corner
sampling), no-flash wake x3, re-wake x2, close-album->lock x2, photos,
single-instance, unlock via injected `uinput` keys. First combined run
**48 PASS / 0 WARN / 0 FAIL**. Replaces the standalone `dsi-qa-check`.
