---
tags: [project, raspberry-pi, e-ink, module]
---

# `config/config.ini`

Read by `load_config()` in [[dashboard.py]] via `configparser`; every key has
a code-level fallback so a missing file/section/key never crashes the
service, it just uses defaults.

```ini
[dashboard]
latitude =
longitude =
refresh_minutes = 3
carousel_minutes = 3
network_poll_seconds = 5
dark_mode_start_hour = 20
dark_mode_end_hour = 6
```

| Key | Default (code fallback) | Meaning |
|---|---|---|
| `latitude` / `longitude` | blank → IP geolocation | Weather location. Blank = auto-detect via `ip-api.com` (one extra outbound call per location lookup, less precise); set explicitly for accuracy/privacy. Currently blank, so it re-resolves on every network change (see [[fixes session log]] fix #10) — normally **Guwahati** via IP geolocation, which is why the system [[fixes session log|timezone was set to Asia/Kolkata]], to match. |
| `refresh_minutes` | 5 | How often the *currently showing* screen redraws. Set to `3` to match `carousel_minutes` (see below). |
| `carousel_minutes` | 5 | How long each of the **three** screens (status / QR / bug art, see [[fixes session log]] fix #10) stays up before flipping. Set to `3` per explicit request — 3 min status, 3 min QR, 3 min bug art, 9 min total cycle. |
| `network_poll_seconds` | 5 | While waiting between refreshes, how often the network fingerprint (`get_network_fingerprint()`) is rechecked — a change (cable plug/unplug, Wi-Fi switch) triggers an immediate redraw instead of waiting out the full `refresh_minutes`. This is what makes the Ethernet-plug-in fix visible within ~5s instead of up to a minute. |
| `dark_mode_start_hour` / `dark_mode_end_hour` | 20 / 6 | 24h local-time window (wraps past midnight) during which both screens render inverted (white-on-black). `start == end` disables dark mode entirely. |

Edit and restart to apply:
```bash
sudo systemctl restart pi-eink-dashboard
```
