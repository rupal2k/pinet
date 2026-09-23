#!/usr/bin/env python3
"""Generate the PINET desktop icon set (desktop/icons/*.svg).

Style: the e-ink panel's own look -- one ink tone on a dark panel, no hue --
in the HUD/chamfered shapes, sized for 48px icons on the pcmanfm desktop
(#14161a) and for librsvg, which draws them:
- one shared frame (chamfered square) so the nine read as one family;
- glyphs in one stroke weight, drawn twice -- a wide faint pass under a crisp
  core -- which on a single ink tone reads as a soft edge, not a neon glow;
- nothing is distinguished by colour alone: running is a dot, stopped is the
  same dot struck through, and the running state is additionally green;
- explicit colours, not currentColor: pcmanfm renders outside any CSS, so
  currentColor would come out black on the dark desktop;
- each icon has a <title>; the label under it on the desktop says the same.
Contrast on #14161a (measured): ink #e8e8e8 is 13.9:1, well past the 3:1 that
meaningful graphics need.

    python3 tools/make_desktop_icons.py    # rewrites desktop/icons/*.svg
"""
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "desktop" / "icons"

# One ink tone, as on the panel. The four names are kept so the glyph specs
# below still say which marks were accents; they all resolve to the same ink
# now, and the shapes carry the meaning.
INK = "#e8e8e8"
CYAN = MAGENTA = GREEN = RED = INK
# The one exception to the single ink tone: a service that is actually running
# is drawn in green, so the desktop says at a glance what is up. The off state
# keeps the struck-through dot, so the pair still reads without the colour.
LIVE = "#4ade80"
PANEL, FACE = "#0b0d12", "#050608"   # panel fill, and the portal figure's face
CORE, GLOW = 2.4, 5.6          # stroke widths: crisp line / halo under it
FRAME = "M9 4 H44 V39 L39 44 H4 V9 Z"   # chamfered top-left + bottom-right corners


def neon(d, color=CYAN, alpha=1.0):
    """A path drawn as halo + core in one colour; alpha dims both (e.g. 'off' states)."""
    return (f'<path d="{d}" stroke="{color}" stroke-width="{GLOW}" stroke-opacity="{0.22 * alpha:.2f}"/>'
            f'<path d="{d}" stroke="{color}" stroke-width="{CORE}" stroke-opacity="{alpha:.2f}"/>')


def dot(cx, cy, r, color):
    return (f'<circle cx="{cx}" cy="{cy}" r="{r + 1.8}" fill="{color}" fill-opacity="0.22"/>'
            f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{color}"/>')


def icon(title, body):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48" fill="none" '
            f'stroke-linecap="round" stroke-linejoin="round">\n'
            f'  <title>{title}</title>\n'
            f'  <path d="{FRAME}" fill="{PANEL}" fill-opacity="0.55" stroke="{CYAN}" stroke-opacity="0.38" stroke-width="1.4"/>\n'
            f'  <path d="M4 14 V9 L9 4 H14 M34 44 H39 L44 39 V34" stroke="{CYAN}" stroke-width="1.8"/>\n'
            f'  {body}\n</svg>\n')


# Wi-Fi arcs centred on (24, 31): radii 5, 10, 15 over a 100-degree sweep.
ARCS = ("M20.2 27.8 A5 5 0 0 1 27.8 27.8 "
        "M16.3 24.3 A10 10 0 0 1 31.7 24.3 "
        "M12.5 20.7 A15 15 0 0 1 35.5 20.7")

# A toggle's glyph and where its state dot sits. on = green and lit,
# off = ink, dimmed, struck through.
SPEAKER = ("M12 15 H25 V33 H12 Z M30 20 A8 8 0 0 1 30 28 "
           "M34.5 16 A14.5 14.5 0 0 1 34.5 32")
DRIVER = "M18.5 27.5 A4 4 0 1 1 18.49 27.5 Z"
STRIKE = "M13 13 L35 35"


def toggle(glyph, dot_at, on):
    x, y = dot_at
    if on:
        return neon(glyph, LIVE) + dot(x, y, 2.2, LIVE)
    return neon(glyph, alpha=0.45) + dot(x, y, 2.2, INK) + neon(STRIKE, INK)


ICONS = {
    "pinet-on": ("PINET hotspot is running", toggle(ARCS, (24, 32.5), True)),
    "pinet-off": ("PINET hotspot is stopped", toggle(ARCS, (24, 32.5), False)),
    "spotify-on": ("Spotify player is running",
                   toggle(SPEAKER + " " + DRIVER, (18.5, 19.5), True)),
    "spotify-off": ("Spotify player is stopped",
                    toggle(SPEAKER + " " + DRIVER, (18.5, 19.5), False)),
    "pinet-portal": ("PINET Portal message board",
                     # the PINET hooded figure: curved hood with a swept tip, dark
                     # face opening, glowing slit eyes (as in the wallpaper art)
                     neon("M24 8 C29 10 34 15 35 23 C36 29 37 33 40 38 H8 C11 33 12 29 13 23 C14 15 19 10 24 8 Z")
                     + f'<path d="M17 30 C17 22 20 18 24 18 C28 18 31 22 31 30 C28 32 20 32 17 30 Z" fill="{FACE}" stroke="{INK}" stroke-width="2.4"/>'
                     + neon("M19.8 24.6 L22.6 26 M28.2 24.6 L25.4 26", MAGENTA)),
    "photo-frame": ("Photo frame slideshow",
                    neon("M10 13 H38 V35 H10 Z")
                    + neon("M13 32 L20 24 L25 29 L29 25 L35 32", CYAN)
                    + dot(31, 18.5, 2.3, MAGENTA)),
    "camera": ("Camera",
               neon("M9 17 H16 L19 13 H29 L32 17 H39 V35 H9 Z")
               + neon("M24 20.5 A5.5 5.5 0 1 1 23.99 20.5 Z")
               + dot(34.5, 21.5, 1.6, MAGENTA)),
    "ezykam-cam": ("Ezykam IP camera",
                   # wall plate + arm, bullet camera tilted down, wireless arcs
                   neon("M10 13 V27 M10 20 H15")
                   + neon("M15 15 L32 18.5 L30.5 27 L14 23.5 Z")
                   + neon("M32 18.5 L35.5 19.2 L34.2 27.3 L30.5 27")
                   + dot(23, 21.2, 1.6, MAGENTA)
                   + neon("M31 32 A5 5 0 0 0 36 30.5 M29.5 37 A10 10 0 0 0 39.5 33.5", MAGENTA)),
    "kali-tools-pirate": ("Kali pentest tools",
                          # angular skull, slit eyes, crossbones
                          neon("M15 22 V16 L19 11 H29 L33 16 V22 L30 25 V29 H18 V25 Z")
                          + neon("M19 18.5 L22 20 M29 18.5 L26 20", MAGENTA)
                          + neon("M22 29 V26.5 M26 29 V26.5")
                          + neon("M11 31 L37 40 M37 31 L11 40")),
    "pinet-lock": ("Lock screen",
                   neon("M17 22 V17 A7 7 0 0 1 31 17 V22")
                   + neon("M13 22 H35 V37 L32 40 H13 Z")
                   + dot(24, 29.5, 2.2, MAGENTA) + neon("M24 31.5 V35", MAGENTA)),
    "graphs-network": ("Graphs viewer",
                       neon("M24 12 L12 33 M24 12 L36 31 M12 33 L36 31 M24 12 V25 M24 25 L12 33 M24 25 L36 31")
                       + dot(24, 12, 3.2, CYAN) + dot(12, 33, 3.2, CYAN) + dot(36, 31, 3.2, CYAN)
                       + dot(24, 25, 2.6, MAGENTA)),
}

if __name__ == "__main__":
    for name, spec in ICONS.items():
        (OUT / f"{name}.svg").write_text(icon(*spec))
        print("wrote", name)
