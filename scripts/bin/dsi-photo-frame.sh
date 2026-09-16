#!/bin/bash
# ExecStart of dsi-photo-frame.service: fullscreen slideshow plus its close
# button. Both run in the service's cgroup, and the button stops the service,
# so "close" means closed until the desktop shortcut (or next boot) starts it
# again -- Restart=always doesn't fire on an explicit stop. Real fullscreen
# covers the taskbar; the layer-shell button stays on top of it (verified).
#
# Photos: /mnt/pinet-media/slideshow (PINET USB storage), fitted to the
# panel (never cropped) into slideshow-cache/. dsi-photo-sync.timer restarts
# this service when photos are added or removed.
#
# pqiv reads actions from the $ACTIONS fifo; dsi-wake.sh sends
# toggle_fullscreen(1) through it on every wake, repairing a window that came
# up small (see below). A no-op when already fullscreen.
set -euo pipefail
export GDK_BACKEND=wayland
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
export WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-wayland-0}"
CACHE="/mnt/pinet-media/slideshow-cache"
ACTIONS="$XDG_RUNTIME_DIR/dsi-photo-frame.actions"

# Best-effort fifo cleanup on stop: systemd signals the whole cgroup, which
# can kill the trap's rm too (then bash exits 143 -- the unit has
# SuccessExitStatus=143). A leftover fifo is harmless: recreated on start,
# and dsi-wake.sh only writes to it while this service is active.
trap 'rm -f "$ACTIONS"' EXIT
trap 'exit 0' TERM

/usr/local/bin/dsi-photo-normalize.sh

# Nothing to show (empty folder or drive missing): wait instead of letting
# pqiv exit and crash-loop. The sync watcher restarts us once photos arrive.
until compgen -G "$CACHE/*.jpg" > /dev/null; do
    sleep 30
    /usr/local/bin/dsi-photo-normalize.sh
done

# If pqiv maps while the output is powered off (screen asleep), it can't go
# fullscreen and stays a small window after wake. Power the output on while
# it maps, then put the screen back to sleep. Under load pqiv can take longer
# than the wait below (seen after a big apt run) -- the wake-time
# toggle_fullscreen(1) is what guarantees fullscreen.
output_was_off=no
wlopm | grep -q "DSI-1 off" && output_was_off=yes
wlopm --on DSI-1 || true

python3 /usr/local/bin/dsi-close-button.py \
    systemctl --user stop --no-block dsi-photo-frame.service &

# Held open read-write here so pqiv never sees EOF between writers.
rm -f "$ACTIONS"
mkfifo -m 600 "$ACTIONS"
exec 3<>"$ACTIONS"

pqiv --fullscreen --slideshow --slideshow-interval=300 --shuffle \
    --hide-info-box --end-of-files-action=wrap --actions-from-stdin \
    "$CACHE" <&3 &
pqiv_pid=$!

# Sleeps via `& wait` so a stop during them still runs the traps (bash
# defers traps while a foreground command runs).
if [ "$output_was_off" = yes ]; then
    sleep 4 & wait $!
    echo "toggle_fullscreen(1)" >&3
    sleep 1 & wait $!
    /usr/local/bin/dsi-sleep.sh || true
fi

wait "$pqiv_pid"
