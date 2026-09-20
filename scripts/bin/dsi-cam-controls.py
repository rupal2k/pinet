#!/usr/bin/env python3
"""Native on-screen Photo/Record controls for the DSI Camera kiosk.

The kiosk renders the live camera view in cog (WPE WebKit), which does NOT
deliver taps to web content -- so in-page buttons never fire. These controls
are instead a Wayland layer-shell overlay (GTK, like dsi-close-button.py, which
is proven tappable), sitting above the cog view. Tapping a button POSTs to the
localhost dsi-cam-server capture endpoints; captures are saved to
/mnt/pinet-media/camera, and FILES opens that folder in the file manager.
"""
import cairo
import io
import json
import shutil
import subprocess
import threading
import urllib.request
from math import pi

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
gi.require_version("GtkLayerShell", "0.1")
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk, GtkLayerShell

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
    min-width: 104px; min-height: 64px;
    margin: 0 8px; padding: 2px 6px;
}
button:active { background-color: rgba(90, 90, 90, 0.8); }
button#rec.recording { border-color: #ff4136; color: #ff4136; }
/* The word under the glyph: the icon alone would be a guess in a hurry. */
label.cap { font-size: 12px; font-weight: bold; letter-spacing: 1px; }
"""

# Glyphs are drawn with cairo rather than loaded as icons: no icon theme, no
# librsvg, no files to keep in step with the buttons. Each one is rasterised
# once at startup and handed over as a pixbuf -- both cheaper than redrawing
# on every expose, and it avoids the "draw" signal, which needs the
# python3-gi-cairo package this image does not carry. Stroke language is the
# desktop icon set's: a wide faint pass under a crisp one, so the edge reads
# soft rather than cut out.
INK = (1.0, 1.0, 1.0, 0.95)
REC_INK = (1.0, 0.25, 0.21, 0.95)   # #ff4136, same red as the recording border
ICON = 30                           # drawing area, px square


def _rounded(cr, x, y, w, h, r):
    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -pi / 2, 0)
    cr.arc(x + w - r, y + h - r, r, 0, pi / 2)
    cr.arc(x + r, y + h - r, r, pi / 2, pi)
    cr.arc(x + r, y + r, r, pi, 3 * pi / 2)
    cr.close_path()


def _ink(cr, rgba, fill=False):
    r, g, b, a = rgba
    cr.set_line_join(1)   # round
    cr.set_line_cap(1)
    cr.set_source_rgba(r, g, b, a * 0.25)
    cr.set_line_width(5.2)
    cr.stroke_preserve()
    cr.set_source_rgba(r, g, b, a)
    if fill:
        cr.fill()
    else:
        cr.set_line_width(2.2)
        cr.stroke()


def draw_photo(cr):
    _rounded(cr, 2, 9, 26, 17, 3.5)
    _ink(cr, INK)
    cr.move_to(8.5, 9.5)
    cr.line_to(11, 5.5)
    cr.line_to(19, 5.5)
    cr.line_to(21.5, 9.5)
    _ink(cr, INK)
    cr.arc(15, 17.5, 5.4, 0, 2 * pi)
    _ink(cr, INK)


def draw_rec(cr, recording):
    # Circle to start, square to stop: shape carries it, so the red is only
    # ever a second signal.
    if recording:
        _rounded(cr, 8, 8, 14, 14, 2.5)
    else:
        cr.arc(15, 15, 7.2, 0, 2 * pi)
    _ink(cr, REC_INK if recording else INK, fill=True)


def draw_files(cr):
    cr.move_to(3, 9.5)
    cr.line_to(3, 6.5)
    cr.line_to(10.5, 6.5)
    cr.line_to(12.8, 9.5)
    _ink(cr, INK)
    _rounded(cr, 2, 9.5, 26, 16, 3)
    _ink(cr, INK)


def pixbuf(draw):
    """Rasterise one glyph into a pixbuf, through PNG bytes: passing a cairo
    surface straight to Gdk needs the foreign-struct converter, which is the
    very package we are avoiding."""
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, ICON, ICON)
    draw(cairo.Context(surface))
    raw = io.BytesIO()
    surface.write_to_png(raw)
    loader = GdkPixbuf.PixbufLoader.new_with_type("png")
    loader.write(raw.getvalue())
    loader.close()
    return loader.get_pixbuf()


def icon_button(glyph, caption, name=None):
    """A button showing a drawn glyph over its word."""
    btn = Gtk.Button()
    area = Gtk.Image.new_from_pixbuf(glyph)
    cap = Gtk.Label(label=caption)
    cap.get_style_context().add_class("cap")
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
    box.set_halign(Gtk.Align.CENTER)
    box.pack_start(area, False, False, 0)
    box.pack_start(cap, False, False, 0)
    btn.add(box)
    btn.set_tooltip_text(caption.capitalize())
    btn.get_accessible().set_name(caption.capitalize())
    if name:
        btn.set_name(name)
    return btn, area, cap


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
    rec_glyph = pixbuf(lambda cr: draw_rec(cr, False))
    stop_glyph = pixbuf(lambda cr: draw_rec(cr, True))
    photo_btn, _, _ = icon_button(pixbuf(draw_photo), "PHOTO")
    rec_btn, rec_img, rec_cap = icon_button(rec_glyph, "REC", name="rec")
    files_btn, _, _ = icon_button(pixbuf(draw_files), "FILES")
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
            rec_cap.set_text("STOP")
            rec_img.set_from_pixbuf(stop_glyph)
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
            rec_cap.set_text("REC")
            rec_img.set_from_pixbuf(rec_glyph)
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
        rec_cap.set_text("REC")
        rec_img.set_from_pixbuf(rec_glyph)
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
