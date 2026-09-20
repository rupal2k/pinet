#!/usr/bin/env python3
"""Native on-screen Photo/Record controls for the DSI Camera kiosk.

The kiosk renders the live camera view in cog (WPE WebKit), which does NOT
deliver taps to web content -- so in-page buttons never fire. These controls
are instead a Wayland layer-shell overlay (GTK, like dsi-close-button.py, which
is proven tappable), sitting above the cog view. Tapping a button POSTs to the
localhost dsi-cam-server capture endpoints; captures are saved to
/mnt/pinet-media/camera, and FILES opens that folder in the file manager.
"""
import json
import shutil
import subprocess
import threading
import urllib.request

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GtkLayerShell", "0.1")
from gi.repository import Gdk, GLib, Gtk, GtkLayerShell

BASE = "http://127.0.0.1:8081"
# Same directory dsi-cam-server.py writes captures to.
MEDIA_DIR = "/mnt/pinet-media/camera"

CSS = b"""
window { background-color: rgba(0, 0, 0, 0); }
#status {
    color: #fff; font-size: 15px; font-weight: bold;
    text-shadow: 0 1px 3px rgba(0,0,0,0.9);
    margin-bottom: 6px;
}
button {
    background-color: rgba(24, 24, 26, 0.72);
    color: rgba(255, 255, 255, 0.95);
    border: 3px solid rgba(255, 255, 255, 0.85);
    border-radius: 14px;
    font-size: 22px; font-weight: bold;
    min-width: 110px; min-height: 60px;
    margin: 0 8px; padding: 0 6px;
}
button:active { background-color: rgba(90, 90, 90, 0.8); }
button#rec.recording { border-color: #ff4136; color: #ff4136; }
"""


def post(path, timeout):
    req = urllib.request.Request(BASE + path, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def main():
    recording = {"on": False}

    style = Gtk.CssProvider()
    style.load_from_data(CSS)
    Gtk.StyleContext.add_provider_for_screen(
        Gdk.Screen.get_default(), style, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
    )

    window = Gtk.Window(type=Gtk.WindowType.TOPLEVEL)
    window.set_decorated(False)
    window.set_app_paintable(True)
    visual = window.get_screen().get_rgba_visual()
    if visual is not None:
        window.set_visual(visual)

    GtkLayerShell.init_for_window(window)
    GtkLayerShell.set_layer(window, GtkLayerShell.Layer.OVERLAY)
    # Anchor to the bottom edge only -> horizontally centred at the bottom.
    GtkLayerShell.set_anchor(window, GtkLayerShell.Edge.BOTTOM, True)
    GtkLayerShell.set_margin(window, GtkLayerShell.Edge.BOTTOM, 14)
    GtkLayerShell.set_exclusive_zone(window, -1)
    GtkLayerShell.set_keyboard_mode(window, GtkLayerShell.KeyboardMode.NONE)

    outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
    status = Gtk.Label(label="")
    status.set_name("status")
    outer.pack_start(status, False, False, 0)

    row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
    row.set_halign(Gtk.Align.CENTER)
    photo_btn = Gtk.Button(label="PHOTO")
    rec_btn = Gtk.Button(label="REC")
    rec_btn.set_name("rec")
    files_btn = Gtk.Button(label="FILES")
    row.pack_start(photo_btn, False, False, 0)
    row.pack_start(rec_btn, False, False, 0)
    row.pack_start(files_btn, False, False, 0)
    outer.pack_start(row, False, False, 0)
    window.add(outer)

    def set_status(text):
        status.set_text(text)
        return False

    def on_photo(_btn):
        set_status("Saving photo…")

        def work():
            try:
                d = post("/capture/photo", timeout=30)
                msg = "Saved " + d["file"] if d.get("ok") else "Photo failed"
            except Exception:  # noqa: BLE001
                msg = "Photo failed"
            GLib.idle_add(set_status, msg)

        threading.Thread(target=work, daemon=True).start()

    def on_rec(_btn):
        if not recording["on"]:
            recording["on"] = True
            rec_btn.set_label("STOP")
            rec_btn.get_style_context().add_class("recording")
            set_status("Recording…")

            def work_start():
                try:
                    d = post("/record/start", timeout=30)
                    if not d.get("ok"):
                        GLib.idle_add(reset_rec, "Record failed")
                except Exception:  # noqa: BLE001
                    GLib.idle_add(reset_rec, "Record failed")

            threading.Thread(target=work_start, daemon=True).start()
        else:
            recording["on"] = False
            rec_btn.set_label("REC")
            rec_btn.get_style_context().remove_class("recording")
            set_status("Saving video…")

            def work_stop():
                try:
                    d = post("/record/stop", timeout=180)
                    msg = "Saved " + d["file"] if d.get("ok") else "Stop failed"
                except Exception:  # noqa: BLE001
                    msg = "Stop failed"
                GLib.idle_add(set_status, msg)

            threading.Thread(target=work_stop, daemon=True).start()

    def reset_rec(msg):
        recording["on"] = False
        rec_btn.set_label("REC")
        rec_btn.get_style_context().remove_class("recording")
        status.set_text(msg)
        return False

    def on_files(_btn):
        # The kiosk stays up; the file manager opens over it, and the overlay
        # close button is still there to get back to the desktop.
        fm = shutil.which("pcmanfm") or shutil.which("xdg-open")
        if fm is None:
            set_status("No file manager")
            return
        try:
            subprocess.Popen([fm, MEDIA_DIR])
            set_status("Opening " + MEDIA_DIR)
        except OSError:
            set_status("Could not open folder")

    photo_btn.connect("clicked", on_photo)
    rec_btn.connect("clicked", on_rec)
    files_btn.connect("clicked", on_files)
    window.connect("destroy", Gtk.main_quit)
    window.show_all()
    Gtk.main()


if __name__ == "__main__":
    main()
