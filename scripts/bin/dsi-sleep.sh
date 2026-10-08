#!/bin/bash
# Put the DSI screen to sleep by blanking the BACKLIGHT only. The DSI output
# (and with it the ft5x06 touch controller) stays powered, so double-tap-to-
# wake keeps registering real touches -- disabling the output (wlopm --off)
# gated the touch panel, which left physical double-tap-to-wake dead after the
# screen went off (software-injected taps still worked, a real finger did not).
set -euo pipefail
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
export WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-wayland-0}"

# Photo frame stays lit while the album is showing (unchanged), and so does
# the HDMI monitor (its flag): don't sleep, just re-arm the idle timer to
# re-check next window.
if systemctl --user is-active --quiet dsi-photo-frame.service \
   || [ -e "$XDG_RUNTIME_DIR/monitor-mode" ]; then
    systemctl --user try-restart dsi-idle-sleep.service >/dev/null 2>&1 || true
    exit 0
fi

sudo /usr/local/bin/dsi-backlight.sh off
