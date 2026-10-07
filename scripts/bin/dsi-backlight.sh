#!/bin/bash
# DSI 7" touchscreen backlight control (official Pi touchscreen, i2c attiny backlight controller).
# Usage: dsi-backlight.sh on [brightness 1-255]  |  off  |  set <10-255> (saved)
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
    set)
        # The taskbar slider (pinet-brightness), via sudo: a new level that is
        # kept for every later wake. Asleep, the panel stays dark.
        level="${2:-}"
        case "$level" in
            ''|*[!0-9]*) echo "dsi-backlight.sh: set needs a level 10-255" >&2; exit 1 ;;
        esac
        [ "${#level}" -gt 3 ] && level=255
        level=$((10#$level))
        [ "$level" -lt 10 ] && level=10     # never fully dark by accident
        [ "$level" -gt 255 ] && level=255
        [ "$(cat "${BL}bl_power")" = 0 ] && echo "$level" > "${BL}brightness"
        if grep -q '^BRIGHTNESS=' /etc/default/dsi-screen 2>/dev/null; then
            sed -i "s/^BRIGHTNESS=.*/BRIGHTNESS=$level/" /etc/default/dsi-screen
        else
            echo "BRIGHTNESS=$level" >> /etc/default/dsi-screen
        fi
        ;;
    *)
        echo "usage: dsi-backlight.sh on [brightness] | off | set <10-255>" >&2
        exit 1
        ;;
esac
