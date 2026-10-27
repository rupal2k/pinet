#!/usr/bin/env python3
"""Full-screen touch passcode lock for the DSI panel.

Shown on wake-from-sleep by dsi-tap-wake.py. Covers the whole screen via the
Wayland layer-shell OVERLAY layer (anchored to all four edges = full output)
with an OPAQUE background, so the desktop behind is fully blocked -- both
visually and to touch. Presents an on-screen number pad (also accepts a
physical keyboard). Entering the configured passcode unlocks (quits).

Single-instance: a second launch while one is already up just exits, so
repeated sleep/wake cycles don't stack locks.

Passcode: first line of /etc/dsi-lock/passcode (default 1234).
Recovery if it ever won't unlock: over SSH run
    kill "$(cat /run/user/1000/dsi-lock.pid)"
"""
import os
import subprocess
import sys
import time

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
gi.require_version("GtkLayerShell", "0.1")
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk, GtkLayerShell

PASSCODE_FILE = "/etc/dsi-lock/passcode"
LOGO_FILE = "/etc/dsi-lock/logo.png"
RUNTIME = os.environ.get("XDG_RUNTIME_DIR", "/run/user/%d" % os.getuid())
PIDFILE = os.path.join(RUNTIME, "dsi-lock.pid")
READYFILE = os.path.join(RUNTIME, "dsi-lock.ready")

CSS = b"""
window { background-color: #0f1114; }
#title { color: #e8e8e8; font-size: 22px; font-weight: bold; margin-top: 2px; }
#dots  { color: #e8e8e8; font-size: 30px; }
#dots.bad { color: #d24141; }
button.key {
    background: #282c30;
    color: #e8e8e8;
    font-size: 25px;
    border-radius: 14px;
    border: 2px solid rgba(255,255,255,0.14);
    min-width: 90px;
    min-height: 70px;
    margin: 4px;
}
button.key:active { background: #5078b4; }
button.off {
    background: #3c4044;
    color: #e8e8e8;
    font-size: 15px;
    border-radius: 20px;
    border: 2px solid rgba(255,255,255,0.18);
    min-width: 110px;
    min-height: 64px;
    padding: 0 6px;
}
button.off:active { background: #7a3c3c; }
"""


def read_passcode():
    # Fail closed: a missing/empty/unreadable passcode file used to unlock
    # with DEFAULT_PASSCODE. Now nothing unlocks -- recover over SSH with the
    # kill in the header above.
    try:
        with open(PASSCODE_FILE) as f:
            return f.readline().strip() or None
    except OSError:
        return None


def single_instance():
    try:
        fd = os.open(PIDFILE, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    except FileExistsError:
        try:
            with open(PIDFILE) as f:
                os.kill(int(f.read().strip() or "-1"), 0)
            return False
        except (OSError, ValueError):
            try:
                os.unlink(PIDFILE)
                fd = os.open(PIDFILE, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
            except OSError:
                return False
    os.write(fd, str(os.getpid()).encode())
    os.close(fd)
    return True


class Lock:
    def __init__(self):
        self.code = read_passcode()
        self.entered = ""
        self.fails = 0
        self.blocked_until = 0.0
        self._pin_missing = self.code is None

        prov = Gtk.CssProvider()
        prov.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), prov,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        # Plain opaque toplevel (no app_paintable / rgba visual) so GTK fills
        # the whole surface with the CSS background and the desktop can't show
        # through -- this is a lock, not a transparent overlay button.
        win = Gtk.Window(type=Gtk.WindowType.TOPLEVEL)
        win.set_decorated(False)

        GtkLayerShell.init_for_window(win)
        GtkLayerShell.set_layer(win, GtkLayerShell.Layer.OVERLAY)
        for edge in (GtkLayerShell.Edge.TOP, GtkLayerShell.Edge.BOTTOM,
                     GtkLayerShell.Edge.LEFT, GtkLayerShell.Edge.RIGHT):
            GtkLayerShell.set_anchor(win, edge, True)
        GtkLayerShell.set_exclusive_zone(win, -1)
        GtkLayerShell.set_keyboard_mode(win, GtkLayerShell.KeyboardMode.EXCLUSIVE)

        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        outer.set_halign(Gtk.Align.CENTER)
        outer.set_valign(Gtk.Align.CENTER)

        # PINET logo (optional -- skip cleanly if the asset is missing).
        try:
            pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(LOGO_FILE, -1, 76, True)
            outer.pack_start(Gtk.Image.new_from_pixbuf(pb), False, False, 0)
        except Exception:
            pass

        self.title = Gtk.Label(label="PIN unavailable — recover via SSH" if self._pin_missing else "Enter passcode")
        self.title.set_name("title")
        self.dots = Gtk.Label(label="–")
        self.dots.set_name("dots")
        outer.pack_start(self.title, False, False, 0)
        outer.pack_start(self.dots, False, False, 0)

        grid = Gtk.Grid()
        grid.set_halign(Gtk.Align.CENTER)
        keys = [("1", 0, 0), ("2", 1, 0), ("3", 2, 0),
                ("4", 0, 1), ("5", 1, 1), ("6", 2, 1),
                ("7", 0, 2), ("8", 1, 2), ("9", 2, 2),
                ("⌫", 0, 3), ("0", 1, 3), ("C", 2, 3)]
        for label, col, row in keys:
            b = Gtk.Button(label=label)
            b.get_style_context().add_class("key")
            b.connect("clicked", self.on_key, label)
            if self._pin_missing:
                b.set_sensitive(False)
            if label == "⌫":
                b.get_accessible().set_name("Backspace")
            grid.attach(b, col, row, 1, 1)
        outer.pack_start(grid, False, False, 0)

        # "Screen off" control (top-right): sleeps the DSI panel immediately
        # instead of waiting for idle-sleep. The lock stays up; a double-tap
        # wakes and re-lights it.
        overlay = Gtk.Overlay()
        overlay.add(outer)
        off_btn = Gtk.Button(label="Screen off")
        off_btn.get_style_context().add_class("off")
        off_btn.set_halign(Gtk.Align.END)
        off_btn.set_valign(Gtk.Align.START)
        off_btn.set_margin_top(6)
        off_btn.set_margin_end(8)
        off_btn.connect("clicked", self.on_screen_off)
        overlay.add_overlay(off_btn)
        win.add(overlay)
        win.connect("destroy", Gtk.main_quit)
        win.connect("key-press-event", self.on_keypress)
        self._ready = False
        win.connect("map-event", self._on_map)
        GLib.timeout_add(500, self._signal_ready)
        win.show_all()

    def _signal_ready(self):
        # Mark that the lock is up so the wake path lights the backlight only
        # now -- the desktop is never shown before the lock. Idempotent; fired
        # from map-event (+ a short frame delay) with a timeout fallback.
        if not self._ready:
            self._ready = True
            try:
                open(READYFILE, "w").close()
            except OSError:
                pass
        return False

    def _on_map(self, _w, _e):
        GLib.timeout_add(80, self._signal_ready)
        return False

    def refresh(self):
        self.dots.set_text("●" * len(self.entered) if self.entered else "–")

    def _pqiv_running(self):
        try:
            for pid in os.listdir('/proc'):
                if not pid.isdigit():
                    continue
                try:
                    with open(f'/proc/{pid}/cmdline', 'rb') as f:
                        exe = f.read().split(b'\x00')[0]
                        if b'pqiv' in exe:
                            return True
                except OSError:
                    pass
        except OSError:
            pass
        return False

    def _unlock(self):
        Gtk.main_quit()

    def _start_countdown(self):
        def _tick():
            from math import ceil
            remaining = self.blocked_until - time.monotonic()
            if remaining <= 0:
                self.title.set_text("Enter passcode")
                return False
            self.title.set_text(f"Try again in {ceil(remaining)}s")
            return True
        GLib.timeout_add(1000, _tick)

    def feed(self, digit):
        if self.code is None:
            return
        if time.monotonic() < self.blocked_until:
            return
        self.dots.get_style_context().remove_class("bad")
        self.entered += digit
        if self.entered == self.code:
            self._unlock()
            return
        self.refresh()
        if len(self.entered) >= len(self.code):
            self.reject()

    def reject(self):
        # 4 digits is only 10^4 codes: after 5 wrong ones, ignore input for
        # 30s, doubling per further miss up to an hour.
        if time.monotonic() >= self.blocked_until:
            self.fails += 1
            if self.fails >= 5:
                self.blocked_until = time.monotonic() + min(30 << (self.fails - 5), 3600)
                self._start_countdown()
        self.dots.set_text("✕")
        self.dots.get_style_context().add_class("bad")
        self.entered = ""
        GLib.timeout_add(700, self._clear_bad)

    def _clear_bad(self):
        self.dots.get_style_context().remove_class("bad")
        self.refresh()
        return False

    def backspace(self):
        self.entered = self.entered[:-1]
        self.refresh()

    def on_key(self, _btn, label):
        if label.isdigit():
            self.feed(label)
        elif label == "⌫":
            self.backspace()
        elif label == "C":
            self.entered = ""
            self.refresh()

    def on_screen_off(self, _btn):
        # Sleep the panel now (output + backlight off). No slideshow runs behind
        # the lock, so dsi-sleep.sh sleeps rather than no-opping. The lock keeps
        # running; a double-tap re-lights it.
        subprocess.Popen(["/usr/local/bin/dsi-sleep.sh"])

    def on_keypress(self, _w, event):
        name = Gdk.keyval_name(event.keyval) or ""
        if len(name) == 1 and name.isdigit():
            self.feed(name)
        elif name.startswith("KP_") and name[3:].isdigit():
            self.feed(name[3:])
        elif name == "BackSpace":
            self.backspace()
        elif name in ("Return", "KP_Enter"):
            if self.code is None:
                pass
            elif len(self.entered) < len(self.code):
                pass
            elif self.entered == self.code:
                self._unlock()
            else:
                self.reject()
        return True


def main():
    if not single_instance():
        sys.exit(0)
    try:
        Lock()
        Gtk.main()
    finally:
        for f in (PIDFILE, READYFILE):
            try:
                os.unlink(f)
            except OSError:
                pass


if __name__ == "__main__":
    main()
