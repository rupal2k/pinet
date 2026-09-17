---
tags: [project, raspberry-pi, e-ink, log]
---

# Fixes session log

Chronological record of every issue found and fixed on the
[[Overview|pi-eink-dashboard]] project in this session, each with root
cause, the fix, and how it was verified.

## 1. Network icon stuck on Wi-Fi when connected via Ethernet

**Symptom**: the status screen's NETWORK tile kept showing the Wi-Fi icon
and "WiFi" even when the Pi was actually connected over Ethernet.

**Root cause**: `get_network_status()` in [[dashboard.py]] decided
Wi-Fi-vs-wired purely from `iwgetid -r` — i.e. whether `wlan0` was
*associated* to an access point — not from which interface was actually
carrying traffic. NetworkManager doesn't drop the Wi-Fi association just
because Ethernet has a better route, so `wlan0` stayed associated (and
`iwgetid` kept returning the SSID) even while all real traffic went out
`eth0`.

**Fix**: added `get_active_interface(ip)` — matches the local IP actually
used for outbound traffic (from the existing `get_ip_address()` socket
trick) to its owning interface via `psutil.net_if_addrs()`. New helper
`_is_wifi(iface, ssid)` decides Wi-Fi-vs-wired from that interface's name
(`wl*`/`ww*`), falling back to the old SSID check only if the interface
can't be resolved. `get_network_fingerprint()` (used to detect network
changes and refresh early) updated the same way.

**Verified**: live on the Pi, before/after plugging in Ethernet —
`get_network_status()` correctly flipped `is_wifi: True → False`, and the
journal logged the exact transition:
```
Network changed ('192.168.29.151', True) -> ('192.168.29.166', False), refreshing early
```
Confirmed the new Ethernet IP (`192.168.29.166`) was independently reachable
over SSH and SFTP.

## 2. QR/Wi-Fi carousel screen also stuck on Wi-Fi over Ethernet

**Symptom**: same underlying issue, different screen — even after fix #1,
the second carousel screen still showed the Wi-Fi QR code (or "no Wi-Fi"
message) instead of anything Ethernet-aware while connected via Ethernet.

**Root cause**: `get_wifi_credentials()` had the identical bug —
decided purely from `get_wifi_ssid()`, so it kept returning the SSID/QR
whenever Wi-Fi stayed associated in the background.

**Fix**: `get_wifi_credentials()` now also checks `_is_wifi()` (the same
helper from fix #1) and returns `(None, None)` while not actually on
Wi-Fi. `render_qr_screen()` gained a new `net` parameter and a new branch:
when there's no SSID but `net["ip"]` is set, it shows "Connected via
Ethernet" + the IP (previously this case fell through to a generic
"No Wi-Fi connection (on Ethernet or offline)" message that didn't
distinguish wired from truly offline). Updated call sites:
`main()`'s QR-screen branch, and the two test scripts that called
`render_qr_screen()` positionally (`offline_test.py`, `preview_render.py`
— see [[test and preview scripts]]), which would otherwise have broken on
the new signature.

**Verified**: `get_wifi_credentials()` confirmed returning `(None, None)`
live while on Ethernet; rendered `preview_qr_wired.png` via
`offline_test.py` and visually confirmed "Connected via Ethernet /
192.168.29.166"; the live service's journal showed it landing in the new
branch on its own during a real carousel cycle.

## 3. Clock time didn't match the configured location

**Symptom**: displayed time was off relative to Guwahati (the weather
location resolved from config/IP-geolocation).

**Root cause**: the Pi's system timezone was `Europe/London` (BST), while
weather/location resolve to Guwahati, India (IST, UTC+5:30) — see
[[config.ini]].

**Fix**: `sudo timedatectl set-timezone Asia/Kolkata` on the Pi.

**Verified**: `date` on the Pi now shows IST; re-rendered dashboard preview
shows a time consistent with IST.

## 4. Switch clock to 12-hour format (+ overflow it caused)

**Ask**: 12-hour clock instead of 24-hour.

**Fix**: `strftime` format changed from `%H:%M:%S` to `%-I:%M:%S %p` in
`render()`.

**Regression this surfaced**: the longer string (with `AM`/`PM`) no longer
fit the fixed 20pt header font on the 250px-wide panel — both the leading
and trailing characters got clipped (centered text wider than the canvas
clips symmetrically on both sides).

**Fix for that**: replaced the fixed-size `FONT_HEADER` with the existing
`fit_text()` helper (already used for the stat-box text), shrinking from
18pt down to a 13pt floor as needed — settles at 17pt in practice, full
text intact, no truncation.

**Verified**: measured text width at several font sizes directly on the Pi
(DejaVu Sans Bold) to confirm 17pt fits comfortably (234px inside a 242px
budget); re-rendered and visually confirmed "Sun 06 Sep    4:38:06 AM"
fully on-screen.

## 5. Icon restyle — thin outlines → bold filled glyphs

**Ask**: restyle icons to match a bold/filled flat-icon reference sheet
(`~/Pictures/Screenshots/Screenshot_2026-09-06_04-42-30.png`). Scope
clarified as *all* icons (not just network), and as a **bold simplified
reinterpretation** rather than literal detail (the reference icons are far
more detailed than legible at the panel's ~10–20px icon size, 1-bit color).

**Fix**: full rewrite of [[icons.py]] — thicker outlines (`width=2`–`3`
instead of 1), filled pin/hanger/prong details instead of hairline strokes,
and the cloud-family icons switched from a thin-outline-with-seam-erase
trick to genuinely solid filled silhouettes. Every function signature kept
identical, so [[dashboard.py]]'s layout offsets didn't need to change.

**Verified**: rendered `icon_gallery.py`'s full labeled grid and eyeballed
every icon; re-rendered the live dashboard in light mode, dark mode, the
offline/no-network state, and the Ethernet-QR fallback screen — all clean,
no layout regressions. Deployed and restarted the live service.

## 6. Follow-up: CPU/RAM/wired needed distinct shapes, not just bold

**Ask**: after fix #5, user pointed out CPU and RAM still looked generic
and that `wired` specifically **looked like a computer** (monitor on a
stand) — asked for real style differences with added detail, not just
bolder strokes.

**Root cause**: fix #5 made every icon thicker/filled but largely kept the
original *shapes*. `wired`'s shape in particular (a square + two wide feet
centered at the bottom) is the classic monitor-and-stand silhouette
regardless of stroke weight.

**Fix**: reshaped three icons in [[icons.py]] specifically:
- `cpu_chip` — added a nested inner die square, and pins on all four edges
  instead of only top/bottom.
- `ram_stick` — added 3 small outlined "chips" across the face, and a
  center notch removed from the bottom contact row (mirroring the
  asymmetric notch real RAM modules have).
- `wired` — completely reshaped into an RJ45 plug: body with an off-center
  clip tab on top and 4 thin evenly-spaced contact pins along the bottom,
  replacing the two-wide-feet design that read as a monitor stand.

**Verified**: re-rendered `icon_gallery.py` and the full dashboard preview
at actual in-panel size (not just the gallery's enlarged cells) — all three
read distinctly and cleanly, no clipping. Deployed and restarted the live
service.

## 7. Layout redesign: real hierarchy instead of a uniform 4-box grid

**Ask**: "redesign the UI ... for a final touch," pointed at skills from the
`anthropics/claude-code` repo. Investigated that repo — it's mostly
Claude-Code-tooling plugins (code review, commit workflows, plugin dev,
etc.); the one visually-relevant one, `frontend-design`, is written for
web/CSS UI (palettes, hero sections, motion) and doesn't map literally onto
a 1-bit 250×122px PIL-drawn panel. Applied its actually-transferable
principle instead: don't give everything identical visual weight just
because it's easy to template.

**Root cause (of the "generic" feel, not a bug)**: the status screen was a
uniform 2×2 grid of four identically-sized, identically-treated boxes
(CPU/RAM/weather/network) — visual weight didn't reflect actual information
priority. CPU/RAM are diagnostic figures; weather/network are what's
actually worth a glance from across the room.

**Fix**: restructured `render()` in [[dashboard.py]] into two tiers — a new
`draw_mini_stat()` compact single-line strip for CPU+RAM (low emphasis), and
`draw_stat_box()` reworked into a "hero" tile (large value text, up to
26pt) used only for weather and network, each now getting roughly 4× the
vertical space CPU/RAM get. Caught and fixed a side effect along the way:
the weather box's no-data fallback used to show a literal "!" as its value
right next to the (also now much bigger) exclamation icon — fine as a
small pairing before, but blown up to hero size it read as two stacked
exclamation marks. Changed the fallback value to "`--`" instead.

**Verified**: re-rendered the full dashboard preview in light mode, dark
mode, and the offline/no-data state after the "`--`" fix — all four
combinations clean, correct hierarchy, no clipping. Deployed and restarted
the live service. The QR/carousel screen was left unchanged — it already
has distinct, purpose-built layouts per case, not the uniform-grid issue.

## 8. Follow-up session (2026-09-06): housekeeping + UI polish pass

**Housekeeping**: checked the two items flagged as "not yet cleaned up" in
[[Overview]] — the stale nested duplicate checkout and the broken
`test_render.py` were both already absent from the Pi (cleaned up outside
any recorded session). Raised `config.ini`'s `refresh_minutes`/
`carousel_minutes` from `1` back to the code default `5` (was left fast from
active testing) and restarted the service — confirmed via the journal that
carousel phases are now minutes apart instead of ~65s apart.

**UI review**: read the live source directly off the Pi (not just the vault,
since it had already drifted once) and the current `preview_*.png` renders.
Four small, low-risk polish changes, each verified with a fresh
`preview_render.py`/`offline_test.py` run before deploying:

- **Header layout** — see [[dashboard.py]]: date left-aligned, clock
  right-aligned, replacing a single centered string with a hand-tuned
  triple-space gap. Uses the full 250px width instead of wasting both edges.
- **Degree signs** — weather and CPU temperatures now show `26°C`/`45°C`
  instead of a bare `26C`/`45C`. DejaVu Sans/Bold both have the glyph, no
  rendering issues at any size in use.
- **Night-aware weather icon** — see [[icons.py]]: new `moon()` icon,
  swapped in for `sun` on clear/mainly-clear codes while `dark_mode` is
  active, via `weather_icon(..., night=dark_mode)`. Iterated on the
  crescent's proportions using a real in-panel-size render
  (`dashboard.render()` with a forced clear-sky/dark-mode weather dict) after
  a first attempt (`offset = r * 0.55` tried in isolation at enlarged scale)
  looked ambiguous — confirmed distinct from `sun` at actual size before
  keeping it.
- **Hero-box breathing room** — `draw_stat_box`'s icon-to-text gap widened
  slightly (`text_x` from `x+32` to `x+34`, weather icon shifted 2px left) —
  the weather cloud icon sat almost flush against the temperature digits.

All four verified in light mode, dark mode, and the offline state; deployed
and restarted the live service; journal showed no errors after restart.

## 10. Follow-up session (2026-09-06, continued): reboot bug, location staleness, 3rd carousel screen, Wi-Fi power-save

**Symptom**: after a Pi reboot, the panel showed only the QR screen for
several minutes, never the status dashboard.

**Root cause**: `main()`'s `phase = int(time.time() // (carousel_minutes*60)) % 2`
was anchored to absolute wall-clock time, not to when the service started.
Every restart was effectively a coin flip for which screen showed first —
confirmed in the journal: a restart at `06:19:06` computed `phase=1 (qr)`
immediately, then correctly flipped to `phase=0 (status)` only at `06:24:28`,
5+ minutes later. This was always possible but easy to miss while
`carousel_minutes=1` (from active testing); it became a multi-minute stall
once that was raised to `5` earlier this session (see fix #8).

**Fix**: `start_time = time.monotonic()` captured once before the loop;
`phase` computed from `time.monotonic() - start_time`, which is always `0`
at `elapsed=0` — the status screen is now guaranteed first after every
restart. Used `monotonic()` rather than `time.time()` for the anchor too: a
Pi with no RTC can have a wrong wall clock for the first several seconds
after boot (then jump once NTP syncs), which would reintroduce a version of
the same class of bug; `monotonic()` only counts forward from process start
and is immune to wall-clock corrections. Verified by simulating the phase
formula standalone across a range of elapsed times (confirmed `elapsed=0`
always yields `phase=0`, and the alternation cadence is unchanged) before
deploying.

**Second bug found while investigating**: `get_location(cfg)` (weather
lat/lon/city) is resolved **once** at startup and was never refreshed. IP
geolocation (used whenever `latitude`/`longitude` are blank in config)
geolocates the *requesting* public IP — so switching the Pi to a different
network (confirmed live this session: home Wi-Fi/Ethernet → a phone hotspot,
after the home network became unreachable mid-session) can change the
resolved city. The network fields (IP/SSID/wired) already update correctly
every render — only weather location didn't. This had gone unnoticed because
every network change so far happened to coincide with a manual service
restart (which always re-resolves location fresh at startup), never with the
service staying up across a live network change.

**Fix**: `has_fixed_location` computed once at startup (`True` only if both
`latitude` and `longitude` are explicitly set). In the wait loop's
network-change branch, if not `has_fixed_location`, re-call `get_location(cfg)`
and log the result before breaking early. A fixed configured location is
never re-resolved (nothing about it depends on the network).

**Third addition**: a third carousel screen — a bug mascot, per explicit
request, ASCII art pasted directly in chat. New `render_ascii_art_screen()`:
renders the art as **pixel art, not literal text** — each character of the
grid becomes one bitmap pixel (non-space = black), then the whole grid is
scaled up with nearest-neighbor to fill the panel. Text at 250px width would
be illegible at the art's actual line length (~68 chars); the character grid
as a silhouette reads as a clean bold shape instead (verified: renders as a
recognizable domed/shell silhouette at real panel resolution, both light and
dark mode). `phase` calculation changed from `% 2` to `% 3`
(`0`=status, `1`=qr, `2`=ascii). `carousel_minutes`/`refresh_minutes` both
set to `3` per explicit request (3 min per screen, 9 min total cycle) — see
[[config.ini]].

**Wi-Fi power-save**: while investigating the mid-session network drop,
checked signal quality (`/sbin/iwconfig wlan0`, tools exist at `/sbin` but
aren't on the default non-interactive SSH `PATH`) — signal itself was fine
(~-51dBm on the phone hotspot at close range; home-network `SPECTRE24`
signal not independently checked), but `Power Management: on`. For an
always-plugged-in device doing periodic network polling, Wi-Fi power-save
adds latency/missed-packet risk for no benefit. Disabled via
`nmcli connection modify <uuid> 802-11-wireless.powersave 2` on **both**
saved Wi-Fi profiles (`SPECTRE24` and the phone hotspot), then
`nmcli connection up <uuid>` to apply it to the already-active connection
(a profile edit alone doesn't affect a connection already up).

## 11. UX audit (2026-09-06): guest-facing screens made friendlier

Asked to review the project as a UI/UX designer and make it more
user-friendly. Rendered every screen state (status/QR/hotspot/DOOM-logo
footer, light+dark, every network state) via `preview_render.py`/
`offline_test.py`/ad-hoc snippets and reviewed them as a batch. Found 7
issues, presented all 7 with a recommendation, and implemented the 4 the
user picked as genuine usability problems (the other 3 — no visual
warning for hot/loaded CPU, no carousel phase indicator, DOOM-logo screen
mixing an easter egg with real power-health data — were left as
subjective/optional, not implemented):

1. **Guest-facing sudoers error replaced.** `render_qr_screen`'s
   no-password fallback said "Password unavailable (check sudoers
   setup)" — a raw dev-facing message with no actionable meaning to an
   actual guest (and this exact failure mode really happened earlier
   this session — see [[power and undervoltage]]'s sudoers section). Now
   reads "Ask your host for the Wi-Fi password". The technical reason
   still goes to the log: `get_wifi_credentials()` previously only
   logged on a Python exception, silently swallowing the more common
   case (sudo denies with a non-zero exit but no exception) — added an
   explicit `returncode != 0` check that logs `stderr`.
2. **QR screen gained a scan hint.** The QR square only ever used its own
   footprint, leaving ~78px unused on the left at this panel's 250×122
   landscape size. Left margin now reads "Scan to join" / "Wi-Fi" as a
   natural two-line phrase.
   - **Follow-up (same session)**: first pass also added a plaintext
     SSID/password fallback in the right margin, and the hint was an
     all-caps "SCAN / TO JOIN / WI-FI" stacked one-word-per-line. Per
     user feedback, the plaintext fallback was removed entirely (QR-only
     is the intended UX here) and the hint reworded to the natural,
     properly-cased two-line phrase above — the all-caps single-word
     stack read as unprofessional.
3. **Hotspot phase restored to the carousel.** It had been dropped to
   `% 3` (`status, qr, ascii`) pending the under-voltage investigation
   (see [[power and undervoltage]]) — that investigation has no fix in
   sight, and there's no reason to keep a guest-facing feature hidden
   indefinitely for it. Back to `% 4` with `hotspot` restored as the
   last phase, matching the original ordering the removal comment
   pointed back to. Full cycle time is now `4 × carousel_minutes` (12min
   at the current `carousel_minutes=3`) instead of 9.
4. **Hotspot screen gained a join QR code.** Previously showed the SSID
   and a live device count but gave a guest no way to actually join
   without asking someone for the password — inconsistent with the home
   Wi-Fi screen's QR affordance. New `get_hotspot_passphrase()` reads
   `wpa_passphrase=` straight from `/etc/hostapd/hostapd.conf` (world-
   readable, no sudo needed) so the shown password always matches what
   hostapd is actually broadcasting; `get_hotspot_status()`'s returned
   dict gained a `password` key. `render_hotspot_screen` draws a small
   (68px) `WIFI:T:WPA;...` QR top-right with a "scan to join" caption
   when a password is available. Caught and fixed one layout bug during
   QA: the "devices connected" label wasn't width-constrained and
   visually ran into the new QR's left edge — fixed by bounding it with
   `fit_text` the same way the device-count number already was.

**Not implemented, flagged as pre-existing and out of scope for this
pass**: dark mode's `ImageOps.invert` applies globally, including to the
pasted QR image itself — meaning a dark-mode QR renders as white modules
on black. Most modern scanners handle inverted QR fine, but not
universally; this predates today's changes (QR screens already inverted
in dark mode before) and wasn't one of the 4 items picked, so left alone.

QA'd via ad-hoc renders of every affected state (short/long/no-password
QR in light+dark, hotspot with/without a QR in light+dark, 1 vs 2+
devices for the singular/plural label) before touching the live service;
one bug (the label overlap above) was caught and fixed during this QA
pass, not after deploying.

## Tooling note

`claude-flow` (Ruflo) MCP tools were invoked for `guidance_brain` at the
start of the icon-restyle/documentation work per project convention, but
the MCP server later disconnected entirely mid-session (all its tools
became unavailable, including `memory_store`) — so no Ruflo memory receipt
exists for this session; this vault page is the durable record instead.

## 12. Follow-up session (2026-09-06 evening): PINET portal rebuilt, concurrent-session collision, DOOM screen redesign, Roboto rollout

A separate session from #8–#11 above. Picked up after [[pinet-captive-portal]]
had been fully removed later the same day it was built (see that note's
own history) — but the removal was never written back to this session's
starting auto-memory, so the session began by treating the portal as
still-live, found it gone, and had to reconstruct what happened from this
vault plus the user before doing anything else. **Lesson applied going
forward: update auto-memory in the same session a documented feature is
removed or changed, don't rely on the vault alone** — already written
into [[pinet-captive-portal]] itself.

1. **PINET hotspot + portal rebuilt, then the rebuild's scope changed
   mid-flight.** `hostapd`/`dnsmasq`/`pinet-ap-network` were re-enabled
   (configs were still on disk, just disabled). The portal was rebuilt
   bundling internet-bridge toggle + anonymous chat + up to 1GB file
   sharing per the day's earlier request — but while doing this over SSH,
   a **second, independent, more complete implementation
   (`pinet-board.service`) appeared on the Pi mid-session**, built by
   what looks like a concurrent session (a live local desktop login had
   been active on the Pi itself since before this session started). Full
   detail, including the port-80 collision this caused and how it was
   resolved (scope narrowed: `pinet-portal` keeps only the bridge toggle
   on its own port 8090; `pinet-board` — sudo-free, SQLite-backed, real
   `TMPDIR` fix for large uploads — keeps the chat/file feature on port
   80), is in [[pinet-captive-portal]]. **Not repeated here in full — that
   note is now the authoritative record for this feature**, including a
   standing warning to check `systemctl status pinet-board` and `who`/`w`
   before assuming sole ownership of the Pi next time this area is
   touched.
2. **`pinet-board`'s UI gained a sticky shortcut bar.** Its board page
   stacked "post a message" → "messages" → "share a file" → "files" as
   one long scroll with no way to jump between sections. Added a small
   sticky top bar (`#messages-section`/`#files-section` anchor links with
   live counts) so shared files don't require scrolling past the whole
   message history to find. Template-only change (`board.html`), no
   backend/`app.py` edits, applied cautiously since this file is owned by
   the other session's build — verified via file mtimes and a diff
   against a pre-change backup (`/tmp/board.html.bak-*` on the Pi) that
   nothing else had touched it before or after.
3. **DOOM-logo screen (`render_image_screen`) gained a disk-space
   readout, then had its layout revised twice on follow-up feedback.**
   First pass added `get_disk_usage()` (`psutil.disk_usage("/")`) sharing
   one footer row with the existing voltage/throttle text (left/right
   split). Per feedback, moved to a single row **above** the logo instead
   of below it. Per further feedback, split into two separate rows —
   voltage/throttle status as a header above the logo, disk space as its
   own footer below it — since sharing one line made one reading feel
   subordinate to the other. Final layout has **no rule lines anywhere on
   this screen** (an explicit, repeated instruction) — separation is
   whitespace-only on both sides of the logo, and the logo's own image
   area is untouched by any of this (same size it's always been; only the
   header/footer strips around it changed). QA'd with rendered previews
   across every combination (normal / low-voltage / throttled+low-disk /
   all-`None`, light+dark) before deploying each revision, specifically
   checking the worst-case text width ("LOW VOLTAGE" + longest disk
   string) for overlap — none found at any revision.
4. **Switched the whole project's font from DejaVu Sans to Roboto.**
   `apt install fonts-roboto` (already-available Debian package, no
   manual font wrangling), `FONT_REGULAR_PATH`/`FONT_BOLD_PATH` repointed
   to `/usr/share/fonts/truetype/roboto/unhinted/RobotoTTF/`. Low-risk
   because almost every text draw in [[dashboard.py]] already goes
   through `fit_text()` (dynamic shrink-to-fit) rather than assuming
   DejaVu's exact glyph metrics — verified anyway with full-carousel
   preview renders (all 4 phases, light+dark) after the swap, no
   overflow/truncation found. Matched by the same font on both PINET web
   UIs (see [[pinet-captive-portal]]'s Roboto section) for one consistent
   typeface across the e-ink panel and both web portals — necessary to
   self-host on the web side specifically, since PINET clients have no
   internet by default and a Google Fonts CDN link would silently fail
   to load.

QA'd throughout with `preview_render.py`-style ad-hoc scripts (rendered
to PNG on the Pi, pulled back over `scp`, visually reviewed) rather than
only checking the live panel, same discipline as fix #11. Pi stability
re-checked after all changes: load average normal, no failed systemd
units, no error-level journal entries, all six services
(`pi-eink-dashboard`, `hostapd`, `dnsmasq`, `pinet-ap-network`,
`pinet-portal`, `pinet-board`) active. The pre-existing under-voltage
condition (`vcgencmd get_throttled` → `0x50005`, see
[[power and undervoltage]]) is unrelated to this session's changes and
remains unresolved.

5. **Disk-space footer expanded to used/total/free, not just free.**
   `get_disk_usage()` now returns `(free_gb, used_gb, total_gb)` (was
   `(free_gb, percent)`) from the same `psutil.disk_usage("/")` call.
   Footer text became `"{used}/{total}GB used · {free}GB free"`, and —
   unlike the plain free-space version — this is routed through the
   codebase's existing `fit_text()` shrink-to-fit helper rather than a
   fixed 13pt draw, since the longer string has less width margin to
   spare. Verified via preview it still renders at full 13pt (didn't
   actually need to shrink) even in the worst-case digit-width case
   (double-digit GB values on both sides of the split).
6. **Hotspot screen's icon changed from the mobile-style Wi-Fi glyph to
   a dedicated antenna icon.** New `icons.antenna()`: a vertical mast on
   a small foot, a dot at the tip, concentric arcs fanning up from it --
   reuses the same arc-drawing convention as `icons.wifi()` for visual
   consistency with the rest of the icon set, but the visible mast is
   what reads as "broadcast antenna" rather than "phone signal bars".
   Only swapped on `render_hotspot_screen`'s active-hotspot icon (line
   ~581) -- the main status screen's own Wi-Fi-client icon (`render()`,
   line ~491) legitimately means Wi-Fi-as-client and was left alone, and
   `icons.offline()` (still built from `wifi()` internally, crossed out)
   also left alone since "no signal" reads fine with either glyph and
   wasn't part of the request.
7. **Self-inflicted regression, caught and fixed: pushing icons.py wiped
   an uncommitted, undocumented-until-now feature.** Adding `antenna()`
   was done by editing the *local* checkout's `icons.py` and `scp`-ing it
   to the Pi -- but unlike `dashboard.py` (which had been freshly pulled
   from the Pi earlier the same session before any local edits), `icons.py`
   was never re-pulled first. The Pi's live copy had a `moon()` icon and
   a `night=` parameter on `weather_icon()` (documented in [[icons.py]]
   as already shipped) that existed only on-disk on the Pi -- not in this
   git repo's only commit (`git log` shows one commit, "Initial commit:
   working state before cleanup") and not in the stale local checkout.
   Pushing the local file silently deleted both, and `dashboard.py`'s
   `render()` still called `weather_icon(..., night=dark_mode)` --
   `TypeError: weather_icon() got an unexpected keyword argument 'night'`,
   crash-looping `pi-eink-dashboard.service` (`NRestarts` climbed to 9+ in
   under 2 minutes) with **the panel stuck fully blank** the whole time
   (the crash happens before the first successful `epd.display()` call
   each restart). Caught via a routine "is the Pi still stable" check,
   not proactively. Fixed by reconstructing `moon()` (filled disc + an
   off-center disc erased in the background color, `offset=r*0.55`, per
   [[icons.py]]'s own documented spec) and the `night` branch on
   `weather_icon()` from that same vault note plus `dashboard.py`'s actual
   call site, cross-checked every other `icons.*` call in `dashboard.py`
   against what's defined in `icons.py` to rule out further clobbered
   functions before redeploying. **Lesson: `scp`-ing a local file to the
   Pi is only safe after re-pulling that exact file fresh first, every
   time, not just once per session for the file that happened to look
   stale** — `dashboard.py` got this treatment, `icons.py` didn't, and
   that was the gap.
8. **Follow-up: `cpu_chip`/`ram_stick` still looked bad after #6's
   width=2 unification.** The isolated `icon_gallery.py` preview renders
   icons at a bigger test size (~20px) than these two icons' real
   in-context size (~12-14px, a single mini-stat strip) -- at that real
   size, 2px strokes + 6 pins left almost no interior negative space and
   read as a solid blob, invisible in the bigger gallery render. Only
   caught by cropping and zooming the actual in-context render, not the
   gallery. Fixed with 1px strokes and fewer/better-spaced pins on just
   these two (everything else's 2px treatment was fine at its own larger
   actual size). **Lesson: an isolated icon-gallery preview at an
   arbitrary convenient size is not sufficient QA for e-ink-scale icons
   -- always additionally check a zoomed crop of the real in-context
   render at the icon's actual deployed size.**
9. **`is_dark_mode()` gained minute precision.** Was whole-hour only
   (`getint` + `datetime.now().hour`); switched to `getfloat` +
   `hour + minute/60` so `dark_mode_start_hour`/`end_hour` can be
   fractional (`17.5`/`5.5` = 5:30 PM/5:30 AM, was `20`/`6`) -- the old
   fixed 8 PM threshold meant dusk at this longitude (Guwahati, well
   east of the IST reference meridian) passed well before dark mode
   kicked in. Hotspot header also simplified from `"Hotspot: PINET"` to
   just `"PINET"`.
10. **Per-phase carousel durations, replacing uniform `carousel_minutes`.**
   `status_seconds=180`, `qr_seconds=30`, `doom_seconds=180`,
   `hotspot_seconds=180` in config.ini. Required reworking phase
   selection (walk cumulative durations instead of one modulo, since
   durations now differ per phase) and capping the refresh-wait loop to
   `remaining_in_phase` -- the old loop always slept the full
   `refresh_minutes` regardless of phase boundaries, which would have
   overshot the short 30s QR phase whenever `refresh_minutes` was
   longer. Verified against a standalone boundary test (every
   transition point across multiple full cycles, including wraparound)
   before trusting it in the live loop -- this kind of off-by-one is
   easy to get subtly wrong and hard to notice from log lines alone.
11. **New: DOOM-logo shutdown splash.** `pi-eink-shutdown-splash.service`
   (`Type=oneshot`, `RemainAfterExit=yes`, `ExecStart=/bin/true`,
   `ExecStop=`.../shutdown_splash.py) shows the DOOM logo, forced dark
   mode, on the real panel during shutdown/reboot, then leaves it
   there -- e-ink holds its last image with no power. Ordered
   `Before=pi-eink-dashboard.service shutdown.target reboot.target
   halt.target poweroff.target` (plus `Conflicts=` those targets,
   `DefaultDependencies=no`) so its `ExecStop` runs only after the live
   dashboard has released the SPI/GPIO panel -- two processes must never
   touch it at once. Needed `User=rupal` explicitly (unlike a plain
   `sudo` invocation, which lacks `waveshare_epd` -- that package lives
   in `rupal`'s user site-packages, not a system path). **Tested without
   a real reboot**: manually `systemctl stop pi-eink-dashboard.service`
   first (release the panel), then `systemctl stop
   pi-eink-shutdown-splash.service` (fires `ExecStop`), confirmed a
   clean run in the journal, then restarted both to resume normal
   operation -- this is the safe way to exercise a shutdown hook without
   actually rebooting the machine.

---

# 2026-09-12 session

A separate later session (everything above is 2026-09-06). Covers a
persistent-journald fix, PINET in-browser file viewing + a responsive tabbed
UI, and a power / boot-timing optimization pass (plus a self-inflicted brownout
loop and its lesson). See also [[power and undervoltage]], [[pinet-board]],
[[systemd service]].

## 12. journalctl never kept logs across reboots (volatile journal)

**Symptom**: `journalctl --header` always showed `/run/log/journal/...`
(volatile); logs wiped on every reboot. An earlier session's attempts (setting
`Storage=persistent` in the main `/etc/systemd/journald.conf`, correct
`/var/log/journal` perms) hadn't worked and it was left "unresolved".

**Root cause**: a Raspberry Pi OS **vendor drop-in**
`/usr/lib/systemd/journald.conf.d/40-rpi-volatile-storage.conf`
(`[Journal]` / `Storage=volatile`) overrode the main config -- drop-ins beat
the main file. Confirmed with `systemd-analyze cat-config systemd/journald.conf`
(main file's `persistent`, then the drop-in's `volatile` parsed last → wins).

**Fix**: `/etc/systemd/journald.conf.d/99-persistent-storage.conf`
(`Storage=persistent` + `SystemMaxUse=100M`). An `/etc` drop-in named `99-`
beats the vendor `40-`; survives apt updates (unlike editing the vendor file);
the size cap bounds SD-card wear (which is *why* RPi OS ships volatile). Also
committed into the `pi-eink-dashboard` git repo as a tracked drop-in + an
install.sh step (commit `cc2d6c6`) -- see [[systemd service]].

**Verified**: reboot-tested -- `journalctl --list-boots` now retains multiple
boots, a pre-reboot marker survived, and the shutdown-splash `ExecStop` finally
appeared in `-b -1` ("DOOM logo (dark mode) shown for shutdown") -- the log
proof the 2026-09-06 reboot tests (entry 11) couldn't get.

## 13. PINET board -- view uploaded files in the browser + responsive tabbed UI

**Change requested**: let users open uploaded files in their browser (not just
download), and make the UI mobile- and desktop-friendly.

**What was done** (`/opt/pinet-board`, see [[pinet-board]]):
- `app.py`: new `/view/<id>` route serves uploads **inline** (images, PDF,
  video, audio, text render in-browser) via `send_from_directory(as_attachment
  =False)` + `mimetypes.guess_type`. Security: scriptable types
  (`html/htm/xhtml/shtml/svg/svgz/xml/js/mjs`) are force-downloaded even from
  `/view`, and every `/view` response sends `X-Content-Type-Options: nosniff`
  -- stops an uploaded file running script in the board origin and stealing the
  session cookie. `/download/<id>` (attachment) unchanged. Added
  `_file_kind()`/`_file_ext()` helpers + a `filesize_str` Jinja filter;
  `board()` passes files as dicts with `kind`/`viewable`. `/view` sits behind
  the same `before_request` auth gate (verified unauthed → 302 /login).
- `templates/board.html`: fake anchor "tabs" replaced with **real
  Messages/Files tabs** (JS-switched, `role=tab`; both panels show if JS off).
  Files render as a responsive **grid of cards** with image thumbnails
  (`<img src=/view/id loading=lazy>`) + View (inline, new tab) + Get (download).
- `static/style.css`: `.tab`/`.tab-panel`, `.file-grid`
  (`minmax(150px,1fr)` → 2-col phone, multi-col desktop), `.file-card`/`.thumb`/
  `.fa-btn`; `.page` widened 560→680px; 640px padding breakpoint.
- `static/app.js`: tab switching; upload success reopens on the Files tab.

**Verified**: Flask test client with an injected authed session (board renders
200 with tabs+grid; `/view` PDF → inline + nosniff; image → image/jpeg inline;
`/download` → attachment; `.svg` → forced download) + live curl (unauthed 302).
Service restarted clean, `NRestarts=0`. Backups `.bak-20260912060031`.
**pinet-board is NOT under git** -- those `.bak` files are the only history.

## 13b. PINET board -- guest/admin roles + admin-only file delete

**Change requested**: a guest login separate from the existing (now admin)
login, with admin able to delete uploaded files.

**What was done** (`/opt/pinet-board`, see [[pinet-board]]):
- Two roles from one password field -- whichever password matches sets
  `session["role"]`. Existing `board.conf` = **admin**; new optional
  `/etc/pinet-board/guest.conf` = **guest** (absent = no guest tier).
  `check_password()` now takes a conf path; login tries admin then guest.
  Added `/logout` and a `@app.context_processor` exposing `role`/`is_admin`.
- **Admin-only delete**: `POST /delete/<id>` guarded by `is_admin()` removes the
  DB row + the file on disk (POST-only, so no GET/prefetch/link can trigger it).
- **UI**: header session bar (Admin/Guest badge + Log out); file cards show a red
  Delete button (JS confirm) only for admin; guests never see it and the route
  rejects them.
- Guest password set via interactive `sudo /opt/pinet-board/set_guest_password.py`
  (writes BOTH the salted hash `guest.conf` and the e-ink display plaintext
  `guest_password_plaintext.txt` -- see entry 18).

**Verified**: Flask test client as the pinet-board user -- admin sees/uses delete,
guest blocked at both UI and route; exercised on a throwaway file so no real
upload was touched. Service restarted clean, NRestarts=0. Backups `.bak-<ts>`.
**pinet-board is not under git** -- backups are the only history.

## 14. Power/RAM optimization -- disabled unused services

**Goal**: reduce load on this chronically under-volted Pi (see
[[power and undervoltage]]) without losing the desktop GUI.

**Disabled (persistent, reversible)**: `docker`+`containerd` (no containers;
the Kali toolbox starts it on demand), `packagekit` (masked -- it was burning
~20% CPU refreshing sources), `rpcbind`+`nfs-blkmap` (NFS unused). Freed ~30MB
and idle CPU; ~524MB available afterward (was ~455). Core services (e-ink,
PINET, hostapd, dnsmasq) all stayed up, 0 failed units.

## 15. Boot-timing staggering -- flatten the boot power spike (keep GUI)

**Symptom/why**: the Pi browns out and resets *during boot* -- the coincident
peak of CPU across all 4 cores + wlan1(USB)/USB-drive inrush + the whole
~215MB desktop launching at once exceeds what the marginal PSU delivers.

**Fix** (see [[systemd service]]): disabled `cloud-init`
(`/etc/cloud/cloud-init.disabled`; ~19s of useless early load on an appliance),
disabled `NetworkManager-wait-online` (17s boot block), delayed `lightdm` 20s
(`lightdm.service.d/10-stagger.conf`) so the desktop launches into a settled
system, pushed `wayvnc` to 50s + `After=lightdm` (its override.conf already had
`sleep 35`) to separate the VNC load from the desktop-launch spike.

**Status**: changes confirmed in effect on the current boot (desktop up,
wayvnc in its 50s pre-sleep). Brownout-**prevention** benefit NOT yet proven
across a clean reboot -- verify on the next NATURAL reboot via the persistent
journal. Does not touch `0x50005` (still present); real cure is a better PSU.

## 16. Self-inflicted brownout reboot loop (LESSON: don't force-reboot this Pi)

**What happened**: after applying entry 15 I rebooted to "validate" it. The Pi
went into a **brownout reboot loop** -- the persistent journal (entry 12) shows
boot `-1` lasted exactly **1 second** (12:45:19→12:45:20) before resetting; it
was unreachable ~13 min, then caught a stable boot on its own.

**Lesson**: the reboot inrush is the single highest-draw moment; forcing a
reboot on this marginal PSU triggers the exact failure we're mitigating. Apply
boot changes and let them take effect on the **next natural reboot**; don't
force one. Documented in [[power and undervoltage]].

## 17. `pinet-ap-network.service` failed at boot -- RF-kill race

**Symptom**: after the recovery boot, `pinet-ap-network.service` (sets wlan0's
static `10.10.10.1` for the PINET hotspot) was a failed unit:
`RTNETLINK answers: Operation not possible due to RF-kill` (exit 2).

**Root cause**: with cloud-init disabled (entry 15) the early boot got ~19s
shorter, so this service now ran **before the onboard wlan0 radio's rfkill
cleared** -- a race the cloud-init delay had previously masked.

**Fix**: drop-in `pinet-ap-network.service.d/10-rfkill-wait.conf` adds two
`ExecStartPre` steps -- unblock all radios via **sysfs**
(`echo 0 > /sys/class/rfkill/*/soft`; the `rfkill` CLI isn't installed) and a
15s wait loop for wlan0 -- before the `ip` commands. See [[systemd service]].

**Verified**: service now active, wlan0 has `10.10.10.1`, hostapd/dnsmasq
active, 2 hotspot clients leased, 0 failed units. Not re-tested across a real
reboot (don't force one -- entry 16).

## 18. e-ink hotspot screen -- show GUEST board password, not admin

**Follow-up to entry 13b's admin/guest split.** The hotspot screen shows the
board password next to the Wi-Fi join QR (via [[dashboard.py]]
`get_board_password`, reading a plaintext copy). Since admin can now delete
uploads, displaying the admin password on a panel anyone nearby can read would
hand out delete-capable access.

**Fix**: guest password set (`/etc/pinet-board/guest.conf` + a
`guest_password_plaintext.txt` 640 root:rupal for the display, mirroring the
admin plaintext model). `get_board_password()` now defaults to the guest
plaintext, falling back to the admin plaintext only if no guest password is set.
Committed in the e-ink repo (`00c5be0`); pinet-board's own guest helper is
`set_guest_password.py`. **Verified**: `get_board_password()` returns the guest
password; service restarted clean, NRestarts=0, no exceptions.

## 19. Hotspot/QR carousel screen -- show PINET media storage free space

**Change requested**: display the PINET file-storage info on the hotspot/QR
carousel screen. That drive (`/mnt/pinet-media`) is where board uploads live.

**What was done** ([[dashboard.py]]): `get_hotspot_status()` now reads
`get_disk_usage("/mnt/pinet-media")` and carries `storage_free_gb`/
`storage_total_gb`; `render_hotspot_screen` repacks the left column (device
count moved up + 40->34px) to fit a `Storage: N GB free of M GB` row between the
board password and the IP, without crowding the bottom edge or the join QR.
`preview_render.py` now also renders this screen for QA.

**Verified**: light + dark previews at real panel resolution (`FakeEPD`,
750x366 upscale) -- storage row fits, no overlap/overflow, QR still scannable in
both modes (screenshot-checked). Live `get_hotspot_status()` returns real values
(53.4GB free / 57GB). Service restarted clean, NRestarts=0. Commit `6766772`.

## 20. Weather intermittently "Unavailable" -- location retry + weather cache

**Symptom** (user-reported): weather sometimes shows "Unavailable". Journal
showed two distinct causes:
- **Startup geolocation failure kills weather for the whole session**:
  `get_location()` runs once before the main loop; right after boot the
  network/DNS often isn't ready (`Temporary failure in name resolution`,
  `Expecting value` from ip-api.com), so `lat/lon=None` and every
  `get_weather(None,None)` returns None until restart. Location only re-resolved
  on a network *change*, so a plain startup failure never recovered. Made more
  likely by disabling `NetworkManager-wait-online` for the boot-power work
  (entry 15) -- boot no longer waits for the network.
- **Transient Open-Meteo 503** blanked the screen for that one cycle.

**Fix** ([[dashboard.py]] main loop, phase 0): retry `get_location()` whenever
`lat/lon` is still unresolved (not only on network change), and cache the last
successful weather -- reuse it over a transient fetch failure, showing
"Unavailable" only if weather has never succeeded this run. Chosen over
re-adding `wait-online` (keeps the boot-power win; robust regardless of boot
timing). **Verified**: live `get_location`/`get_weather` succeed (Guwahati,
30C Overcast); service restarted clean, NRestarts=0. Commit `e950bf8`.


**Validated across a reboot (2026-09-12)**: the weather fix (entry 20) was
confirmed on a real boot. The dashboard journal shows the exact fail-then-recover
path: `14:02:37 IP geolocation failed -> lat=None` (network not ready at boot),
then `14:04:02 Location resolved on retry: ... Guwahati` -- proving the status-
phase retry recovers weather on its own (~90s), where the old code would have
left it "Unavailable" until the next restart. Clean single boot, 0 failed units,
throttled=0x0.

---

# 2026-09-15 session -- DSI slideshow, cleanup, QA audit

The DSI touchscreen work (built 2026-09-14/15) is documented in
[[dsi photo frame]]; these entries cover the 2026-09-15 changes.

## 21. Slideshow cropped photos -- now fitted, over a blurred background

**Symptom** (user): slideshow images got cropped. **Cause**:
`dsi-photo-normalize.sh` used `-resize 800x480^ -extent`, filling the panel
and cutting off the rest; a portrait certificate lost most of its content.
**Fix**: fit the whole photo (`-resize 800x480`); first with black bars, then,
at the user's request, over a blurred, darkened copy of the same photo
(80x48 thumbnail, `-blur 0x5`, scaled up, `-modulate 50`; cheap on a Pi 3,
~5s per large photo, once). A `.render-mode` marker in the cache forces a
rebuild when settings change. **Verified**: portrait and landscape renders
checked by eye; the new rule is saved as a user requirement.

## 22. Cleanup: temp files, old backups, Firefox, Docker, orphaned packages

At the user's request. Deleted: a 256MB SD speed-test file, an aborted
diagnostics report, 1.2GB apt cache, Chromium leftovers, 46 old `.bak*` files
(kept the `*.bak-splash` boot-recovery set), the stale bootstrap copy, and
`~/e-Paper` (2GB Waveshare repo; the driver is installed separately in
`~/.local/lib/python3.13/site-packages/waveshare_epd`). Purged Firefox (+
`rpi-firefox-mods`), Docker (docker.io, containerd, runc, buildx, cli) and 19
orphaned packages (xdg-desktop-portal*, pipewire-libcamera, slurp, criu,
needrestart, ...). SD card **73% → 43%** full. **pinet-board and
`/usr/local` now have no `.bak` history**; keep rollback copies off the Pi.
The PINET Portal desktop shortcut was repointed from Firefox to the Qt web
window, see [[dsi photo frame]].

## 23. Slideshow came up as a small window after a package install

**Symptom** (user): slideshow not fullscreen (640x384 in a corner). **Cause**:
the install guard restarted the slideshow while the screen was off; the script
powers the output on for a fixed 4s while pqiv maps, but the Pi was still busy
after apt, pqiv mapped late with the output off, and came up windowed.
**Fix**: pqiv reads actions from a fifo; `dsi-wake.sh` sends
`toggle_fullscreen(1)` on every wake (no-op if already fullscreen), only while
the service is active since a stale fifo blocks writers. Unit gets
`SuccessExitStatus=143`. **Verified**: reproduced the tiny-window state on
purpose, then an ordinary wake restored fullscreen; also survived a real
24-package apt run.

## 24. QA audit -- everything exercised live

User asked for a complete QA pass. Results:
- System: 0 failed units, recent shutdowns clean, no SD errors, journal
  persistent, NTP synced, write-back limits applied.
- e-ink: running since boot, 0 restarts; all 4 carousel phases on schedule;
  all 5 screens (incl. kiosk) rendered light+dark from live data; guest (not
  admin) password shown; data sources in 2.3s.
- PINET: AP on channel 6, WPA2; DHCP + option 114; every DNS name resolves
  to 10.10.10.1; ip_forward 0, no NAT.
- Portal: 26 live HTTP checks (unauth redirect over HTTP and HTTPS, wrong
  password, guest/admin roles, upload/view/download/delete, SVG forced to
  download, logout) all pass. See [[pinet-board]].
- Slideshow add/remove; screen sleep, touch grab, single vs double tap;
  Camera, Ezykam and Portal kiosks with shed + full restore: all pass.
- Found and fixed: entries 25-27. Open: camera image very dark (physical?),
  firewall untested from a real PINET client, boot splash unseen.

**Mistake during QA**: a test cleanup scraped `/delete/<id>` from the board
HTML and deleted a real upload (id 10, `Degree_Certificate.jpg`). Restored
from the byte-identical slideshow copy (its mtime matched the 07:13:14 upload
in the access log) and re-inserted under the original id, name, size and
time; verified it lists and opens. Lesson: delete only exact IDs captured at
creation time, never IDs scraped from a page.

## 25. Screen stayed on forever after a double-tap wake

**Cause**: while asleep the tap daemon grabs the touchscreen, so the wake
tap never reaches the compositor and swayidle never re-arms. **Fix**:
`dsi-wake.sh` ends with `systemctl --user try-restart dsi-idle-sleep.service`
(no-op while a kiosk has idle-sleep stopped). **Verified**: >200s awake with
no input before; 88s after the fix.

## 26. Bluetooth was never really shed during kiosks

**Cause**: `dbus-org.bluez.service` alias -- the taskbar applet restarted
bluetoothd 0.13s after the power manager stopped it. **Fix**:
pi-power-manager runtime-masks bluetooth while shed, unmasks before restore.
**Verified**: stayed inactive for the whole shed; back active and still
enabled after restore. Also removed the dead `x-www-browser` taskbar launcher
left by the Firefox removal.

## 27. SSH and VNC reachable from PINET guests -- firewall added

**Risk**: sshd (password auth) and wayvnc listened on wlan0; guests can read
the PINET Wi-Fi password on the e-ink, and rupal has NOPASSWD sudo; no
firewall rules were loaded. **Fix** (user-approved): `/etc/nftables.conf`
(`nftables.service` enabled) with one rule, `iifname "wlan0" tcp dport
{ 22, 5900 } counter drop`, everything else accepted. **Verified**: SSH and
VNC still work over home Wi-Fi, portal answers on 80/443. Not yet tested from
a device on PINET. Note: `nft` is `/usr/sbin/nft`, not on the SSH PATH.

## 28. Phone uploads fail with a connection error -- portal note added

**Symptom** (user): after a long time in the phone's file picker, the upload
shows a connection error. **Findings**: the phone's upload never reached the
Pi. The server was ruled out: every response is `Connection: close`, and both
a 6-minute idle then upload and a slow 90s upload succeed. The user uses the
Samsung sign-in popup with mobile data on; most likely the popup (a restricted
mini-browser) is cut off while in the file picker and/or the request leaves
over mobile data. Not confirmed on the device. **Mitigation**: a note on the
Files tab ("open 10.10.10.1 in your browser instead of the Wi-Fi sign-in
popup, and turn off mobile data") and a specific network-error message; also
fixed a card-sized heading icon. See [[pinet-board]].

---

# 2026-09-16 session

## 29. Kali toolbox rebuilt NATIVE (Docker was purged)

Docker (and its `kali-pentest` image) was removed 2026-09-15, so the container
was gone. All 13 lean tools turned out to be in Debian trixie's own repos (no
Kali repo → no repo-mixing risk), so they were installed natively via `apt`
(nmap, arp-scan, netdiscover, masscan, aircrack-ng, mdk4, hcxdumptool, hcxtools,
wifite, reaver, bully, macchanger, tcpdump). A mid-install power cut (loose plug)
corrupted `python3-matplotlib`; repaired with `dpkg --configure -a` +
`apt --reinstall`. **Verified**: 13/13 installed, dpkg clean.

## 30. Kali power mode + pirate carousel

New `/usr/local/sbin/kali-power-shed start|stop` frees the power budget for a
pentest session: stops PINET + sheds VNC/BT/slideshow and drops `/run/pentest-mode`;
restores in reverse. `wifi-pentest-start/stop` now call it (and the stale
"docker start" line was fixed). `dashboard.py` shows a big skull-and-crossbones
"PENTEST MODE" carousel screen while `/run/pentest-mode` exists or wlan1 is in
monitor mode (committed `35f7025`). A **Kali Tools** desktop shortcut (pirate
icon) opens a terminal in `~/kali-work`; `kali-tools-guide.txt` written to the
desktop. **Verified**: shed/restore cycle; pirate screen via panel-res preview.

## 31. Camera capture controls (Photo/Video → PINET storage)

Added on-screen Photo/Record to the DSI Camera kiosk, saving to
`/mnt/pinet-media/camera` (photos PIL-rotated upright; H.264 video with a
display-matrix rotation, no re-encode). **Cause of much pain**: `cog` (WPE)
does NOT deliver taps to web content, and a rich page even segfaults it, while
QtWebEngine renders it but BROWNS THE Pi OUT. **Fix**: the buttons are NATIVE
GTK layer-shell overlays (`dsi-cam-controls.py`, same path as the ✕ button) that
POST to a bare-`<img>` cam-server; `dsi-cam-server.py` uses a single persistent
worker thread + dual stream (an encoder started on a transient HTTP thread
produces no output). Rotation set to 270°. **Verified**: native taps saved a
photo + video; ✕ tears everything down and restores PINET.

## 32. PINET made on-demand

`do not start pinet by default`: `pinet-ap-network`, `hostapd`, `dnsmasq`,
`pinet-board`, `stunnel@pinet-board` all `systemctl disable`d. New
`pinet-start`/`pinet-stop` (root, NOPASSWD) + **Start PINET / Stop PINET**
desktop shortcuts (monochrome wifi / slashed-wifi icons). **Verified**:
start→active, stop→inactive, disabled at boot.

## 33. raspotify → Bluetooth speaker

`raspotify` connected from Spotify but dropped. **Causes**: backend was `alsa`
(played to the built-in card, not BT); and `ProtectHome=true` in the unit hid
`/run/user`, so librespot couldn't reach the PipeWire-pulse socket
("PulseAudioSink Connection refused" → crash); plus `Restart=no` meant the boot
race never recovered. **Fix** (override drop-in): `LIBRESPOT_BACKEND=pulseaudio`,
`ProtectHome=no`, `Restart=on-failure`. Volume: BT sink → 150%, librespot
`VOLUME_CTRL=linear` + full initial volume. Note: `pactl` isn't installed here —
use `wpctl`/`pw-play`. **Verified**: plays to "Dubstep Pop 600"; test tone reached
the speaker. See [[Device Overview]].

## 34. Desktop / UX polish

Execute-popup on shortcuts fixed (all launchers marked trusted + `quick_exec=1`;
renamed a broken photo-frame launcher). 12-hour taskbar clock. Ezykam shortcut
icon → a Wi-Fi security-camera design; Kali Tools → pirate skull. Epiphany
(WebKitGTK, light) installed for desktop browsing. `lxterminal` shortcut needed
`GDK_BACKEND=wayland` (Xwayland isn't running under labwc).

## 35. Power incident, audits, cleanup, docs

Several resets this session were a **loose power plug** (+ Chromium load), not the
installs — confirmed the 5V-sag → 600 MHz throttle mechanism (no amperage readout
on a Pi 3B). QA + code audit: both pass (0 failed units, dpkg clean, scripts
parse). Session temp files + camera test captures cleaned (exact paths,
`.bak-splash` preserved). New whole-device description written: [[Device Overview]].


# 2026-09-17 session -- DSI passcode lock, Spotify e-ink panel, unified diagnostic

## 36. Photo frame no longer sleeps while the album is showing

`dsi-sleep.sh` now exits early (and `try-restart`s `dsi-idle-sleep` so it
re-checks next window) whenever `dsi-photo-frame.service` is active, so the
slideshow stays lit; normal idle-sleep resumes once the album is closed.
**Verified** (entry 40 diagnostic): with the album running, `dsi-sleep.sh` is a
no-op and the backlight stays on.

## 37. Passcode lock on wake (opaque, blocks the desktop, PINET logo)

`when i wake up ask for a password`. New `/usr/local/bin/dsi-lock.py`: a
full-screen Wayland layer-shell (OVERLAY) **opaque** window with an on-screen
number pad + the PINET hood logo; entering the code in `/etc/dsi-lock/passcode`
(default `1234`) unlocks. Single-instance via `/run/user/1000/dsi-lock.pid`.
Wired into `dsi-tap-wake.py` (`wake_and_lock()`) so ONLY a genuine
double-tap-from-sleep locks -- not the boot/kiosk/demo/install-guard paths that
also call `dsi-wake.sh`.
- **First version showed the desktop through it** -- it copied
  `dsi-close-button.py`'s transparent setup (`app_paintable` + rgba visual), so
  only the buttons were opaque. Fixed to a plain opaque toplevel; the
  all-four-edge anchoring already gives a full 800x480 surface. **Proven with a
  `grim` screenshot**: all four corners sample `srgb(15,17,20)`, no bleed-through.
- **Desktop flashed before the lock on wake** -- the backlight came on before the
  lock had painted. Fixed with a handshake: `dsi-wake.sh` defers the backlight
  when `DSI_DEFER_BACKLIGHT=1`; the lock touches `/run/user/1000/dsi-lock.ready`
  on first `map-event`; `wake_and_lock` lights the panel only after that. (The
  GTK `draw` signal needs pycairo, which errored here -- `map-event` avoids it.)
  Re-wake while already locked re-lights.
- Cold-start ~3s (Python/GTK on the Pi 3) on the first wake after an unlock;
  re-wakes ~0.8s. Recovery if it ever won't unlock:
  `ssh <pi> 'kill "$(cat /run/user/1000/dsi-lock.pid)"'`.

## 38. Closing the album (the X) drops to the lock, not the desktop

`when closing the album assign the same lock screen`. New shared helper
`dsi-lock-show` raises the lock in its OWN `systemd-run --user --scope` (so it
survives the photo-frame service being stopped -- a plain child would be in the
slideshow's cgroup and get SIGTERM'd). New `dsi-photo-close` raises the lock
FIRST (while the slideshow still covers the desktop) then stops the slideshow.
`dsi-photo-frame.sh`'s X now runs `dsi-photo-close`; `wake_and_lock` uses the
same helper. **Verified**: photo -> X -> lock (grim corners = lock bg), unlock ->
desktop.

## 39. +12 scenic photos in the slideshow

Downloaded 4 each of space / mountains / beach (CC Flickr via loremflickr,
800x480) into `/mnt/pinet-media/slideshow/scenic_*.jpg`, pre-rendered into the
cache. 15 photos total; no brownout.

## 40. Unified `pi-diagnostic` (replaces `dsi-qa-check`)

`/usr/local/bin/pi-diagnostic [all|eink|network|dsi]` -- one health/QA
diagnostic. **eink**: service active + NRestarts=0; carousel liveness from
`Carousel phase=` journal lines; the invariant that `epd.sleep()` appears
exactly once as code (finally-only, never in the loop -- in the loop it crashes
`displayPartial`); `displayPartial` present (no white flash); no tracebacks.
**network**: uplink/route/internet/DNS; PINET on-demand DOWN as INFO not FAIL;
nftables; raspotify + the `--onevent` hook. **dsi**: the former `dsi-qa-check`
(opaque lock via grim corner sampling, no-flash wake x3, re-wake x2, close->lock
x2, photos, single-instance, unlock via injected keys) -- self-restoring. First
combined run **48 PASS / 0 WARN / 0 FAIL**. eink+network read-only; dsi invasive.
See [[test and preview scripts]].

## 41. Spotify now-playing panel on the hotspot screen when PINET is down

`when pinet is inactive show a spotify carousel ... keep the pinet-inactive
message`. `render_hotspot_screen`'s inactive branch keeps "Hotspot inactive" and
adds a Spotify panel: track / artist / `[playing|paused]`, or device + output
when idle. Fed by a new librespot `--onevent` hook
(`/usr/local/bin/raspotify-nowplaying-hook` -> `/run/user/1000/raspotify-nowplaying`;
wiring it needed a raspotify restart, dropping the Connect session). New
`get_spotify_status()` + `icons.spotify()`. **Committed** `58044df` (the DSI
scripts stay out of git). Verified by rendering all states at 250x122 and viewing
the PNGs; the arrow glyph was tofu in Roboto so the output line uses `>`. See
[[dashboard.py]], [[icons.py]], and entry 33 for the raspotify setup.

## 42. Spotify panel -- live play-state + device renamed PINET

`still showing nothing playing` + `change the raspotify name to PINET`. The panel
showed "Nothing playing" while audio was flowing, because the librespot
`--onevent` file only updates on events and playback predated the hook. Fixed:
`get_spotify_status()` now takes play/idle from the live PipeWire librespot node
(`pw-dump`, `state==running`); the event file still gives the title. New "Playing"
(no-title) render case. Device renamed to **PINET** (`LIBRESPOT_NAME=PINET`). The
panel only renders when the hotspot is INACTIVE, so it's hidden while PINET is up.
Commit `bf368a1`. See [[dashboard.py]].

## 43. LOW VOLTAGE message debounced (ignore one-time spikes)

`don't show low voltage if it's just a one-time spike`. `main()` now samples power
every loop iteration and shows LOW VOLTAGE/THROTTLED only after
`undervoltage_min_readings` (default 3) consecutive active reads, so a momentary
blip is ignored; the chronic sustained `0x50005` still shows. `get_power_status`
already excluded the sticky bits 16/18. Checked now: still `0x50005`, ARM at
600 MHz (really throttled). Commit `bf368a1`. See [[power and undervoltage]].

## 44. Lock screen "Screen off" button

`add a turn-screen-off button at the lockscreen`. `dsi-lock.py` now has a
top-right **"Screen off"** button (a `Gtk.Overlay` over the keypad -- number pad
untouched) that runs `dsi-sleep.sh` to blank the DSI panel immediately rather
than waiting for idle-sleep. The lock keeps running; a double-tap re-lights it.
**Verified** by injecting a touch at the button: `bl_power` 0->1 (screen off),
lock still up. Passcode also changed from the default. `dsi-*` stay out of git.

## 45. Spotify track title -- librespot omits it, resolved via oEmbed

`watch for the track title when i play`. Confirmed live: this librespot 0.8.0
`--onevent` passes `TRACK_ID` but not `NAME`/`ARTISTS`. So
`raspotify-nowplaying-hook` now resolves the title from Spotify's public oEmbed
endpoint (no API key; needs internet), caches by track_id, and preserves it across
non-track events. `dashboard.py` shows the title only while playing/paused.
Verified end-to-end: a real track change -> hook resolved "Namastute" -> panel
shows it with `[playing]`. No artist (oEmbed gives title only). Commit `a26394c`;
the hook lives in `/usr/local/bin` (not git). See [[dashboard.py]].

## 46. Lock Screen shortcut + double-tap-wake fix (backlight-only sleep)

`add a lock screen shortcut` + `double tap to wake not working / touch not registered`.
Added a trusted **Lock Screen** desktop shortcut (`dsi-lock-show`, padlock icon
`pinet-lock.svg`). For the wake bug: software-injected taps always woke the panel but a
real finger did not after the Screen off button -- because `dsi-sleep.sh` ran
`wlopm --off DSI-1`, and disabling the DSI output gates the ft5x06 touch controller's
reporting (device stays enumerated, but no touch events). Fix: `dsi-sleep.sh` now blanks
the **backlight only**, keeping the output + touch powered (screen still dark). Costs a bit
of power. `pi-diagnostic all` = 50 PASS; physical double-tap to be confirmed by the user
(software evdev injection is not a faithful proxy for a real touch, which is what misled
earlier testing). Passcode also changed to a new value (not recorded).

## 47. Spotify pauses/resumes with the Bluetooth speaker

`when the bluetooth disconnects the song keeps playing -- pause it and resume on reconnect`.
librespot keeps advancing (Spotify Connect drives play/pause, not the sink), so on BT loss
it moved the stream to the built-in card and played on. New `raspotify-bt-guard` (user
service) polls for the BT speaker's PipeWire sink and **SIGSTOPs librespot when it's gone**
(freezes audio + track position) / **SIGCONTs when it returns** (resumes the same spot).
Runs as rupal; `ExecStop` resumes librespot if the guard is stopped. Verified: disconnect
-> librespot state T (paused), reconnect -> state S (resumed). Long disconnects may drop the
Connect session (network frozen too). See [[Device Overview]].
