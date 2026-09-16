#!/bin/bash
# DSI 7" touchscreen backlight control (official Pi touchscreen, i2c attiny backlight controller).
# Usage: dsi-backlight.sh on [brightness 1-255]  |  dsi-backlight.sh off
# Default "on" brightness comes from BRIGHTNESS in /etc/default/dsi-screen.
set -euo pipefail

BRIGHTNESS=1
[ -r /etc/default/dsi-screen ] && . /etc/default/dsi-screen

BL=$(ls -d /sys/class/backlight/*/ 2>/dev/null | head -1)
if [ -z "$BL" ]; then
    echo "dsi-backlight.sh: no backlight device found under /sys/class/backlight" >&2
    exit 1
fi

case "${1:-}" in
    on)
        BRIGHTNESS="${2:-$BRIGHTNESS}"
        echo 0 > "${BL}bl_power"
        echo "$BRIGHTNESS" > "${BL}brightness"
        ;;
    off)
        echo 1 > "${BL}bl_power"
        echo 0 > "${BL}brightness"
        ;;
    *)
        echo "usage: dsi-backlight.sh on [brightness] | off" >&2
        exit 1
        ;;
esac
