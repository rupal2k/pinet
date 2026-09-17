#!/usr/bin/env python3
"""Tablet-style touch handling for the DSI touchscreen.

While the screen is asleep (backlight blanked), grab the touchscreen
exclusively so taps on the dark panel never reach apps -- otherwise they
press invisible buttons (e.g. the slideshow's close button). While grabbed,
a double-tap wakes the screen; once awake the grab is released and touch
works normally.

On wake the passcode lock (dsi-lock.py) is raised over the screen so waking
from sleep asks for a code before the desktop is usable. The lock is started
just before the wake -- while the touchscreen is still grabbed and before the
backlight returns -- so it is already the top surface and no tap can reach an
app behind it. dsi-lock.py is single-instance, so repeated sleep/wake cycles
never stack locks.

Reads raw evdev directly (independent of the compositor), so it keeps
working with the DSI output blanked.
"""
import glob
import os
import select
import subprocess
import time

import evdev
from evdev import ecodes

DOUBLE_TAP_WINDOW = 0.5   # seconds between taps to count as a double-tap
COOLDOWN = 1.5            # ignore further taps for this long after waking
STATE_POLL = 1.0         # seconds between asleep/awake checks
WAKE_SCRIPT = "/usr/local/bin/dsi-wake.sh"
LOCK_SCRIPT = "/usr/local/bin/dsi-lock.py"
RUNTIME = os.environ.get("XDG_RUNTIME_DIR", "/run/user/%d" % os.getuid())
LOCK_PIDFILE = os.path.join(RUNTIME, "dsi-lock.pid")
LOCK_READYFILE = os.path.join(RUNTIME, "dsi-lock.ready")


def find_touchscreen():
    for path in evdev.list_devices():
        dev = evdev.InputDevice(path)
        if "ft5x06" in dev.name.lower():
            return dev
    raise RuntimeError("no ft5x06 touchscreen input device found")


def is_asleep():
    matches = glob.glob("/sys/class/backlight/*/bl_power")
    if not matches:
        return True
    # Any non-zero bl_power is blanked: our sleep script writes 1, but a
    # compositor output-off makes the panel driver write 4 (POWERDOWN).
    with open(matches[0]) as f:
        return f.read().strip() != "0"


def set_grab(dev, want, grabbed):
    if want == grabbed:
        return grabbed
    try:
        dev.grab() if want else dev.ungrab()
        return want
    except OSError:
        return grabbed


def _lock_running():
    try:
        with open(LOCK_PIDFILE) as f:
            os.kill(int(f.read().strip() or "0"), 0)
        return True
    except (OSError, ValueError):
        return False


def _output_on():
    try:
        out = subprocess.run(["/usr/bin/wlopm"], capture_output=True,
                             text=True, check=False).stdout
    except OSError:
        return True  # if wlopm is missing, assume on rather than stall
    return "DSI-1 on" in out


def wake_and_lock():
    """Wake the panel with the passcode lock already painted, so the desktop
    is never shown first. Sequence: bring the output up but keep the backlight
    OFF (DSI_DEFER_BACKLIGHT), so nothing is visible yet; make sure the lock is
    running and has drawn a frame (it touches LOCK_READYFILE on first draw);
    only then light the backlight -- so the first lit frame is the lock. If the
    screen re-sleeps while already locked, the still-running lock's ready-file
    is already present, so this just re-lights the panel."""
    env = dict(os.environ)
    env.setdefault("XDG_RUNTIME_DIR", RUNTIME)
    env.setdefault("WAYLAND_DISPLAY", "wayland-0")

    wenv = dict(env)
    wenv["DSI_DEFER_BACKLIGHT"] = "1"
    subprocess.run([WAKE_SCRIPT], env=wenv, check=False)

    # dsi-wake.sh only powers the output on once its boot/install guards pass;
    # if it stayed off, honour that and do not light or lock.
    if not _output_on():
        return

    # Raise the lock (in its own scope) and wait until it has painted a frame;
    # only then light the backlight, so the first lit frame is the lock. Shared
    # with the photo-album close button so both raise the same lock.
    subprocess.run(["/usr/local/bin/dsi-lock-show"], env=env, check=False)
    subprocess.run(["sudo", "/usr/local/bin/dsi-backlight.sh", "on"], check=False)


def main():
    dev = find_touchscreen()
    grabbed = False
    last_down = 0.0
    last_wake = 0.0
    while True:
        grabbed = set_grab(dev, is_asleep(), grabbed)
        ready, _, _ = select.select([dev.fd], [], [], STATE_POLL)
        if not ready:
            continue
        for event in dev.read():
            if event.type != ecodes.EV_KEY or event.code != ecodes.BTN_TOUCH:
                continue
            if event.value != 1:  # only touch-down
                continue
            now = time.monotonic()
            if now - last_wake < COOLDOWN:
                continue
            if now - last_down <= DOUBLE_TAP_WINDOW:
                if is_asleep():
                    wake_and_lock()
                    last_wake = now
                last_down = 0.0
            else:
                last_down = now


if __name__ == "__main__":
    main()
