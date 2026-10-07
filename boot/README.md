# Boot display setup (official Raspberry Pi 7" Touch Display, v1)

Everything on the DSI panel is rotated 180° to match the PINET boot splash:
the plymouth logo, the console, the login/logout greeter, the desktop and
touch.

`/boot/firmware/config.txt`, under `[all]` (with `display_auto_detect=0`):

    dtoverlay=vc4-kms-dsi-7inch,invx,invy

`/boot/firmware/cmdline.txt`, appended to the single line:

    video=DSI-1:800x480@60,panel_orientation=upside_down

- `panel_orientation` sets the DRM connector property that fbcon and
  plymouth read. labwc ignores it.
- The desktop gets `transform 180` from `~/.config/kanshi/config`
  (`config/kanshi/config`). The greeter gets it from
  `/etc/xdg/labwc-greeter/config.kanshi` (`config/labwc-greeter/`).
- kanshi applies the rotation only after labwc's first frames, so
  `systemd/lightdm.service.d/20-dsi-dark.conf` blanks the panel before
  lightdm starts. `dsi-backlight-enable` turns it back on later.
- The overlay inverts touch x and y by default. `invx`/`invy` *remove* that
  inversion.
