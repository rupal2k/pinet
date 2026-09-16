---
tags: [project, raspberry-pi, e-ink, hotspot, security]
---

# PINET captive portal (2026-09-06 REMOVED→REBUILT, 2026-09-07 REMOVED FOR GOOD)

**Status as of 2026-09-07: permanently removed.** This feature (the
password-gated internet-bridge toggle, `pinet-portal.service` on port
8090) went through removal → rebuild on 2026-09-06 (see history below),
then was explicitly removed again — for good this time — on 2026-09-07
at the user's request, and fully verified clean: no leftover service
unit, `/opt/pinet-portal`, `/etc/pinet-portal`, sudoers grant,
`/usr/local/sbin/pinet-bridge` script, or `pinet-portal` system
user/group. Port 8090 no longer listens, `ip_forward=0`, no NAT rules.
A full functional-integrity pass on the rest of the project (e-ink
dashboard's 4 carousel phases, `pinet-board`, hostapd/dnsmasq) found
zero regressions from the removal.

**This note is kept only for historical/architectural record** — the
design rationale below (why not the root password, the
`CapabilityBoundingSet` bug, password storage approach) may be useful
if a similar feature gets built again, but none of it describes
anything currently running on the Pi.

**One correction to this note's own prior claim, found 2026-09-07**:
the "Dashboard integration" section below said `dashboard.py` had a
`get_bridge_active()` function showing live "Internet: ON/OFF" status
on the hotspot carousel screen. **A direct grep of the actual
`dashboard.py` on the Pi found no such function ever existed in the
code** — this note was wrong (or described something that was written
here but never actually merged). Left the original text below,
struck through in spirit, as a caution: verify vault claims against
the live file before trusting them, this vault has now been caught
out of sync with real code more than once (see the e-ink project's
`icons.py` regression history in Overview.md / auto-memory).

**Current architecture: `pinet-board` only, one service.**
- `pinet-board.service` (`/opt/pinet-board`, port **80**, user
  `pinet-board`) — the anonymous message board + up to 1GB file sharing
  feature, originally built independently and concurrently by a
  different session while this one was rebuilding the (now-removed)
  bridge toggle (found running, mid-build, at 2026-09-06 17:13 — see
  "Concurrent build collision" below). This is now simply "the portal"
  — there is no second service. Uploads/tmp storage moved off the SD
  card onto a dedicated USB drive at `/mnt/pinet-media` on 2026-09-07
  (see auto-memory `pi-pinet-media-storage`, not duplicated here).
- The dnsmasq wildcard DNS redirect (`/etc/dnsmasq.d/wlan0-ap-captive.conf`,
  `address=/#/10.10.10.1`) — originally built for the bridge toggle's
  captive-portal trigger — was **deliberately kept** when the bridge
  toggle was removed, because it's now what makes phones joining PINET
  auto-popup to `pinet-board`'s login page instead. Removing it would
  silently kill that auto-popup (phones would need to manually browse
  to `10.10.10.1`). If this file is ever touched again, check whether
  `pinet-board`'s auto-popup still depends on it first.

## Concurrent build collision (2026-09-06, ~17:10-17:25)

While rebuilding this feature over SSH, a second, more complete
implementation (`pinet-board`) appeared on the Pi mid-session — built
between 17:10 and 17:19, while a separate local desktop login (`seat0`,
active since 16:45) was also present. Likely another session (the user
working directly on the Pi, or a parallel remote-control session) asked
for the same "anonymous chat + file sharing" feature independently. This
caused a live port-80 conflict (`pinet-portal` crash-looping on "Address
already in use") until it was noticed and the rebuild scope was narrowed
to just the bridge toggle on its own port. **If asked to touch this area
again, check `systemctl status pinet-board` and who's logged in
(`who`/`w`) before assuming you have the Pi to yourself** — per the
project's own concurrency rule, two writers should never share one
scope unclaimed.

## Original design history (still accurate for the bridge-toggle half)

**First status: fully removed**, at the user's request, later the same
session it was first built. All files, the `pinet-portal` system user,
the sudoers grant, and the dnsmasq captive-DNS override were deleted;
confirmed clean afterward (no leftover units/files/user, `ip_forward=0`,
no NAT rule, `/etc/dnsmasq.d/` back to just the original
`wlan0-ap.conf`). Kept this note for the architecture record and the
real bugs found during building it.

A captive portal that opens automatically when a phone joins the PINET
hotspot (see [[pi-eink-dashboard-hotspot]]), showing a page with a button
that bridges PINET to the internet -- gated behind a dedicated password,
never the Pi's root/sudo password (see "Why not the root password" below).

## Default state

**PINET is intranet-only by default, same as before this feature existed.**
The bridge starts (and returns to, after every `off`) a state where PINET
clients can reach the Pi but nothing beyond it -- bridging to the internet
is an explicit, password-gated, reversible action, not a new default.

## Architecture

- **DNS wildcard redirect**: `/etc/dnsmasq.d/wlan0-ap-captive.conf`
  (`address=/#/10.10.10.1`) makes dnsmasq answer *every* domain query from
  PINET clients with the Pi's own IP -- this is what makes any phone's
  captive-portal probe request (and literally any other HTTP request) land
  on the Pi regardless of what host it asked for. Present when the bridge
  is off; removed when the bridge is on (see below for why).
- **Catch-all web app**: `/opt/pinet-portal/app.py` (Flask, systemd service
  `pinet-portal.service`, listens on port 80). Every path on every host
  gets the same portal page (`templates/portal.html`) -- this is what
  actually triggers each OS's captive-portal sign-in sheet: Apple/Android/
  Windows each probe a specific URL expecting a specific "no portal here"
  response (e.g. Android expects a bare `204` from
  `/generate_204`), and getting our real HTML back instead is what makes
  the OS decide it's behind a captive portal and pop the browser
  automatically. No per-OS special-casing needed -- a genuine catch-all
  fails all of them the same way.
- **Privileged toggle, narrowly scoped**: `/usr/local/sbin/pinet-bridge
  on|off|status` (root-owned, mode 750) is the *only* thing the portal's
  backend can run as root, via `/etc/sudoers.d/020-pinet-portal` granting
  `NOPASSWD` to the `pinet-portal` system user for exactly those three
  invocations -- not blanket sudo, and specifically not routed through
  `rupal` (who has full `NOPASSWD:ALL` per [[pi-eink-dashboard-access]] --
  using that account for this would have defeated the whole point of a
  narrow grant). The script itself: enables `net.ipv4.ip_forward`, adds a
  `MASQUERADE`/`FORWARD` iptables rule pair from `10.10.10.0/24` out
  whatever the Pi's *current* default-route interface is (`wlan1` or
  `eth0` -- detected live via `ip route show default`, not hardcoded,
  since this Pi's WAN interface changes; see
  [[pi-eink-dashboard-access]]), and removes the DNS wildcard override +
  restarts dnsmasq so real domain resolution works once bridged (leaving
  the wildcard in place while "on" would mean the Pi answering DNS with
  its own IP for every domain even with a working route out -- silently
  breaking browsing rather than enabling it). `off` reverses all of it and
  restores the DNS wildcard.
- **Password storage**: `/etc/pinet-portal/portal.conf` (`salt:pbkdf2-hash`,
  mode `640`, `root:pinet-portal` -- unreadable by `rupal` or anyone else).
  Set/changed via `sudo python3 /opt/pinet-portal/set_password.py`
  (interactive `getpass` prompt, never appears in shell history). 200,000
  PBKDF2-SHA256 iterations, `hmac.compare_digest` for the check (constant-time,
  avoids a timing side-channel).
- **Rate limiting**: 5 wrong attempts from the same IP locks that IP out
  for 60s (in-memory, resets on service restart -- acceptable for this
  threat model: a handful of guest devices on a physical premises, not an
  internet-facing service).

## Why not the root password

The user's first framing of this request was to gate the bridge behind
the Pi's actual root password. Flagged and changed before building
anything, for two concrete reasons: (1) captive portals are plain HTTP --
phones don't trust self-signed TLS certs cleanly, so there's no good way
to encrypt this in transit, and (2) anyone else already on PINET shares
the same local network segment as whoever's submitting the password. A
dedicated, unrelated, single-purpose password confines the blast radius
of both of those to "someone can flip the internet bridge," not "someone
has root on the Pi."

## The `CapabilityBoundingSet` bug (found and fixed during QA)

First version of `pinet-portal.service` set both `AmbientCapabilities=
CAP_NET_BIND_SERVICE` (needed so the non-root `pinet-portal` user can bind
port 80) *and* `CapabilityBoundingSet=CAP_NET_BIND_SERVICE`. The bounding
set option cascades to every descendant process, including the `sudo`
child this service shells out to -- and `sudo`'s own internal
setuid/setgid transition to root needs capabilities well beyond
`CAP_NET_BIND_SERVICE`, so every privileged call failed with `sudo:
unable to change to root gid: Operation not permitted`, silently caught
by the app's exception handler and reported to the user as a generic
"Failed to change bridge state." Fixed by dropping the
`CapabilityBoundingSet=` override entirely -- `AmbientCapabilities` alone
is sufficient for the port-80 bind, and leaving the bounding set at its
default lets `sudo`'s child process regain full capabilities the moment
it becomes root, same as it would for any other service. Caught via
`app.logger.error`/`.exception()` calls added specifically to debug this
(kept in the shipped version -- this failure mode had been completely
silent before that).

## Dashboard integration — **INCORRECT, see correction at top of note**

~~[[dashboard.py]]'s hotspot carousel screen (`render_hotspot_screen`) now
shows live bridge status -- `get_bridge_active()` reads
`/proc/sys/net/ipv4/ip_forward` directly (world-readable, no sudo needed,
exactly the flag `pinet-bridge` toggles), bold "Internet: ON" or plain
"Internet: OFF (local only)" on its own row above the IP. Bounded to the
same reduced width as the device-count number and label when the join QR
is present (see [[fixes session log]] fix #11) -- the OFF-state text is
long enough to run into the QR's caption otherwise; caught during this
session's QA render, not after deploying.~~

Verified 2026-09-07 against the actual `dashboard.py`: no
`get_bridge_active()` function, no `ip_forward` reference, no
"Internet: ON/OFF" text anywhere in the file. `render_hotspot_screen`'s
real current signature is `(epd, hotspot, dark_mode=False)`, and it
only ever shows SSID, connected-device count, and a join QR/password —
never bridge status. Whatever this section originally described was
either never actually merged into the shipped code or was reverted
without this note being updated. Moot now that the bridge toggle is
gone entirely, but left visible (rather than deleted outright) as a
concrete example of this vault drifting from real code.

## Shelved: BitChat relay via the portal (2026-09-06)

Asked whether a "start BitChat server" button could be added to the
portal, using the Pi's onboard Bluetooth (BlueZ 5.82, hci0 confirmed
supports LE central+peripheral+advertising; Pi had ~249MB free RAM, load
0.18/4 cores at the time -- hardware was never the constraint). Checked
the actual upstream repo (github.com/permissionlesstech/bitchat) before
answering: it's a native Swift iOS/macOS app (Android has a separate
port) built directly on Apple's CoreBluetooth -- there is no server, no
daemon, no BlueZ/Linux target, and no documented BLE wire-protocol spec.
"Start it from the portal" would mean reverse-engineering their
Noise-protocol BLE mesh framing from the Swift source and writing an
original BlueZ-based Linux relay from scratch -- a real multi-day project,
not a feature toggle. Shelved by the user rather than commissioned as a
separate project. Revisit only if explicitly asked again; don't assume
the scope has changed without re-checking the upstream repo.

## Operational notes

- Change the portal password any time: `sudo python3
  /opt/pinet-portal/set_password.py` on the Pi.
- Check bridge state without the web page: `sudo /usr/local/sbin/pinet-bridge status`.
- `pinet-portal.service` is enabled (auto-starts at boot) but only
  matters while PINET (`hostapd`) itself is active -- see
  [[pi-eink-dashboard-hotspot]] for the hotspot's own current
  enabled/disabled state, which is independent of this feature.
- Not implemented: HTTPS (not practical for a captive portal -- see "Why
  not the root password" above), and no attempt to make the portal's
  in-app browser experience match every OS's captive-portal UI chrome
  pixel-for-pixel -- it's a plain mobile-responsive page, which is what
  every OS's captive browser renders regardless.
