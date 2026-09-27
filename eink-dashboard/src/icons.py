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

Pixel pass 2026-09-19: 1-bit has no anti-aliasing, so every icon was
re-checked at its real render size (4x NEAREST previews, light + dark) and
snapped to whole pixels instead of float coordinates that PIL rounds
unpredictably:
  * a 2px stroke can't sit symmetrically on a single centre pixel, so
    2px-stroke icons (sun, moon, cloud family, bones) are built around a
    half-pixel centre (an even-width box, cx-n..cx+n-1), and 1px/3px
    details (chip die, "!" bar) around a whole-pixel one;
  * no free-angle diagonals -- only 45 deg and 2:1 slopes, which alias to
    a regular staircase instead of a lumpy one (sun rays, bones, slash);
  * gaps between marks are >=2px wherever the size allows, since a 1px
    gap between two black shapes closes up on the panel (rake-like RJ45
    pins, touching snow crosses);
  * small fixed details (rain drops, snowflakes, lightning bolt) are
    hand-placed pixel sprites -- at 4-8px a primitive's rounding decides
    the shape, a sprite says exactly which pixels are on.
Icons that knock a shape out of a solid one (moon, offline slash, skull
eyes) derive the knock-out colour as `255 - color` when no `bg` argument
exists, so they stay correct in inverted (color=255) calls too.
"""
import math


def _bg(color):
    """The other 1-bit colour -- for knock-outs in icons with no `bg` arg."""
    return 255 - color


def _sprite(draw, x, y, rows, color):
    """Plot a tiny hand-drawn bitmap ('#' = on) with its top-left at (x, y)."""
    for dy, row in enumerate(rows):
        for dx, ch in enumerate(row):
            if ch == "#":
                draw.point((x + dx, y + dy), fill=color)


def calendar(draw, x, y, size=11, color=0):
    """Solid header band instead of a 2px rule under a 2px frame (the two
    merged into one ragged 4-5px bar), rings as exact 2px posts."""
    x, y, size = int(x), int(y), int(size)
    draw.rounded_rectangle((x, y, x + size, y + size), radius=2, outline=color, width=2)
    draw.rectangle((x, y, x + size, y + 3), fill=color)
    for rx in (x + 2, x + size - 3):
        draw.rectangle((rx, y - 2, rx + 1, y), fill=color)


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
    marks read clearer at this scale than more, thinner ones.

    2026-09-19: pins on all four sides (top/bottom only read as a ladder
    or the letter "H"), the die grown to a solid 3x3 square, and all
    coordinates integers so the pins land 3px apart symmetrically about
    the die instead of wherever `size / 2 +- 2` rounded to."""
    x, y, size = int(x), int(y), int(size)
    pad = max(2, round(size / 4))
    x1, y1 = x + size, y + size
    draw.rectangle((x + pad, y + pad, x1 - pad, y1 - pad), outline=color, width=1)
    cx, cy = x + size // 2, y + size // 2
    die = max(1, (size - 2 * pad) // 5)
    draw.rectangle((cx - die, cy - die, cx + die, cy + die), fill=color)
    step = max(2, (size - 2 * pad) // 3)
    for d in (-step, step):
        draw.line((cx + d, y, cx + d, y + pad), fill=color)       # top
        draw.line((cx + d, y1 - pad, cx + d, y1), fill=color)     # bottom
        draw.line((x, cy + d, x + pad, cy + d), fill=color)       # left
        draw.line((x1 - pad, cy + d, x1, cy + d), fill=color)     # right


def ram_stick(draw, x, y, w=16, h=10, color=0):
    """Same fix as `cpu_chip` and for the same reason -- a 2px outline at
    this icon's small actual size read as a heavy filled blob rather than
    a stick. 1px outline, 3 teeth instead of 4, more spacing between.

    2026-09-19: an empty box on 3 legs read as a table; two solid memory
    chips on the board plus 4 edge-connector teeth split by a centre key
    notch read as a DIMM. Teeth snapped to whole columns (the old
    `w * i / 4` put them 3/4/3px apart)."""
    x, y, w, h = int(x), int(y), int(w), int(h)
    draw.rectangle((x, y, x + w, y + h), outline=color, width=1)
    cx = x + w // 2
    gap = max(2, round(w / 7))          # half-width of the centre key/space
    chip_w = max(2, round(w * 0.2))
    chip_top, chip_bot = y + round(h / 3), y + h - round(h / 3)
    draw.rectangle((cx - gap - chip_w + 1, chip_top, cx - gap, chip_bot), fill=color)
    draw.rectangle((cx + gap, chip_top, cx + gap + chip_w - 1, chip_bot), fill=color)
    outer = w // 2 - 2
    for tx in (cx - outer, cx - gap, cx + gap, cx + outer):
        draw.line((tx, y + h, tx, y + h + 3), fill=color)


def wifi(draw, cx, cy, size=10, color=0):
    # 3x3 square dot rather than a 3px ellipse, which PIL rounds to a
    # lopsided blob at that size
    cx, cy = int(cx), int(cy)
    draw.rectangle((cx - 1, cy - 1, cx + 1, cy + 1), fill=color)
    for r in (size // 3 + 2, size * 2 // 3 + 3, size + 4):
        draw.arc((cx - r, cy - r, cx + r, cy + r), start=210, end=330, fill=color, width=2)


def antenna(draw, cx, cy, size=10, color=0):
    """Radio antenna broadcasting a signal -- a mast planted on a small
    foot with a ball at the tip and concentric arcs fanning outward/upward
    from it, used for the PINET hotspot screen in place of the mobile-
    style `wifi` glyph (a visible mast is what reads as "antenna" rather
    than "phone signal bars").

    2026-09-19: mast/foot as exact rectangles (a 2px `line` on a single
    centre pixel lands off to one side), 3px mast so it is centred, ball a
    clean odd-width disc, arcs pulled in so the gap between ball and
    first arc is a solid 2px instead of 1px."""
    cx = int(cx)
    tip_y = round(cy - size * 0.6)
    base_y = round(tip_y + size * 1.7)
    foot = round(size * 0.4)
    draw.rectangle((cx - 1, tip_y, cx + 1, base_y), fill=color)
    draw.rectangle((cx - foot, base_y - 1, cx + foot, base_y), fill=color)
    r = max(2, round(size * 0.15))
    draw.ellipse((cx - r, tip_y - r, cx + r, tip_y + r), fill=color)
    step = max(4, round(size * 0.28))
    for k in (1, 2, 3):
        rad = r + 4 + step * (k - 1)
        bbox = (cx - rad, tip_y - rad, cx + rad, tip_y + rad)
        draw.arc(bbox, start=205, end=335, fill=color, width=2)


def wired(draw, x, y, size=12, color=0):
    """RJ45 plug: a tapered polygon body (wider at the pin end, narrower
    at the clip end, matching a real 8P8C connector), an off-center clip
    tab on top, and 8 thin contact pins along the bottom edge. Restored
    2026-09-06 evening -- had silently reverted to a plain square-with-
    two-feet, which reads as a monitor-on-a-stand rather than a network
    plug (flagged and fixed once already, see [[fixes session log]]).

    2026-09-19: still a tapered plug with contacts along the pin end, but
    solid-filled with the contacts knocked out as windows, and the cable
    leaving the narrow end in place of the clip tab. At its real 13px the
    outline + tab + 8 pins hanging below read as a broom / shower head
    (8 pins 1.6px apart merged into bristles); a solid plug with 4 windows
    on a 3px pitch reads as a connector. 8 are kept where they fit
    (the 24px Ethernet screen). Shoulders are 45 deg, not a shallow
    free-angle taper that aliased into a ragged edge."""
    x, y, size = int(x), int(y), int(size)
    bg = _bg(color)
    cx = x + size // 2
    cable_w = max(3, round(size * 0.24)) | 1
    body_top = y + round(size * 0.38)
    inset = max(2, round(size * 0.16))
    boot_top = body_top - inset
    draw.rectangle((cx - cable_w // 2, y, cx + cable_w // 2, boot_top), fill=color)
    draw.polygon(
        [(x + inset, boot_top), (x + size - inset, boot_top), (x + size, body_top),
         (x + size, y + size), (x, y + size), (x, body_top)],
        fill=color,
    )
    n = 8 if size >= 20 else 4
    pitch = max(2, size // n) if n == 8 else 3
    start = x + (size - (n - 1) * pitch + 1) // 2
    # closed contact windows above a solid 2px rim -- slots open at the
    # bottom edge turned the solid plug back into a comb
    rim = 2
    slot = max(3, round(size * 0.3))
    for i in range(n):
        px = start + i * pitch
        draw.line((px, y + size - rim - slot + 1, px, y + size - rim), fill=bg)


def offline(draw, cx, cy, size=10, color=0):
    """`wifi` struck through. The slash is a 45 deg line kept inside the
    fan (it used to run on down to cy+size+2, into empty space under the
    dot), with a background-coloured halo so the arcs stop 1px short of
    it instead of fusing into one blob where they cross."""
    cx, cy = int(cx), int(cy)
    wifi(draw, cx, cy, size=size, color=color)
    fan_r = size + 4
    mid_y = cy - fan_r // 2
    s = fan_r // 2 + 1
    seg = (cx - s, mid_y - s, cx + s, mid_y + s)
    draw.line(seg, fill=_bg(color), width=5)
    draw.line(seg, fill=color, width=2)


def pirate(draw, cx, cy, size=10, color=0):
    """Skull and crossbones -- shown in the network box in place of the
    normal offline glyph while a WiFi pentest session is active (wlan1 in
    monitor mode, see /usr/local/sbin/wifi-pentest-start): the network box
    already reads "Offline" in that state (there's genuinely no route out
    once wlan1 leaves managed mode), so this just makes the *reason*
    visible at a glance instead of looking like an ordinary connectivity
    drop.

    2026-09-19: solid skull with the eyes knocked out (an outline circle
    with two dots read as a smiley face at size 10), a jaw block with
    teeth gaps, and bones on an exact 2:1 slope with knobbed ends -- a
    plain X under a face read as "close", not "crossbones". Same overall
    extents as before, so the network box / pentest carousel layout is
    unchanged."""
    cx, cy = int(cx), int(cy)
    bg = _bg(color)
    skull_r = round(size * 0.62)
    skull_cy = round(cy - size * 0.22)

    # crossbones first, so the skull sits on top of where they cross
    bone_y = round(cy + size * 0.62)
    # exact 2:1 slope; wide enough that the upper ends clear the jaw
    ay = max(2, round(size * 0.26))
    ax = 2 * ay
    if size < 20:
        bone_w, knob = 2, 1
    else:
        bone_w, knob = max(2, round(size * 0.1)), max(2, round(size * 0.07))
    for sign in (1, -1):
        x0, y0 = cx - ax, bone_y - sign * ay
        x1, y1 = cx + ax, bone_y + sign * ay
        draw.line((x0, y0, x1, y1), fill=color, width=bone_w)
        ln = math.hypot(ax, ay)
        ux, uy = ax / ln, sign * ay / ln        # along the bone
        px, py = -uy, ux                        # across it
        for (ex, ey, out) in ((x0, y0, -1), (x1, y1, 1)):
            # two knuckles per bone end, split across the bone
            for lobe in (-1, 1):
                lx = round(ex + out * ux * knob * 0.5 + lobe * px * knob * 0.9)
                ly = round(ey + out * uy * knob * 0.5 + lobe * py * knob * 0.9)
                draw.ellipse((lx - knob, ly - knob, lx + knob, ly + knob), fill=color)

    # cranium + jaw, with a background halo that parts it from the bones
    halo = 1 if size < 20 else 2
    jaw_w = round(skull_r * 0.62)
    jaw_top = skull_cy + round(skull_r * 0.45)
    jaw_bot = skull_cy + round(skull_r * 1.12)
    draw.ellipse((cx - skull_r - halo, skull_cy - skull_r - halo,
                  cx + skull_r + halo, skull_cy + skull_r + halo), fill=bg)
    draw.rectangle((cx - jaw_w - halo, jaw_top, cx + jaw_w + halo, jaw_bot + halo), fill=bg)
    draw.ellipse((cx - skull_r, skull_cy - skull_r, cx + skull_r, skull_cy + skull_r), fill=color)
    draw.rectangle((cx - jaw_w, jaw_top, cx + jaw_w, jaw_bot), fill=color)

    eye_r = max(1, round(skull_r * 0.28))
    eye_dx = max(eye_r + 1, round(skull_r * 0.42))
    eye_y = skull_cy + round(skull_r * 0.08)
    for ex in (cx - eye_dx, cx + eye_dx):
        draw.ellipse((ex - eye_r, eye_y - eye_r, ex + eye_r, eye_y + eye_r), fill=bg)
    if size >= 20:
        # nose + teeth only where there are enough pixels to draw them
        nose = max(1, round(skull_r * 0.14))
        ny = eye_y + eye_r + nose + 1
        draw.polygon([(cx, ny - nose), (cx - nose, ny + nose), (cx + nose, ny + nose)], fill=bg)
        tooth_gap = max(1, round(size * 0.04))
        for tx in (cx - jaw_w // 2, cx, cx + jaw_w // 2):
            draw.rectangle((tx - tooth_gap // 2, jaw_bot - round(skull_r * 0.3),
                            tx + (tooth_gap - 1) // 2, jaw_bot), fill=bg)
    else:
        draw.point((cx, jaw_bot), fill=bg)


def exclamation(draw, cx, cy, size=9, color=0):
    """Warning "!" glyph -- a rounded bar plus a dot, used for a data source
    that couldn't be fetched (e.g. no network connectivity).

    2026-09-19: bar forced to an odd width (3px at every size the
    dashboard uses) so it centres exactly on cx, and the dot is a square
    of the same width 2px below the bar -- the old float-radius dot came
    out wider than the bar and off-centre."""
    cx, cy = int(cx), int(cy)
    bar_w = max(1, round(size * 0.28)) | 1
    half = bar_w // 2
    bar_top = cy - size
    bar_bottom = cy + round(size * 0.25)
    draw.rounded_rectangle((cx - half, bar_top, cx + half, bar_bottom), radius=half, fill=color)
    dot_top = bar_bottom + 3
    draw.rectangle((cx - half, dot_top, cx + half, dot_top + bar_w - 1), fill=color)


def sun(draw, cx, cy, r=7, color=0):
    """Disc plus 8 rays, built around a half-pixel centre (see module
    docstring) so the 2px rays are symmetric: orthogonal rays are exact
    2x3 bars, diagonal rays exact 2x2 blocks on the 45 deg line -- the old
    `line()` at 45 deg rendered each diagonal ray as a different lumpy
    shape."""
    cx, cy, r = int(cx), int(cy), int(r)
    draw.ellipse((cx - r, cy - r, cx + r - 1, cy + r - 1), fill=color)
    near, far = r + 2, r + 4
    # orthogonal rays (offsets from the half-pixel centre, as pixel indices)
    draw.rectangle((cx - 1, cy - 1 - far, cx, cy - 1 - near), fill=color)
    draw.rectangle((cx - 1, cy + near, cx, cy + far), fill=color)
    draw.rectangle((cx - 1 - far, cy - 1, cx - 1 - near, cy), fill=color)
    draw.rectangle((cx + near, cy - 1, cx + far, cy), fill=color)
    d = round((r + 2.5) / math.sqrt(2) - 0.5)
    for sx in (1, -1):
        for sy in (1, -1):
            px = cx + d if sx > 0 else cx - 2 - d
            py = cy + d if sy > 0 else cy - 2 - d
            draw.rectangle((px, py, px + 1, py + 1), fill=color)


def moon(draw, cx, cy, r=7, color=0, bg=255):
    """Crescent used instead of `sun` for clear/mainly-clear codes at
    night (see `weather_icon`'s `night` flag). A filled disc with a
    second, off-center disc erased in the background color -- same
    fill-based silhouette trick the cloud family uses -- rather than a
    color swap. offset=r*0.55 tuned by trial to stay a clearly separate
    thin crescent instead of a near-total overlap or a barely-clipped
    circle.

    2026-09-19: disc drawn 2px larger (a 15px moon looked undersized next
    to the 24px sun in the same slot) and the eraser offset up-and-right
    as well as sideways, which gives a thick belly and tapered horns
    instead of an even 2-3px sliver that nearly vanished on the panel."""
    cx, cy = int(cx), int(cy)
    R = int(r) + 2
    draw.ellipse((cx - R, cy - R, cx + R - 1, cy + R - 1), fill=color)
    ox, oy = round(R * 0.5), -round(R * 0.3)
    er = R - 1
    draw.ellipse((cx - er + ox, cy - er + oy, cx + er - 1 + ox, cy + er - 1 + oy), fill=bg)


def _cloud_shapes(cx, cy, w, h):
    """(x0, y0, x1, y1) boxes for the ellipses/rounded base making up the
    cloud silhouette -- whole-pixel boxes around a half-pixel centre, so
    the cloud is exactly symmetric in weight and its flat base gives the
    rain/snow/bolt below a straight edge to hang from."""
    cx, cy, w, h = int(cx), int(cy), int(w), int(h)
    left, right = cx - w // 2, cx + w // 2 - 1
    top, bottom = cy - h // 2, cy + h // 2 - 1
    base_h = max(4, round(h * 0.5))
    big = max(4, round(h * 0.86))
    small = max(3, round(h * 0.58))
    big_x = cx - round(w * 0.12) - big // 2
    return [
        (left, bottom - base_h + 1, right, bottom),                       # base
        (big_x, top, big_x + big - 1, top + big - 1),                      # main puff
        (right - small - 1, bottom - small - 2, right - 1, bottom - 2),    # right puff
    ]


def cloud(draw, cx, cy, w=20, h=14, color=0, bg=255):
    """Solid cloud silhouette: fills each overlapping circle (`fill=color`)
    rather than outlining every circle and erasing the seams -- solid
    overlap is harmless with fills, so one pass gives a single clean
    silhouette instead of a "flying saucer" of disjoint thin outlines.
    Restored 2026-09-06 evening after silently reverting to the older
    outline-based approach; `bg` kept for signature compatibility even
    though this version no longer needs it.

    2026-09-19: flat-bottomed (rounded base + two puffs) instead of five
    circles with a round underside, which read as a lumpy blob / tree
    top at 20px."""
    for i, box in enumerate(_cloud_shapes(cx, cy, w, h)):
        if i == 0:
            base_h = box[3] - box[1] + 1
            draw.rounded_rectangle(box, radius=base_h // 2, fill=color)
        else:
            draw.ellipse(box, fill=color)


# Weather particles: hand-placed sprites (see module docstring). Each is
# placed relative to the cloud's half-pixel centre so the set is symmetric.
_RAIN_DROP = [".##", ".##", "##.", "##."]
_SNOWFLAKE = ["#.#.#", ".###.", "#####", ".###.", "#.#.#"]
_BOLT = [
    "..####",
    ".####.",
    ".###..",
    "######",
    "..###.",
    "..##..",
    ".##...",
    ".#....",
]


def rain(draw, cx, cy, color=0):
    cx, cy = int(cx), int(cy)
    cloud(draw, cx, cy, color=color)
    # three slanted 2px drops, the middle one lower so they read as falling
    for dx, dy in ((-8, 9), (-2, 11), (4, 9)):
        _sprite(draw, cx + dx, cy + dy, _RAIN_DROP, color)


def snow(draw, cx, cy, color=0):
    cx, cy = int(cx), int(cy)
    cloud(draw, cx, cy, color=color)
    # 5x5 flakes 2px apart and staggered -- the old 2px-stroke crosses
    # 6px apart touched and read as one dotted bar
    for dx, dy in ((-10, 8), (-3, 11), (4, 8)):
        _sprite(draw, cx + dx, cy + dy, _SNOWFLAKE, color)


def fog(draw, cx, cy, w=20, color=0):
    """Three 2px bars, now staggered (short-long-short, offset left/right)
    -- three equal bars were indistinguishable from a "menu" icon."""
    cx, cy, w = int(cx), int(cy), int(w)
    left, right = cx - w // 2, cx + w // 2 - 1
    short = round(w * 0.3)
    for dy, x0, x1 in ((-4, left, right - short), (1, left, right), (6, left + short, right)):
        draw.rectangle((x0, cy + dy, x1, cy + dy + 1), fill=color)


def thunder(draw, cx, cy, color=0):
    cx, cy = int(cx), int(cy)
    cloud(draw, cx, cy, color=color)
    _sprite(draw, cx - 3, cy + 8, _BOLT, color)


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
        # bg derived from color so an inverted (color=255) call still
        # erases the crescent instead of drawing a full white disc
        moon(draw, cx, cy, color=color, bg=_bg(color))
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


_BOLT_SMALL = ("...##", "..##.", ".##..", "#####", "..##.", ".##..", "##...", "#....")
_BOLT_BIG = ("....###", "...###.", "..###..", ".###...", "#######", "...###.", "..###..",
             ".###...", "###....", "##.....")


_BANG_BIG = ("###",) * 6 + ("...",) + ("###",) * 2   # "!" inside a large pill


def battery(draw, x, y, fill_pct, charging=False, w=34, h=16, color=0, bg=None, alert=False):
    """Phone-style battery (the One UI look): a rounded pill, a small nub, and
    one solid rounded fill proportional to `fill_pct` instead of cells. While
    `charging` a bolt sits in the middle (with `alert`, a low-battery "!"),
    knocked out of the fill and solid over the empty part, so it reads at any
    level. Bounded by
    (x, y, x+w-1, y+h-1), and cleared to `bg` first so the carousel can
    redraw it in place for each animation frame."""
    x, y = int(x), int(y)
    bg = _bg(color) if bg is None else bg
    draw.rectangle((x, y, x + w - 1, y + h - 1), fill=bg)
    body_r = x + w - 4
    draw.rounded_rectangle((x, y, body_r, y + h - 1), radius=max(2, h // 3), outline=color, width=2)
    draw.rectangle((x + w - 2, y + h // 4 + 1, x + w - 1, y + h - 2 - h // 4), fill=color)
    # 1px of air between the outline and the fill, like the phone icon.
    left, right, top, bottom = x + 3, body_r - 3, y + 3, y + h - 4
    fill_r = left + round((right - left + 1) * max(0, min(100, fill_pct)) / 100) - 1
    if fill_r >= left:
        draw.rounded_rectangle((left, top, fill_r, bottom), radius=1, fill=color)
    if charging or alert:
        if alert:
            rows = _BANG_BIG
        else:
            rows = _BOLT_BIG if bottom - top + 1 >= len(_BOLT_BIG) else _BOLT_SMALL
        bx = (left + right + 1 - len(rows[0])) // 2
        by = (top + bottom + 1 - len(rows)) // 2
        for dy, row in enumerate(rows):
            for dx, ch in enumerate(row):
                if ch == "#":
                    px = bx + dx
                    draw.point((px, by + dy), fill=bg if px <= fill_r else color)


POWER_GLYPH_W, POWER_GLYPH_H = 8, 12
_BOLT = ("....###.", "...###..", "..###...", ".###....", "#######.", "######..",
         "...###..", "..###...", ".###....", ".##.....", "##......", "#.......")


def bolt(draw, x, y, color=0):
    """8x12 bolt: charging, in front of the header's small battery."""
    _sprite(draw, int(x), int(y), _BOLT, color)


_PLUG = ("..#..#..", "..#..#..", "..#..#..", ".######.", ".######.", ".######.",
         "..####..", "...##...", "...##...", "...##...", "...##...", "...##...")


def plug(draw, x, y, color=0):
    """8x12 plug: external power, where the bolt goes when charging."""
    _sprite(draw, int(x), int(y), _PLUG, color)


_ALERT = ("..###...",) * 8 + ("........",) * 2 + ("..###...",) * 2


def power_glyph(draw, x, y, state, color=0, low=False):
    """The 8x12 glyph in front of a small battery: bolt while charging, plug on
    external power, "!" when low on battery, else nothing. Returns whether it
    drew one."""
    if state == "charging":
        bolt(draw, x, y, color)
    elif state == "full":
        plug(draw, x, y, color)
    elif low:
        _sprite(draw, int(x), int(y), _ALERT, color)
    else:
        return False
    return True


def spotify(draw, cx, cy, size=9, color=0, bg=255):
    """Spotify mark: a filled disc with three upward-bowing 'sound wave' arcs
    (largest on top), drawn in the negative colour. Pure primitives so it
    scales down cleanly on the 1-bit panel.

    2026-09-19: disc on a half-pixel centre and the three arcs given
    whole-pixel boxes with 2px between them -- at size 8 the float boxes
    rounded the arcs into each other and the mark filled in solid."""
    cx, cy = int(cx), int(cy)
    r = int(size)
    draw.ellipse((cx - r, cy - r, cx + r - 1, cy + r - 1), fill=color)
    # three arcs 4px apart (2px stroke + 2px gap), largest on top
    top = -round(r * 0.45)
    for dy, hw in ((0, round(r * 0.72)), (4, round(r * 0.55)), (8, round(r * 0.36))):
        ah = round(hw * 0.8)
        box = (cx - hw, cy + top + dy, cx + hw - 1, cy + top + dy + 2 * ah - 1)
        draw.arc(box, start=215, end=325, fill=bg, width=2)
