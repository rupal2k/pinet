# Boot display setup (official Raspberry Pi 7" Touch Display, v1)

Nothing is rotated: the PINET plymouth splash (boot and shutdown), the
console, the lightdm greeter, the desktop, the pointer and touch all use their
defaults, and that is the right way up for how the panel is mounted.

`/boot/firmware/config.txt`, under `[all]` (with `display_auto_detect=0`):

    dtoverlay=vc4-kms-dsi-7inch

`/boot/firmware/cmdline.txt` has no `video=` or `fbcon=rotate` entry.

Don't use `video=DSI-1:...,panel_orientation=...` (2026-10-07). With it, the
kernel turns the display hardware (the primary plane's rotation) whenever it
holds the screen. labwc then inherits that turn and never clears it, so the
pointer (on its own plane) comes out inverted and the desktop needs a
cancelling kanshi transform. Plymouth inherits it at shutdown ("Keeping hw 180°
rotation") and draws the shutdown splash the other way up from the boot one.
Check with `sudo grep rotation= /sys/kernel/debug/dri/0/state`: every plane
should be `rotation=1`.

The overlay inverts touch x and y by default, which is correct here. Don't add
`invx`/`invy` (on this overlay they *remove* that inversion).
