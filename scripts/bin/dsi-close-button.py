#!/usr/bin/env python3
"""Small always-on-top, semi-transparent close button for a kiosk-style app
(photo frame, kiosk browser, ...). Uses the Wayland layer-shell protocol
(via gtk-layer-shell) so it renders above the app's surface and stays
tappable. Tapping it runs the command given as arguments, then exits.

With DSI_CLOSE_AUTOHIDE=<seconds> the button is invisible until tapped:
the first tap in its corner shows it, a second tap closes, and it hides
again after that many seconds untouched (the HDMI monitor uses this so the
video is unobstructed). Without it the button is always shown, as before.

Usage: [DSI_CLOSE_CORNER=left] [DSI_CLOSE_AUTOHIDE=4] dsi-close-button.py <command> [args...]
"""
import os
import subprocess
import sys

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GtkLayerShell", "0.1")
from gi.repository import Gdk, GLib, Gtk, GtkLayerShell

CSS = b"""
window {
    background-color: rgba(0, 0, 0, 0);
}
button {
    background-color: rgba(40, 40, 40, 0.4);
    color: rgba(255, 255, 255, 0.9);
    border-radius: 999px;
    border: 2px solid rgba(255, 255, 255, 0.45);
    font-size: 22px;
    font-weight: bold;
    min-width: 56px;
    min-height: 56px;
    padding: 0;
}
button:active {
    background-color: rgba(200, 40, 40, 0.6);
}
/* Auto-hide: fully transparent, but the window still takes the tap. */
button.hidden, button.hidden:active {
    background-color: rgba(0, 0, 0, 0);
    border-color: rgba(0, 0, 0, 0);
    color: rgba(0, 0, 0, 0);
}
"""


def main():
    if len(sys.argv) < 2:
        print("usage: dsi-close-button.py <command> [args...]", file=sys.stderr)
        sys.exit(1)
    close_command = sys.argv[1:]
    autohide = float(os.environ.get("DSI_CLOSE_AUTOHIDE") or 0)
    hide_timer = [0]

    def hide(button):
        button.get_style_context().add_class("hidden")
        hide_timer[0] = 0
        return False

    def on_close_clicked(button):
        style = button.get_style_context()
        if style.has_class("hidden"):
            # First tap only reveals the button; close needs a second one.
            style.remove_class("hidden")
            hide_timer[0] = GLib.timeout_add(int(autohide * 1000), hide, button)
            return
        if hide_timer[0]:
            GLib.source_remove(hide_timer[0])
        subprocess.run(close_command, check=False)
        Gtk.main_quit()

    style_provider = Gtk.CssProvider()
    style_provider.load_from_data(CSS)
    Gtk.StyleContext.add_provider_for_screen(
        Gdk.Screen.get_default(),
        style_provider,
        Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
    )

    window = Gtk.Window(type=Gtk.WindowType.TOPLEVEL)
    window.set_decorated(False)
    window.set_default_size(56, 56)
    window.set_app_paintable(True)

    screen = window.get_screen()
    visual = screen.get_rgba_visual()
    if visual is not None:
        window.set_visual(visual)

    GtkLayerShell.init_for_window(window)
    GtkLayerShell.set_layer(window, GtkLayerShell.Layer.OVERLAY)
    side = (GtkLayerShell.Edge.LEFT if os.environ.get("DSI_CLOSE_CORNER") == "left"
            else GtkLayerShell.Edge.RIGHT)
    GtkLayerShell.set_anchor(window, GtkLayerShell.Edge.TOP, True)
    GtkLayerShell.set_anchor(window, side, True)
    GtkLayerShell.set_margin(window, GtkLayerShell.Edge.TOP, 10)
    GtkLayerShell.set_margin(window, side, 10)
    GtkLayerShell.set_exclusive_zone(window, -1)
    GtkLayerShell.set_keyboard_mode(window, GtkLayerShell.KeyboardMode.NONE)

    button = Gtk.Button(label="✕")
    button.connect("clicked", on_close_clicked)
    if autohide > 0:
        button.get_style_context().add_class("hidden")
    window.add(button)
    window.connect("destroy", Gtk.main_quit)
    window.show_all()

    Gtk.main()


if __name__ == "__main__":
    main()
