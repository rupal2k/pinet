# Boot display setup (official Raspberry Pi 7" Touch Display, v1)

The panel is mounted upside down, so everything is rotated 180°: the PINET
boot splash, the console, the desktop and touch.

`/boot/firmware/config.txt`, under `[all]` (with `display_auto_detect=0`):

    dtoverlay=vc4-kms-dsi-7inch,invx,invy

`/boot/firmware/cmdline.txt`, appended to the single line:

    video=DSI-1:800x480@60,panel_orientation=upside_down

`panel_orientation` sets the DRM connector property that fbcon and plymouth
read. The desktop gets `transform 180` on DSI-1 in `~/.config/kanshi/config`.
`invx,invy` flip the FT5406 touch so it matches the rotated desktop (labwc
maps it to DSI-1 in `config/labwc/rc.xml`).
