"""Small vector icons drawn with PIL primitives -- no external image files.

Every function takes a PIL ImageDraw object, a center or top-left position,
and a `color` (0=black, 255=white on a 1-bit e-ink canvas), and draws within
a bounded box so callers can lay out rows without surprises:
  calendar/cpu_chip/ram_stick/wired: bounded by (x, y, x+size, y+size)
  clock/wifi/weather icons: bounded by roughly cy-14..cy+14 around a center

Modernized 2026-09-06 evening against a rounded, evenly-weighted reference
icon set (see the vault): every outline/stroke in this file is now a
consistent `width=2` (was a mix of the PIL default `width=1` and `2`/`3`,
which read as mismatched weight between icons), and every hard-cornered
rectangle became `rounded_rectangle`. Deliberately NOT copied as literal
hairline/`width=1` strokes the way the reference draws them -- on this
panel (1-bit, small, meant to be read from across a room, see
[[fixes session log]] fix #7's layout-hierarchy reasoning) a 1px line
would alias away to near-invisible, so "modern" here means adopting the
reference's roundness and consistency, adapted to a bolder weight this
specific medium actually needs.

Cloud-based icons (cloud/rain/snow/fog/thunder) fill each of several
overlapping circles solid (`fill=color`) -- solid overlap is harmless with
fills, so this produces one clean cloud silhouette in a single pass,
unlike an outline-per-circle approach (leaves visible seams where circles
cross) that this replaced.
"""
import math


def calendar(draw, x, y, size=11, color=0):
    draw.rounded_rectangle((x, y, x + size, y + size), radius=2, outline=color, width=2)
    draw.line((x, y + 3, x + size, y + 3), fill=color, width=2)
    draw.line((x + 3, y - 2, x + 3, y + 1), fill=color, width=2)
    draw.line((x + size - 3, y - 2, x + size - 3, y + 1), fill=color, width=2)


def clock(draw, cx, cy, r=9, color=0):
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), outline=color, width=2)
    draw.line((cx, cy, cx, cy - r + 2), fill=color, width=2)
    draw.line((cx, cy, cx + r - 3, cy), fill=color, width=2)
    # small rounded cap on the minute hand's tip -- a softer, friendlier
    # line-ending than PIL's default square butt cap, at negligible cost
    tip_r = 1
    draw.ellipse((cx - tip_r, cy - r + 2 - tip_r, cx + tip_r, cy - r + 2 + tip_r), fill=color)


def cpu_chip(draw, x, y, size=14, color=0):
    """At this icon's actual size (~12-14px, one small strip on the
    status screen) a 2px stroke plus 6 pins left almost no interior
    negative space and read as a solid blob, not a chip -- reported as
    "horrible" and confirmed by a zoomed render of the real in-context
    size, not just the isolated icon gallery (which renders bigger and
    hid the problem). Fixed with a 1px outline, a single centered die
    dot, and 2 pins per side instead of 3 -- fewer, better-separated
    marks read clearer at this scale than more, thinner ones."""
    pad = 3
    body = (x + pad, y + pad, x + size - pad, y + size - pad)
    draw.rounded_rectangle(body, radius=1, outline=color, width=1)
    cx, cy = (body[0] + body[2]) / 2, (body[1] + body[3]) / 2
    draw.point((cx, cy), fill=color)
    for dx in (-2, 2):
        px = x + size / 2 + dx
        draw.line((px, y, px, y + pad), fill=color, width=1)
        draw.line((px, y + size - pad, px, y + size), fill=color, width=1)


def ram_stick(draw, x, y, w=16, h=10, color=0):
    """Same fix as `cpu_chip` and for the same reason -- a 2px outline at
    this icon's small actual size read as a heavy filled blob rather than
    a stick. 1px outline, 3 teeth instead of 4, more spacing between."""
    draw.rounded_rectangle((x, y, x + w, y + h), radius=1, outline=color, width=1)
    for i in range(3):
        lx = x + w * (i + 1) / 4
        draw.line((lx, y + h, lx, y + h + 3), fill=color, width=1)


def wifi(draw, cx, cy, size=10, color=0):
    draw.ellipse((cx - 1.5, cy - 1.5, cx + 1.5, cy + 1.5), fill=color)
    for r in (size // 3 + 2, size * 2 // 3 + 3, size + 4):
        draw.arc((cx - r, cy - r, cx + r, cy + r), start=210, end=330, fill=color, width=2)


def antenna(draw, cx, cy, size=10, color=0):
    """Radio antenna broadcasting a signal -- a mast planted on a small
    foot with a ball at the tip and concentric arcs fanning outward/upward
    from it, used for the PINET hotspot screen in place of the mobile-
    style `wifi` glyph (a visible mast is what reads as "antenna" rather
    than "phone signal bars")."""
    mast_h = size * 1.7
    tip_y = cy - size * 0.6
    base_y = tip_y + mast_h
    draw.line((cx, tip_y, cx, base_y), fill=color, width=2)
    draw.line((cx - size * 0.4, base_y, cx + size * 0.4, base_y), fill=color, width=2)
    r = max(1.5, size * 0.14)
    draw.ellipse((cx - r, tip_y - r, cx + r, tip_y + r), fill=color)
    for k in (1, 2, 3):
        rad = size * 0.32 * k
        bbox = (cx - rad, tip_y - rad, cx + rad, tip_y + rad)
        draw.arc(bbox, start=200, end=340, fill=color, width=2)


def wired(draw, x, y, size=12, color=0):
    """RJ45 plug: a tapered polygon body (wider at the pin end, narrower
    at the clip end, matching a real 8P8C connector), an off-center clip
    tab on top, and 8 thin contact pins along the bottom edge. Restored
    2026-09-06 evening -- had silently reverted to a plain square-with-
    two-feet, which reads as a monitor-on-a-stand rather than a network
    plug (flagged and fixed once already, see [[fixes session log]])."""
    top_w = size * 0.72
    body_top = y + size * 0.22
    body_bottom = y + size * 0.68
    top_l = x + (size - top_w) / 2
    top_r = top_l + top_w
    draw.polygon(
        [(top_l, body_top), (top_r, body_top), (x + size, body_bottom), (x, body_bottom)],
        outline=color, width=2,
    )
    tab_w = size * 0.14
    tab_x = top_l + top_w * 0.6
    draw.rectangle((tab_x, y, tab_x + tab_w, body_top - 1), fill=color)
    n = 8
    for i in range(n):
        px = x + size * (i + 0.5) / n
        draw.line((px, body_bottom, px, y + size), fill=color, width=1)


def offline(draw, cx, cy, size=10, color=0):
    wifi(draw, cx, cy, size=size, color=color)
    r = size + 2
    draw.line((cx - r, cy - r, cx + r, cy + r), fill=color, width=2)


def pirate(draw, cx, cy, size=10, color=0):
    """Skull and crossbones -- shown in the network box in place of the
    normal offline glyph while a WiFi pentest session is active (wlan1 in
    monitor mode, see /usr/local/sbin/wifi-pentest-start): the network box
    already reads "Offline" in that state (there's genuinely no route out
    once wlan1 leaves managed mode), so this just makes the *reason*
    visible at a glance instead of looking like an ordinary connectivity
    drop."""
    skull_r = size * 0.62
    skull_cy = cy - size * 0.22
    draw.ellipse(
        (cx - skull_r, skull_cy - skull_r, cx + skull_r, skull_cy + skull_r),
        outline=color, width=2,
    )
    eye_r = max(1.3, size * 0.16)
    eye_dx = skull_r * 0.42
    eye_y = skull_cy + skull_r * 0.05
    draw.ellipse((cx - eye_dx - eye_r, eye_y - eye_r, cx - eye_dx + eye_r, eye_y + eye_r), fill=color)
    draw.ellipse((cx + eye_dx - eye_r, eye_y - eye_r, cx + eye_dx + eye_r, eye_y + eye_r), fill=color)
    jaw_w = skull_r * 0.5
    jaw_y = skull_cy + skull_r * 0.85
    draw.line((cx - jaw_w, jaw_y, cx + jaw_w, jaw_y), fill=color, width=1)

    bone_len = size * 1.15
    bone_y = cy + size * 0.62
    for sign in (1, -1):
        x0 = cx - bone_len * 0.5
        x1 = cx + bone_len * 0.5
        y0 = bone_y - sign * size * 0.32
        y1 = bone_y + sign * size * 0.32
        draw.line((x0, y0, x1, y1), fill=color, width=2)


def exclamation(draw, cx, cy, size=9, color=0):
    """Warning "!" glyph -- a rounded bar plus a dot, used for a data source
    that couldn't be fetched (e.g. no network connectivity)."""
    bar_w = max(2, round(size * 0.28))
    bar_top = cy - size
    bar_bottom = cy + size * 0.25
    draw.rounded_rectangle((cx - bar_w / 2, bar_top, cx + bar_w / 2, bar_bottom), radius=bar_w / 2, fill=color)
    dot_r = bar_w * 0.75
    dot_cy = cy + size * 0.65
    draw.ellipse((cx - dot_r, dot_cy - dot_r, cx + dot_r, dot_cy + dot_r), fill=color)


def sun(draw, cx, cy, r=7, color=0):
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=color)
    for angle in range(0, 360, 45):
        rad = math.radians(angle)
        x1 = cx + (r + 3) * math.cos(rad)
        y1 = cy + (r + 3) * math.sin(rad)
        x2 = cx + (r + 7) * math.cos(rad)
        y2 = cy + (r + 7) * math.sin(rad)
        draw.line((x1, y1, x2, y2), fill=color, width=2)


def moon(draw, cx, cy, r=7, color=0, bg=255):
    """Crescent used instead of `sun` for clear/mainly-clear codes at
    night (see `weather_icon`'s `night` flag). A filled disc with a
    second, off-center disc erased in the background color -- same
    fill-based silhouette trick the cloud family uses -- rather than a
    color swap. offset=r*0.55 tuned by trial to stay a clearly separate
    thin crescent instead of a near-total overlap or a barely-clipped
    circle."""
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=color)
    offset = r * 0.55
    draw.ellipse((cx - r + offset, cy - r, cx + r + offset, cy + r), fill=bg)


def _cloud_shapes(cx, cy, w, h):
    """(x, y, rx, ry) for each circle making up the cloud silhouette."""
    return [
        (cx - w * 0.30, cy + h * 0.05, h * 0.40, h * 0.40),
        (cx - w * 0.02, cy - h * 0.22, h * 0.52, h * 0.52),
        (cx + w * 0.26, cy - h * 0.02, h * 0.42, h * 0.42),
        (cx + w * 0.40, cy + h * 0.14, h * 0.30, h * 0.30),
        (cx, cy + h * 0.30, w * 0.48, h * 0.30),
    ]


def cloud(draw, cx, cy, w=20, h=14, color=0, bg=255):
    """Solid cloud silhouette: fills each overlapping circle (`fill=color`)
    rather than outlining every circle and erasing the seams -- solid
    overlap is harmless with fills, so one pass gives a single clean
    silhouette instead of a "flying saucer" of disjoint thin outlines.
    Restored 2026-09-06 evening after silently reverting to the older
    outline-based approach; `bg` kept for signature compatibility even
    though this version no longer needs it."""
    for (sx, sy, rx, ry) in _cloud_shapes(cx, cy, w, h):
        draw.ellipse((sx - rx, sy - ry, sx + rx, sy + ry), fill=color)


def rain(draw, cx, cy, color=0):
    cloud(draw, cx, cy, color=color)
    for dx in (-6, 0, 6):
        draw.line((cx + dx, cy + 8, cx + dx - 2, cy + 13), fill=color, width=2)


def snow(draw, cx, cy, color=0):
    cloud(draw, cx, cy, color=color)
    for dx in (-6, 0, 6):
        draw.line((cx + dx - 2, cy + 11, cx + dx + 2, cy + 11), fill=color, width=2)
        draw.line((cx + dx, cy + 9, cx + dx, cy + 13), fill=color, width=2)


def fog(draw, cx, cy, w=20, color=0):
    for dy in (-3, 2, 7):
        draw.line((cx - w // 2, cy + dy, cx + w // 2, cy + dy), fill=color, width=2)


def thunder(draw, cx, cy, color=0):
    cloud(draw, cx, cy, color=color)
    draw.line(
        [(cx + 2, cy + 6), (cx - 2, cy + 10), (cx + 1, cy + 10), (cx - 3, cy + 15)],
        fill=color, width=2,
    )


# Open-Meteo WMO weather codes -> icon-drawing function
WEATHER_ICON_BY_CODE = {
    0: sun, 1: sun,
    2: cloud, 3: cloud,
    45: fog, 48: fog,
    51: rain, 53: rain, 55: rain, 56: rain, 57: rain,
    61: rain, 63: rain, 65: rain, 66: rain, 67: rain,
    80: rain, 81: rain, 82: rain,
    71: snow, 73: snow, 75: snow, 77: snow, 85: snow, 86: snow,
    95: thunder, 96: thunder, 99: thunder,
}


def weather_icon(draw, code, cx, cy, color=0, night=False):
    if night and code in (0, 1):
        moon(draw, cx, cy, color=color)
    else:
        (WEATHER_ICON_BY_CODE.get(code) or cloud)(draw, cx, cy, color=color)


def seigaiha(draw, x, y, w, h, scale=None, rings=3, rows=2, color=0):
    """Seigaiha (青海波) -- the traditional Japanese repeating wave pattern:
    overlapping concentric semicircle 'fans' tiled in offset rows. A subtle,
    genuinely Japanese background/watermark texture, bounded by (x,y,x+w,y+h).
    """
    if scale is None:
        scale = h * 1.1
    row_h = h / rows
    n = int(w / scale) + 2
    for row in range(rows):
        cy = y + h - row * row_h
        offset = (scale / 2) if (row % 2) else 0
        for i in range(-1, n):
            cx = x + i * scale + offset
            for k in range(1, rings + 1):
                r = row_h * k / rings * 1.3
                bbox = (cx - r, cy - r, cx + r, cy + r)
                draw.arc(bbox, start=180, end=360, fill=color, width=1)


def spotify(draw, cx, cy, size=9, color=0, bg=255):
    """Spotify mark: a filled disc with three upward-bowing 'sound wave' arcs
    (largest on top), drawn in the negative colour. Pure primitives so it
    scales down cleanly on the 1-bit panel."""
    r = size
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=color)
    for yo, wf, wd in ((-0.34, 0.74, 2), (-0.04, 0.54, 2), (0.24, 0.34, 1)):
        aw = r * wf          # half-width of this arc
        ah = r * 0.55        # arc bow height
        ay = cy + r * yo     # vertical centre of this arc's bbox
        draw.arc((cx - aw, ay - ah, cx + aw, ay + ah), start=200, end=340,
                 fill=bg, width=wd)
