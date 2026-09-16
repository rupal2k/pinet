#!/bin/bash
# Put the DSI screen to sleep: blank the compositor output, then kill the backlight.
set -euo pipefail
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
export WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-wayland-0}"
/usr/bin/wlopm --off DSI-1 || true
sudo /usr/local/bin/dsi-backlight.sh off
