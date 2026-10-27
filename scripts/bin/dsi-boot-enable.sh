#!/bin/bash
# Boot-time DSI enable, run as root by dsi-backlight-enable.service (already
# ordered after lightdm + wayvnc). Keeps the panel dark until the e-ink
# dashboard is live, then wakes it and restarts the idle timer.
set -u

# "Live" = the dashboard's main loop has logged its first carousel phase this
# boot (the first render starts right after), plus time for the full refresh.
# Capped so a broken e-ink service can't keep the DSI dark forever.
EINK_WAIT_CAP=240
waited=0
until journalctl -b 0 -u pi-eink-dashboard.service --no-pager -q | grep -q "Carousel phase="; do
    if [ "$waited" -ge "$EINK_WAIT_CAP" ]; then
        echo "e-ink not live after ${EINK_WAIT_CAP}s, enabling DSI anyway" >&2
        break
    fi
    sleep 2
    waited=$((waited + 2))
done
sleep 8

touch /run/dsi-boot-ready

USER_ENV=(XDG_RUNTIME_DIR=/run/user/1000 WAYLAND_DISPLAY=wayland-0)
runuser -u rupal -- env "${USER_ENV[@]}" /usr/local/bin/dsi-wake.sh \
    || /usr/local/bin/dsi-backlight.sh on

# swayidle's 90s timer started whenever its service did; restart it so the
# panel sleeps 90s after coming on, not at some arbitrary earlier point.
runuser -u rupal -- env "${USER_ENV[@]}" systemctl --user restart dsi-idle-sleep.service || true
