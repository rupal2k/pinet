#!/bin/bash
# On-demand fullscreen kiosk with the layer-shell close button.
# Usage: [DSI_CLOSE_CORNER=left] [DSI_KIOSK_ENGINE=qtwebengine|cog]
#        [DSI_KIOSK_TITLE="KIOSK MODE ON"] [DSI_KIOSK_LABEL=<Name>]
#        [DSI_KIOSK_SHED=no] dsi-kiosk.sh <name> <url>
# TITLE/LABEL are what the e-ink dashboard shows while the kiosk is open.
# DSI_KIOSK_SHED=no skips the kiosk flag entirely (no power shedding, no e-ink
# kiosk screen) -- for local pages that need PINET running, i.e. the portal.
#
# Writing the kiosk flag makes pi-power-manager shed power-hungry services
# (PINET, VNC, Bluetooth, slideshow, idle-sleep...) and the e-ink dashboard
# show "KIOSK MODE ON". The browser only starts once shedding is done, so the
# two loads never overlap; removing the flag on exit makes the manager bring
# everything back one at a time.
#
# Engines (full chromium and Firefox both browned this power-marginal Pi 3B
# out, so neither is used here):
# - qtwebengine (default): dsi-webkiosk.py, a bare Chromium-engine window.
#   Needed for sites like Ezykam that misbehave in WebKit. GPU off: this Pi's
#   GPU can't do Chromium's GPU path.
# - cog: WPE WebKit, lightest; fine for simple pages (the camera stream).
#   LIBGL_ALWAYS_SOFTWARE=1 is required -- with the VC4 driver cog aborts on
#   its first frame ("on_export_wl_egl_image: assertion failed").
# Fullscreen covers the taskbar; the close button stays on top. taskset/nice
# are a cheap guard against all-core load spikes.
set -euo pipefail

NAME="$1"
URL="$2"
ENGINE="${DSI_KIOSK_ENGINE:-qtwebengine}"
DATA_DIR="$HOME/.local/share/kiosk-$NAME"
FLAG="/run/user/$(id -u)/kiosk-mode"
MODE=/run/pi-power-manager/mode
mkdir -p "$DATA_DIR"

browser_pid=""
button_pid=""
owns_flag=no
cleanup() {
    [ -n "$button_pid" ] && kill "$button_pid" 2>/dev/null || true
    [ -n "$browser_pid" ] && kill "$browser_pid" 2>/dev/null || true
    # Only remove a flag we wrote -- never one of a real kiosk still open.
    [ "$owns_flag" = yes ] && rm -f "$FLAG" || true
}
trap cleanup EXIT

if [ "${DSI_KIOSK_SHED:-yes}" != no ]; then
    printf '%s\n%s\n' "${DSI_KIOSK_TITLE:-KIOSK MODE ON}" "${DSI_KIOSK_LABEL:-${NAME^}}" > "$FLAG"
    owns_flag=yes
    for _ in $(seq 1 60); do
        [ "$(cat "$MODE" 2>/dev/null)" = kiosk ] && break
        sleep 0.5
    done
fi
/usr/local/bin/dsi-wake.sh

if [ "$ENGINE" = cog ]; then
    COG_PLATFORM_WL_VIEW_FULLSCREEN=1 LIBGL_ALWAYS_SOFTWARE=1 taskset -c 0,1 nice -n 10 \
        cog --platform=wl \
        --cookie-store=always --cookie-jar="sqlite:$DATA_DIR/cookies.db" \
        "$URL" &
else
    QT_QPA_PLATFORM=wayland \
    QTWEBENGINE_CHROMIUM_FLAGS="--disable-gpu --disable-gpu-compositing --renderer-process-limit=1 --disable-dev-shm-usage" \
        taskset -c 0,1 nice -n 10 python3 /usr/local/bin/dsi-webkiosk.py "$NAME" "$URL" &
fi
browser_pid=$!

python3 /usr/local/bin/dsi-close-button.py kill "$browser_pid" &
button_pid=$!

wait "$browser_pid" || true
