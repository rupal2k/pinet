---
tags: [project, raspberry-pi, dsi, touchscreen, slideshow, active]
---

# DSI touchscreen — photo frame, kiosks, power manager (2026-09-14/15)

The official Raspberry Pi 7" DSI touchscreen, added alongside the e-ink panel
(see [[Overview]] for the original "can a DSI screen coexist" research). It is
a photo frame by default, with on-demand kiosks (camera, Ezykam, PINET portal).

**None of the DSI scripts are in git.** They live in `/usr/local/bin/dsi-*`
and `/usr/local/sbin/` on the Pi. Only the e-ink side of the kiosk feature is
committed, in `~/pi-eink-dashboard` (`6bf0037`, `4103ca7`).

## Hardware and session

| Fact | Value |
|---|---|
| Panel | Official Pi 7" DSI touchscreen, 800x480, output `DSI-1` |
| Touch | `edt_ft5x06` (evdev name contains `ft5x06`) |
| Backlight | `/sys/class/backlight/10-0045` (`bl_power` 0 = on) |
| Brightness | `BRIGHTNESS=1` in `/etc/default/dsi-screen` (lowest, per user) |
| Session | lightdm autologin → labwc (Wayland), `WAYLAND_DISPLAY=wayland-0` |
| Camera | Pi camera, mounted portrait; `CAMERA_ROTATION=90` in `/etc/default/dsi-camera` |

## Screen sleep / wake

- **Idle sleep**: `dsi-idle-sleep.service` (user) = `swayidle -w timeout 90 dsi-sleep.sh`.
  `dsi-sleep.sh` powers the output off (`wlopm --off DSI-1`) then the backlight.
- **Double-tap wake**: `dsi-tap-wake.service` (user) runs `dsi-tap-wake.py`,
  which reads the touchscreen's evdev node directly. While the screen is
  asleep it **grabs the touchscreen exclusively (EVIOCGRAB)**, so taps on the
  dark panel never reach apps. Before this, invisible taps closed the
  slideshow via its ✕ and opened desktop menus. A double tap (two touch-downs
  within 0.5s) runs `dsi-wake.sh`; the grab is released once awake.
- **`dsi-wake.sh`**: output on → (if the slideshow runs) `toggle_fullscreen(1)`
  → backlight on → `systemctl --user try-restart dsi-idle-sleep.service`.
  - No-op until `/run/dsi-boot-ready` exists, and while
    `/run/dsi-install-guard` exists AND dpkg is running.
  - Defaults `WAYLAND_DISPLAY`/`XDG_RUNTIME_DIR`: the tap daemon starts
    before the session exports them, and without them wlopm fails
    (backlight on, output off = black screen).
  - **The idle-sleep re-arm (added 2026-09-15)** fixes a real bug: a
    double-tap wake never reaches the compositor (the touchscreen is
    grabbed), so swayidle never saw activity and never re-armed. The screen
    stayed on indefinitely until someone touched it again. Measured after
    the fix: back to sleep 88s after a double-tap wake with no touch.
- **Boot**: udev kills the backlight at probe; `systemd-backlight@backlight:10-0045`
  is masked; `dsi-backlight-enable.service` → `dsi-boot-enable.sh` waits for
  the e-ink journal's first `Carousel phase=` (cap 240s) + 8s. **User rule:
  the DSI never lights before the e-ink is live.** (e-ink ~T+35s, DSI ~T+105s.)

## Slideshow

- `dsi-photo-frame.service` (user) → `dsi-photo-frame.sh`: pqiv fullscreen
  (shuffle, 300s per photo, no fade) plus a layer-shell ✕ button
  (`dsi-close-button.py`) in the same cgroup; ✕ = service stop.
- **Photos**: `/mnt/pinet-media/slideshow/` (PINET USB drive, owned rupal,
  separate from the portal's `uploads/`; Desktop link "Slideshow Photos").
- **Sync**: `dsi-photo-sync.timer` (every 30s; a `.path` unit never fired for
  new files) → `dsi-photo-sync.sh` → `dsi-photo-normalize.sh`, restarting a
  running slideshow if the cache changed. QA-measured: a new photo appears
  within ~18s, a removed one is gone within ~24s.
- **Fit, never crop (user rule, 2026-09-15)**: `dsi-photo-normalize.sh`
  renders each photo into `slideshow-cache/` at exactly 800x480. The whole
  photo is fitted (`-resize 800x480`, not `^`) over a **blurred background**
  (user chose it over black bars): the same photo fill-cropped to an 80x48
  thumbnail, `-blur 0x5`, scaled up, `-modulate 50`. About 5s per large photo
  on the Pi 3, done once. A `.render-mode` marker in the cache forces a full
  rebuild whenever the rendering settings change. Previously photos were
  cropped to fill the screen (a portrait certificate lost most of its content).
- **Small-window bug (fixed 2026-09-15)**: if pqiv maps while the output is
  off, it comes up as a small window. The script powers the output on while
  pqiv starts, but after a heavy apt run pqiv took longer than the fixed 4s
  and still came up small. Fix: pqiv runs `--actions-from-stdin` on a fifo,
  `/run/user/1000/dsi-photo-frame.actions`, held open read-write by the
  script, and `dsi-wake.sh` sends `toggle_fullscreen(1)` through it on every
  wake (a no-op when already fullscreen). `dsi-wake.sh` writes only while the
  service is active, because a stale fifo blocks writers.
- The unit has `SuccessExitStatus=143`: systemd signals the whole cgroup on
  stop, which can also kill the EXIT trap's `rm`, making bash exit 143.

## Kiosks (desktop shortcuts)

`dsi-kiosk.sh <name> <url>` writes `/run/user/1000/kiosk-mode` (line 1 =
e-ink title, line 2 = label), waits for pi-power-manager to report `kiosk`,
launches the browser plus a ✕ button, and removes the flag on exit.

| Shortcut | Engine | Notes |
|---|---|---|
| Camera | cog (WPE WebKit), `LIBGL_ALWAYS_SOFTWARE=1` | `dsi-kiosk-camera.sh` starts `dsi-cam-server.py` (picamera2 MJPEG 640x480 @10fps on 127.0.0.1:8081). e-ink: "CAMERA MODE ON / Live view" |
| Ezykam | `dsi-webkiosk.py` (PyQt6 QtWebEngine, GPU off) | ✕ top-left. e-ink: "KIOSK MODE ON / Ezykam". Opens on Ezykam's QR login screen |
| PINET Portal | `dsi-webkiosk.py` with `DSI_KIOSK_SHED=no` | Added 2026-09-15 after Firefox was removed. No shedding (it would stop the portal itself), no kiosk flag. ✕ top-left so it doesn't overlap the slideshow's ✕ |

**No desktop browser** since 2026-09-15: Firefox purged at the user's request
(Chromium earlier; both browned the Pi out). The dead `x-www-browser` taskbar
launcher was removed from `~/.config/wf-panel-pi/wf-panel-pi.ini`.

## pi-power-manager

`/usr/local/sbin/pi-power-manager` (system service). While the kiosk flag
exists it stops, if running: slideshow, photo-sync timer, idle-sleep,
rpi-connect-wayvnc, PINET (stunnel, pinet-board, dnsmasq, hostapd), wayvnc,
bluetooth. State in `/run/pi-power-manager/`. Restores in reverse, 2s apart,
waiting ≤5s per step for under-voltage to clear; resumes an interrupted
restore. Keeps the e-ink, wlan1, sshd and rpi-connect running.

- **Bluetooth fix (2026-09-15)**: bluetooth is D-Bus activated
  (`dbus-org.bluez.service` alias), and the taskbar applet restarted a
  plain-stopped bluetoothd within ~0.1s, so it was never really shed. Now it
  is `mask --runtime`d while shed and unmasked just before restore
  (`MASK_WHILE_SHED`); a reboot also clears a runtime mask.
- **It works**: during the 2026-09-15 QA run of the Ezykam kiosk, live
  under-voltage cleared (`0x50005` → `0x50000`) while services were shed.
  A full restore takes ~30-80s.

## Install guard

`/etc/apt/apt.conf.d/80dsi-install-guard` → `/usr/local/sbin/dsi-install-guard pre|post`:
sync, DSI off, slideshow paused during dpkg; sync + restore afterwards.
`/etc/sysctl.d/90-sd-writeback.conf`: dirty 16MB / background 4MB / expire 10s
(the default held ~180MB for 30s). Exercised by every apt run on 2026-09-15.

## Look (PINET dark theme)

Taskbar at the bottom; launchers now `pcmanfm x-terminal-emulator`. Wallpaper
`~/Pictures/pinet-logo-wallpaper.png` (PINET logo on a #0f1114→#1e2128
gradient). GTK theme PiXonyx, panel `#1e2128ff`. Icon theme
`~/.local/share/icons/PINET` (hand-written white line SVGs; menu button = the
hood from the PINET logo). Font Nunito Sans Light 10. pcmanfm's desktop config
must be `desktop-items-DSI-1.conf`; restart with `pkill -x pcmanfm` (respawns).

## Boot splash (2026-09-15, not yet seen on a real boot)

`disable_splash=1` (config.txt), `logo.nologo` (cmdline.txt), Plymouth theme
`/usr/share/plymouth/themes/pinet`, `Theme=pinet` in `plymouthd.conf`; the
initramfs was rebuilt and contains the theme (verified in QA). **Recovery** if
it won't boot: on another PC rename `/boot/firmware/initramfs8.bak-splash`
back to `initramfs8` (`config.txt.bak-splash`, `cmdline.txt.bak-splash` and
`/etc/plymouth/plymouthd.conf.bak-splash` are also kept). A plymouth package
update could reset the theme; re-check `Theme=` after upgrades.

## Lessons

- Heavy load or heavy SD I/O (browsers, big apt installs, even `dpkg --verify`)
  stalls the SD controller ("Card stuck being busy") and the board resets.
  5 unclean resets on 2026-09-15. Real fix: a proper 5V/3A supply. See
  [[power and undervoltage]].
- Unclean resets zero recently written files: `sync` after every deploy and
  check sha256 after a reset. Never force a reboot.
- Over SSH, never `pkill -f`/`pgrep -f` a pattern that appears in the same
  command string: it matches (and kills) its own SSH session. Use exact PIDs.
- Testing touch remotely: writing EV_KEY/EV_ABS events to the ft5x06 evdev
  node injects real taps, which reach the grabbing tap daemon.

## Open items

- Camera picture is almost black (mean brightness 16/255 with auto-exposure
  on). Probably physical: what it points at, or a covered lens.
- Is brightness level 1 readable? Camera rotation 90 vs 270?
- Boot splash to be seen on the next natural reboot.

See also [[fixes session log]] entries 21-28 and [[pinet-board]].


---

## Update 2026-09-17 -- passcode lock, wake/close behaviour, photos, diagnostic

- **No sleep while the album is showing**: `dsi-sleep.sh` is now a no-op (and
  re-arms the idle timer) while `dsi-photo-frame.service` is active, so the
  frame stays lit; normal idle-sleep resumes once the album is closed.
- **Passcode lock (`dsi-lock.py`)**: waking from sleep (a real double-tap) now
  raises a full-screen **opaque** layer-shell lock with an on-screen number pad
  + the PINET hood logo; the code in `/etc/dsi-lock/passcode` (default `1234`)
  unlocks. Single-instance via `/run/user/1000/dsi-lock.pid`. Only the
  double-tap-from-sleep path in `dsi-tap-wake.py` (`wake_and_lock()`) locks --
  not boot/kiosk/demo/install-guard, which also call `dsi-wake.sh`.
  - No desktop shown before the lock: `dsi-wake.sh` defers the backlight
    (`DSI_DEFER_BACKLIGHT=1`) until the lock touches
    `/run/user/1000/dsi-lock.ready` on first `map-event`. Re-wake while locked
    re-lights. Cold-start ~3s on the first wake after an unlock; ~0.8s after.
  - Change the code: `echo NEW | sudo tee /etc/dsi-lock/passcode`. Recovery:
    `kill "$(cat /run/user/1000/dsi-lock.pid)"` over SSH.
- **Closing the album (X) drops to the lock, not the desktop**: `dsi-photo-close`
  (run by the X) raises the lock first via the shared helper `dsi-lock-show`
  (which launches it in its own `systemd-run --user --scope` so it survives the
  slideshow stop), then stops the slideshow. Enter the code to reach the desktop.
- **+12 scenic photos**: 4 each space / mountains / beach (see
  [[fixes session log]] entry 39). 15 in the slideshow now.
- **QA**: the DSI checks are now part of the whole-device `pi-diagnostic`
  (`pi-diagnostic dsi`) -- see [[test and preview scripts]].

**Still not in git** -- the new `dsi-lock*`, `dsi-photo-close`, `dsi-lock-show`,
`raspotify-nowplaying-hook` and `pi-diagnostic` live in `/usr/local/bin` on the
Pi; `.bak-<ts>` copies are the only history. Passcode default `1234` -- change it.

## Update 2026-09-17 (later) -- lock "Screen off" button

`dsi-lock.py` gained a top-right **"Screen off"** button (a `Gtk.Overlay` over
the keypad, so the number pad is unchanged) that runs `dsi-sleep.sh` to blank the
panel immediately instead of waiting for the 90s idle-sleep. The lock stays up; a
double-tap re-lights it. Verified with an injected touch (`bl_power` 0->1, lock
still running). The passcode was also changed from the default (value not
recorded). See [[fixes session log]] entry 44.

## Update 2026-09-17 (later 2) -- Lock Screen shortcut + backlight-only sleep

- **"Lock Screen" desktop shortcut** (`~/Desktop/lock-screen.desktop`, trusted, padlock
  icon `~/.local/share/icons/pinet-lock.svg`) runs `dsi-lock-show` to lock on demand.
- **`dsi-sleep.sh` no longer does `wlopm --off`** -- it blanks only the backlight, keeping
  the DSI output + ft5x06 touch powered. The user hit "touch not registered" for
  double-tap-to-wake after the Screen off button; disabling the output gates the touch
  panel's reporting (software-injected taps still woke it, but that isn't a real finger).
  Trade-off: a little more power (output stays on, screen dark). `pi-diagnostic all` = 50
  PASS after the change; physical double-tap still to be confirmed on the panel.
  See [[fixes session log]] entry 46.
