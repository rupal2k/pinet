#!/usr/bin/env python3
"""Small always-on-top, semi-transparent close button for a kiosk-style app
(photo frame, kiosk browser, ...). Uses the Wayland layer-shell protocol
(via gtk-layer-shell) so it renders above the app's surface and stays
tappable. Tapping it runs the command given as arguments, then exits.

Usage: [DSI_CLOSE_CORNER=left] dsi-close-button.py <command> [args...]
"""
import os
import subprocess
import sys

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GtkLayerShell", "0.1")
from gi.repository import Gdk, Gtk, GtkLayerShell

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
"""


def main():
    if len(sys.argv) < 2:
        print("usage: dsi-close-button.py <command> [args...]", file=sys.stderr)
        sys.exit(1)
    close_command = sys.argv[1:]

    def on_close_clicked(_button):
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
    window.add(button)
    window.connect("destroy", Gtk.main_quit)
    window.show_all()

    Gtk.main()


if __name__ == "__main__":
    main()
