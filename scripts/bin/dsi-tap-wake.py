#!/usr/bin/env python3
"""Tablet-style touch handling for the DSI touchscreen.

While the screen is asleep (backlight blanked), grab the touchscreen
exclusively so taps on the dark panel never reach apps -- otherwise they
press invisible buttons (e.g. the slideshow's close button). While grabbed,
a double-tap wakes the screen; once awake the grab is released and touch
works normally.

Reads raw evdev directly (independent of the compositor), so it keeps
working with the DSI output blanked.
"""
import glob
import select
import subprocess
import time

import evdev
from evdev import ecodes

DOUBLE_TAP_WINDOW = 0.5   # seconds between taps to count as a double-tap
COOLDOWN = 1.5            # ignore further taps for this long after waking
STATE_POLL = 1.0          # seconds between asleep/awake checks
WAKE_SCRIPT = "/usr/local/bin/dsi-wake.sh"


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
                    subprocess.run([WAKE_SCRIPT], check=False)
                    last_wake = now
                last_down = 0.0
            else:
                last_down = now


if __name__ == "__main__":
    main()
