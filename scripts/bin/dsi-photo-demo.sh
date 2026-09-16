#!/bin/bash
# "Photo Frame Demo" desktop shortcut: wake the panel and (re)start the
# slideshow service, which brings its own close button.
/usr/local/bin/dsi-wake.sh
systemctl --user restart dsi-photo-frame.service
