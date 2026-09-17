#!/bin/bash
# Wake the DSI screen: re-enable the compositor output first so a real frame
# is ready, then unblank the backlight (avoids a flash of a stale/garbage frame).
# No-op until dsi-boot-enable.sh has marked this boot ready (e-ink live), so a
# double-tap or shortcut during boot can't light the panel early.
set -euo pipefail
[ -e /run/dsi-boot-ready ] || exit 0
# Package install in progress (dsi-install-guard): stay dark. Only honoured
# while dpkg is actually running, so a failed apt run can't leave it stuck.
if [ -e /run/dsi-install-guard ] && pgrep -x dpkg > /dev/null; then exit 0; fi
# Callers like dsi-tap-wake.service can start before the desktop session
# publishes these; without them wlopm fails and the panel stays black.
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
export WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-wayland-0}"
/usr/bin/wlopm --on DSI-1 || true
# Slideshow running: make sure it's fullscreen before the backlight comes on
# (it comes up small if it mapped while the output was off). Its fifo is held
# open by dsi-photo-frame.sh. A stopped slideshow can leave a stale fifo (its
# cleanup can be killed by the stop), and writing to one blocks -- hence the
# is-active check, with timeout as the backstop.
ACTIONS="$XDG_RUNTIME_DIR/dsi-photo-frame.actions"
if [ -p "$ACTIONS" ] && systemctl --user is-active --quiet dsi-photo-frame.service; then
    timeout 1 bash -c 'echo "toggle_fullscreen(1)" > "$1"' _ "$ACTIONS" || true
    sleep 0.5
else
    sleep 0.15
fi
if [ -z "${DSI_DEFER_BACKLIGHT:-}" ]; then sudo /usr/local/bin/dsi-backlight.sh on; fi
# Re-arm idle sleep: swayidle only re-arms on compositor input, and a
# double-tap wake never reaches the compositor (the tap daemon grabs the
# touchscreen while asleep) -- without this the screen stays on until someone
# touches it again. try-restart: no-op while a kiosk has idle-sleep stopped.
systemctl --user try-restart dsi-idle-sleep.service || true
