#!/bin/bash
# Camera desktop shortcut: start the localhost-only camera stream, show it in
# the cog kiosk with NATIVE Photo/Record overlay buttons, and stop everything
# when the kiosk closes.
set -euo pipefail

python3 /usr/local/bin/dsi-cam-server.py &
cam_pid=$!
controls_pid=""
cleanup() {
    [ -n "$controls_pid" ] && kill "$controls_pid" 2>/dev/null || true
    kill "$cam_pid" 2>/dev/null || true
    wait 2>/dev/null || true
}
trap cleanup EXIT

for _ in $(seq 1 30); do
    curl -s -o /dev/null http://127.0.0.1:8081/ && break
    kill -0 "$cam_pid" 2>/dev/null || { echo "camera server failed to start" >&2; exit 1; }
    sleep 0.5
done

# Native layer-shell Photo/Record buttons: cog (WPE) does not deliver taps to
# web content, so in-page buttons never fire -- these overlay buttons do.
python3 /usr/local/bin/dsi-cam-controls.py &
controls_pid=$!

# cog: the stream page is a single <img>, and it's the lightest engine
# (Chromium/QtWebEngine browns this Pi out).
DSI_KIOSK_ENGINE=cog DSI_KIOSK_TITLE="CAMERA MODE ON" DSI_KIOSK_LABEL="Live view" \
    /usr/local/bin/dsi-kiosk.sh camera http://127.0.0.1:8081/
