---
tags: [project, raspberry-pi, e-ink, module]
---

# `src/icons.py`

Every icon on the panel is drawn by hand with PIL `ImageDraw` primitives —
no image assets, so nothing to ship/scale/dither for a 1-bit display. Every
function takes `(draw, x_or_cx, y_or_cy, ..., color=0)` and draws within a
predictable bounding box so [[dashboard.py]]'s layout math (`draw_stat_box`
offsets) doesn't need to know icon internals.

## Restyle (this session)

Originally every icon was a **thin 1px outline**. First pass: restyled to
**bold, filled glyphs** (thicker strokes, solid fills) to match a reference
flat-icon sheet the user provided (`~/Pictures/Screenshots/`). Second pass
(same session, follow-up feedback): the user pointed out that CPU/RAM
looked generic and `wired` specifically read as a *computer monitor on a
stand*, not an ethernet plug — bold strokes alone weren't enough, three
icons needed genuinely different shapes/detail, not just thicker lines.
Both passes kept every function signature identical — no caller changes
needed. QA'd with `icon_gallery.py` (renders every icon in a labeled grid,
see [[test and preview scripts]]) and by re-rendering the live dashboard in
light/dark mode plus both status/offline/QR screens.

## Icons actually used by the dashboard

- **`cpu_chip(draw, x, y, size=14, color=0)`** — processor package: outer
  housing outline, a smaller **inner die square** nested inside for detail,
  and pins on **all four edges** (previously only top/bottom) — reads as an
  actual chip rather than a box with teeth on two sides. Outer outline is
  `width=1` (thinned from `2` in a later pass, see below).
- **`ram_stick(draw, x, y, w=16, h=10, color=0)`** — memory module: outline,
  **3 small outlined "chips"** across the face for texture, and a row of
  bottom contact teeth with a **center notch removed** — mirrors the
  asymmetric notch real RAM sticks have (so it doesn't insert backwards),
  and visually distinguishes it from `cpu_chip`. Outer outline is `width=1`
  (thinned from `2`, see below).

### Follow-up (2026-09-06): un-bolded CPU/RAM outlines

The icon restyle's "bold, filled glyphs" treatment was applied uniformly,
including to `cpu_chip`/`ram_stick` — but those two only ever appear inside
`draw_mini_stat` (see [[dashboard.py]]), the deliberately low-emphasis
CPU/RAM strip, sitting right above the bold "hero" weather/network icons.
Bold outlines on the demoted tile fought the strip's own reason for
existing (lower visual weight than the hero boxes). Fix: outer-outline
`width` dropped from `2` to `1` on both (inner die/chip detail and pins
untouched — those were already thin). Verified via `icon_gallery.py` and a
full dashboard re-render, deployed and restarted the live service.
**Modernization pass (2026-09-06 evening)**: every icon in this file now
uses a consistent `width=2` stroke (was a mix of PIL's default `width=1`
and `2`/`3`, which read as mismatched weight icon-to-icon) and
`rounded_rectangle` for `calendar`/`cpu_chip`/`ram_stick`, taking cues
from a reference icon set the user provided (rounded, evenly-weighted)
without copying its literal hairline stroke width — a 1px line would
alias to near-invisible on this 1-bit panel at this size, so "modern"
here means adopting the roundness/consistency, adapted bolder for the
actual medium. Same pass **discovered and fixed a second silent
regression** beyond the `moon()`/`night` one already documented in
[[fixes session log]] fix #12: `cloud()` had reverted to an older
outline-per-circle approach (thin, seamed) instead of the solid
`fill=color` version described below, and `wired()` had reverted all the
way back to the plain square-with-two-feet design this same file
explicitly says was rejected as reading like "a monitor on a stand." Both
restored to spec; `wired()`'s taper proportions were also tuned (less
dramatic taper, tab pulled 1px clear of the body) after the literal
restoration still read ambiguous at small icon sizes in a rendered check.

- **`wifi(draw, cx, cy, size=10, color=0)`** — filled center dot + 3
  concentric arcs (`width=3`, 210°→330°, i.e. opening downward) forming the
  classic "wifi signal" glyph.
- **`antenna(draw, cx, cy, size=10, color=0)`** (added 2026-09-06 evening)
  — vertical mast on a small foot, a filled dot at the tip, and 3
  concentric arcs (200°→340°) fanning up/outward from the tip. Reuses
  `wifi()`'s arc-drawing convention for visual consistency with the rest
  of the icon set, but the visible mast is what reads as "broadcast
  antenna" rather than "phone signal bars". Used only for
  `render_hotspot_screen`'s active-hotspot icon (see [[dashboard.py]]) —
  the main status screen's Wi-Fi-client icon legitimately means
  Wi-Fi-as-client and stayed on `wifi()`.
- **`wired(draw, x, y, size=12, color=0)`** — **RJ45 plug**: a body with an
  **off-center clip tab on top** and **8 thin contact pins along the
  bottom edge**. Replaced the original design (a square + two wide feet
  centered at the bottom), which — correctly flagged by the user — read as
  a monitor-on-a-stand rather than a network plug; the off-center single
  tab and thin evenly-spaced pins are the deliberate visual differentiators
  from that silhouette.
  - **Follow-up (2026-09-06)**: body changed from a plain rectangle to a
    **tapered polygon** (wider at the pin end, narrower at the clip end,
    matching a real 8P8C connector's shape) and pin count doubled from 4
    to 8 (matching a real RJ45's 8 contacts), per user feedback that the
    icon needed more detail. Also, at its call site in `render_qr_screen`
    (the "Connected via Ethernet" fallback screen — see [[dashboard.py]]),
    `size` was doubled from `12` to `24` specifically for prominence,
    since that's the one screen that explicitly tells the user they're on
    Ethernet; its other call site (the compact NETWORK hero-box icon on
    the main status screen) was left at its existing small size — the
    8-pin detail mostly blurs together at that scale regardless (same
    limitation the old 4-pin version had), and that box wasn't the one
    flagged. QA'd via `icon_gallery.py`, `offline_test.py`
    (`preview_qr_wired.png`, light + dark), and an ad-hoc render of the
    main status screen's NETWORK hero box with a synthetic wired `net`
    dict (not a permanent script — [[test and preview scripts]] doesn't
    have a wired-hero-box preview built in).
- **`offline(draw, cx, cy, size=10, color=0)`** — `wifi()` plus a bold
  diagonal strike-through line (`width=3`), the standard "no signal"
  convention (à la Font Awesome `wifi-slash`).
- **`exclamation(draw, cx, cy, size=9, color=0)`** — warning glyph (rounded
  bar + dot) shown when a data source couldn't be fetched: weather tile
  when there's no network, network tile when fully offline.
- **`sun/cloud/rain/snow/fog/thunder`** — weather icons, dispatched by
  `weather_icon(draw, code, cx, cy, color=0)` via `WEATHER_ICON_BY_CODE`
  (Open-Meteo WMO code → drawing function).
  - `sun` — filled circle + 8 bold rays (`width=3`).
  - `moon(draw, cx, cy, r=7, color=0)` — crescent used instead of `sun` for
    clear/mainly-clear codes when it's night (`weather_icon(..., night=True)`,
    driven by `dashboard.py`'s `dark_mode`): a filled disc with a second,
    off-center disc erased (drawn in the canvas's white background) rather
    than a color swap — same fill-based silhouette trick the cloud family
    uses. Tuned by trial (`offset = r * 0.55`) to stay a clearly separate
    thin crescent rather than either a near-total overlap (unnoticeable) or
    barely-clipped circle (reads as a mistake, not a moon) — verified at the
    dashboard's actual in-panel size, not just enlarged.
  - `_cloud_shapes(cx, cy, w, h)` returns 5 `(x, y, rx, ry)` circles whose
    union forms a cloud silhouette. `cloud()` now just **fills** each one
    (`fill=color`) — solid overlap is harmless with fills, unlike the old
    approach (outline every circle, then paint a smaller inset circle in
    the background color to erase the seams where outlines crossed) which
    only ever produced a thin-outline cloud, not a solid one.
  - `rain`/`snow`/`fog`/`thunder` = `cloud()` (or, for `fog`, just 3 bold
    horizontal lines) plus their respective bold embellishment
    (raindrops/snowflakes/lightning bolt), all bumped to `width=2`–`3`.

## Icons defined but not currently wired into any screen

Still restyled for consistency (per explicit request), but nothing in
[[dashboard.py]] currently calls these:

- **`calendar(draw, x, y, size=11, color=0)`** — thick outline + filled
  header bar + two filled "hanger tab" nubs on top.
- **`clock(draw, cx, cy, r=9, color=0)`** — thick circle outline + bold
  hour/minute hands + filled center dot.

## Decorative, out of restyle scope

- **`seigaiha(draw, x, y, w, h, ...)`** — traditional Japanese overlapping-
  fan wave pattern, a background/watermark texture generator. Not an
  icon-with-meaning like the others, so left untouched by the icon restyle.
  Exercised standalone by `wave_test.py` (see [[test and preview scripts]]).

## QA tool

`icon_gallery.py` renders every actively-used icon in a labeled 4-column
grid (`icon_gallery.png`) — the fastest way to eyeball every icon at once
after any change here, before bothering with a full dashboard re-render.


## Update 2026-09-17 -- `spotify()` glyph

`spotify(draw, cx, cy, size=9, color=0, bg=255)` -- a filled disc with three
upward-bowing "sound wave" arcs (largest on top) in the negative colour, all
pure primitives so it scales down on the 1-bit panel. Used by [[dashboard.py]]'s
new Spotify panel on the hotspot screen (see [[fixes session log]] entry 41). At
~8px it reads mostly as a dark disc; it sits next to the "Spotify" label so it's
unambiguous.
