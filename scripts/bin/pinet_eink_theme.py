"""Shared GTK3 e-ink theme for the PINET desktop apps (Kali Tools, Ethernet
Share). One file so both apps read identically, and the look changes in one
place.

Matches the PINET confirm dialogs (the GTK4 gtk.css the zenity wrappers use):
pure black on white, Roboto, no colour anywhere. State and emphasis come from
weight, a 2px black frame and invert-on-press, never colour -- so a
colour-blind read and the 1-bit e-ink panel agree.

Pure data only (no gi import), so it loads under the stdlib unit tests too.
The importing script puts its own directory on sys.path first, so this file
resolves both in the repo (scripts/bin/) and deployed (/usr/local/bin/).
"""
import os

# PINET wordmark for an app header. First hit wins; both are the same file.
LOGO_PATHS = (os.path.expanduser("~/.local/share/icons/pinet-logo.png"),
              "/opt/pinet-board/static/pinet-logo.png")

CSS = b"""
* { outline: none; }
.root, .root.background { background-color: #ffffff; color: #000000;
                          font-family: "Roboto", sans-serif; }
.titlebar { background-color: #ffffff; border-bottom: 2px solid #000000;
            padding: 10px 14px; }
.app-title { color: #000000; font-weight: 800; font-size: 15px;
             letter-spacing: 2px; }
.app-sub { color: #000000; font-size: 10px; letter-spacing: 1px; }
/* OFF = outlined; ON = full invert (black fill). Text carries the word too. */
.pill { border-radius: 6px; padding: 5px 12px; font-size: 10px;
        font-weight: 700; letter-spacing: 1px; border: 2px solid #000000; }
.pill-off { background-color: #ffffff; color: #000000; }
.pill-on  { background-color: #000000; color: #ffffff; }
.ghost { background-color: #ffffff; color: #000000; border: 2px solid #000000;
         border-radius: 8px; padding: 6px 14px; font-size: 12px; font-weight: 700; }
.ghost:hover { background-color: #ffffff; border-color: #000000; }
.ghost:active, .ghost:checked { background-color: #000000; color: #ffffff; }
.danger { }
.card { background-color: #ffffff; border: 2px solid #000000;
        border-radius: 12px; }
.card-title { color: #000000; font-weight: 700; font-size: 11px;
              letter-spacing: 2px; }
.card-sub { color: #000000; font-size: 10px; }
.dot { border-radius: 2px; min-width: 8px; min-height: 8px;
       background-color: #000000; }
.tool { background-color: #ffffff; color: #000000; border: 2px solid #000000;
        border-radius: 8px; padding: 0; }
.tool:hover { background-color: #ffffff; border-color: #000000; }
.tool:active, .tool:checked { background-color: #000000; color: #ffffff; }
.tool:disabled { opacity: 0.35; }
.tool-name { color: inherit; font-weight: 700; font-size: 13px; }
.tool-desc { color: inherit; font-size: 10px; }
.badge { color: #000000; font-size: 9px; font-weight: 700; letter-spacing: 1px;
         border: 2px solid #000000; border-radius: 4px; padding: 0 4px; }
.pane-bar { background-color: #ffffff; border: 2px solid #000000;
            border-bottom: none; border-radius: 12px 12px 0 0; padding: 6px 10px; }
.pane-title { color: #000000; font-size: 11px; font-weight: 700; letter-spacing: 2px; }
.term { border: 2px solid #000000; border-radius: 0 0 12px 12px; }
.term text { background-color: #ffffff; color: #000000;
             font-family: monospace; font-size: 11px; }
.mini { padding: 3px 12px; font-size: 11px; }
entry { background-color: #ffffff; color: #000000; border: 2px solid #000000;
        border-radius: 6px; padding: 6px 8px; }
entry:focus { border-color: #000000; }
.cmd { color: #000000; font-family: monospace; font-size: 11px;
       background-color: #ffffff; border: 2px solid #000000; border-radius: 6px;
       padding: 8px; }
.field-label { color: #000000; font-size: 11px; font-weight: 700; }
.big-num { font-weight: 800; font-size: 40px; }
.stat-label { color: #000000; font-size: 10px; letter-spacing: 1px; }
"""
