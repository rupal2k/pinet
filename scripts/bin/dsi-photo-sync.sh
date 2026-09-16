#!/bin/bash
# Run every 30s by dsi-photo-sync.timer: bring the slideshow cache up to date
# and, if it changed, reload a running slideshow (a closed one stays closed).
# Repeats until the folder stops changing so a copy in progress is picked up
# once it finishes. (A systemd .path unit on the folder never fired for new
# files here, hence the timer.)
set -uo pipefail
SRC="/mnt/pinet-media/slideshow"
CACHE="/mnt/pinet-media/slideshow-cache"

snapshot() { find "$1" -maxdepth 1 -type f -printf '%f %s %T@\n' 2>/dev/null | sort | md5sum; }

cache_before=$(snapshot "$CACHE")
while :; do
    src_before=$(snapshot "$SRC")
    /usr/local/bin/dsi-photo-normalize.sh
    sleep 3
    [ "$(snapshot "$SRC")" = "$src_before" ] && break
done

if [ "$(snapshot "$CACHE")" != "$cache_before" ] \
        && systemctl --user is-active --quiet dsi-photo-frame.service; then
    systemctl --user restart dsi-photo-frame.service
fi
