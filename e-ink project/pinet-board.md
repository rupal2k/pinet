---
tags: [project, raspberry-pi, e-ink, hotspot, security]
---

# PINET board -- anonymous message board + file drop (2026-09-06)

Built after removing [[pinet-captive-portal]] (the internet-bridge
feature) same session. A captive portal opens automatically on joining
PINET, same DNS-wildcard mechanism as before, but this time serves a
message board (no accounts, anonymous posts) and a file drop (upload/
download up to 1GB) instead of a network-bridging toggle.

## Scope decisions, in the order the user actually gave them

The requirements shifted twice mid-build -- worth recording since a
future session might otherwise "fix" this back to an earlier stated
version:

1. First framed as "piratebox file transfer... allow files up to 2GB" --
   asked whether to gate it with the portal password or leave it fully
   open (classic PirateBox is anonymous/no-login). User picked **same
   portal password**.
2. Redefined shortly after to "anonymous messaging portal with file
   transfer up to 1GB" -- the word "anonymous" directly contradicted the
   just-made password decision, so asked again specifically: fully open,
   or keep the password? User picked **keep the password**. Final
   resolved meaning of "anonymous": no accounts/no per-post identity,
   *not* no-password -- the whole board sits behind one password gate,
   but nothing posted or uploaded is attributed to anyone.
3. **1GB**, not 2GB, is the final, current limit (`MAX_CONTENT_LENGTH` in
   `app.py`) -- the 2GB number was only ever mentioned in the first,
   superseded framing.

## Architecture

- **No sudo, no privileged actions at all** -- a deliberate simplification
  versus the removed bridge feature, which needed a sudoers rule +
  root-privileged script to toggle NAT/iptables. This board is a plain
  Flask app; removing the privilege-escalation path removes the whole
  class of risk that produced the `CapabilityBoundingSet` bug in
  [[pinet-captive-portal]].
- **`pinet-board.service`** (Flask, port 80, dedicated system user
  `pinet-board`, `AmbientCapabilities=CAP_NET_BIND_SERVICE` for the
  non-root port-80 bind -- no `CapabilityBoundingSet=` override, learned
  from the earlier bug, though it wouldn't have mattered here without
  sudo anyway).
- **Session-based login**, not per-action passwords: enter the portal
  password once at `/login`, get a signed session cookie
  (`app.secret_key` from `/etc/pinet-board/secret_key`, pre-generated at
  install time -- the app user only ever *reads* `/etc/pinet-board/`,
  never writes to it, see the bug below), then view/post/upload/download
  freely for that session. Much more usable than gating every individual
  post, which the earlier one-shot bridge-toggle design didn't have to
  consider.
- **Password storage**: `/etc/pinet-board/board.conf`
  (`salt:pbkdf2-hash`, mode 640, `root:pinet-board`), same PBKDF2-SHA256
  (200k iterations) + `hmac.compare_digest` approach as the removed
  bridge portal. Change via `sudo python3 /opt/pinet-board/set_password.py`.
- **Messages**: SQLite (`/opt/pinet-board/data/board.db`), a single
  `messages` table, no editing/deleting from the UI (by design -- keeps
  it simple, matches "anonymous drop" spirit).
- **Files**: stored at `/opt/pinet-board/uploads/` with a random-prefixed
  filename (`secrets.token_hex(8)_<original name>`) to avoid collisions
  and path-traversal tricks (`secure_filename()` also applied), metadata
  (original name, size, timestamp) in a `files` SQLite table.
- **Catch-all route**: any unmatched path redirects to the board or
  login, same mechanism the removed bridge portal used to make every
  OS's captive-portal probe trigger the auto-popup sign-in sheet
  (Apple/Android/Windows all expect a specific "no portal" response on
  specific probe URLs; getting redirected instead is what makes them
  decide there's a portal).

## The `/tmp` tmpfs trap (found and fixed before it could bite)

**This Pi's `/tmp` is a 463MB RAM-backed tmpfs**, not disk
(`mount | grep tmp` -- `tmpfs on /tmp type tmpfs ... size=463416k`).
Flask/Werkzeug spools multipart file uploads to a temp file via Python's
`tempfile` module *before* application code ever sees them, and
`tempfile` defaults to `TMPDIR` or the system temp dir -- i.e. `/tmp` on
this box, by default. A 1GB upload would have either blown straight
through the tmpfs's 463MB cap (upload fails) or, worse, actually
consumed 463MB+ of real RAM on a Pi with only ~900MB total, likely
triggering exactly the kind of OOM/thrashing behavior this session's
[[power and undervoltage]] investigation was already worried about.

Fixed via `Environment=TMPDIR=/opt/pinet-board/tmp` in the systemd unit
-- a directory on the real disk (4.5GB free), owned `pinet-board:pinet-board`.
Verified two ways: (1) a 200MB test upload kept available RAM basically
flat (561Mi -> 542Mi) versus a mistaken *test-file-creation* command that
accidentally wrote to `/tmp` directly and nearly exhausted RAM (down to
~100Mi available) before failing outright with "No space left on
device" at 453MB -- a useful accidental demonstration of exactly the
failure this fix prevents; (2) `du` on `/opt/pinet-board/tmp/` after a
completed upload showed it empty (Werkzeug cleans up its own temp file
correctly at request teardown), confirming no leak.

**Disk-space accounting accounts for this doubling**: the app's
`before_request` check for `/upload` rejects based on
`content_length * 2 + MIN_FREE_BYTES`, not just `content_length` --
because the incoming file briefly exists twice (once in Werkzeug's
TMPDIR-redirected temp file, once again after `f.save()` copies it into
`UPLOAD_DIR`) before the temp copy is cleaned up.

## Bugs found and fixed during install (before going live)

1. **`unable to open database file`** -- `BASE_DIR` (`/opt/pinet-board`)
   is root-owned 755; the `pinet-board` user could traverse into it but
   not create new files there, so `sqlite3.connect()` on a DB path
   directly under `BASE_DIR` failed. Fixed by moving the DB into a
   dedicated `data/` subdirectory, pre-created and owned
   `pinet-board:pinet-board` at install time (same pattern as
   `uploads/`), rather than trying to make the app write into a
   root-owned directory.
2. **`PermissionError` writing `/etc/pinet-board/secret_key`** at
   startup -- the app originally tried to generate its own session
   secret key on first run if missing, but `/etc/pinet-board` is
   `root:pinet-board 750` (no write for the app's own group in the
   directory sense that matters for file creation... actually the real
   issue: the *directory* needs group-write for the group to create
   files in it, and it didn't have that, deliberately, to keep
   `board.conf`'s hash file safe from being clobbered by a compromised
   app process). Fixed by pre-generating the secret key file as part of
   install (root-owned, `pinet-board`-group-readable, mode 640) --
   consistent with the general principle applied throughout this
   feature: the app process should only ever need *read* access to
   anything under `/etc/pinet-board/`, never write.
3. **`/etc/pinet-board` traversal blocked for `rupal`** -- once the
   board password needed to be shown on the e-ink hotspot screen (see
   below), `dashboard.py` (running as `rupal`) couldn't even traverse
   into `/etc/pinet-board` (`750 root:pinet-board`, and `rupal` isn't in
   that group) to read the one file it needed. Fixed with
   `chmod 751 /etc/pinet-board` -- execute-only for "other", which
   allows traversal into a *known* filename but not listing the
   directory's contents, so `board.conf`'s hash file and the secret key
   still can't be discovered/read by `rupal`, only the one file
   deliberately made group-readable by it.

## Dashboard integration: password shown next to the Wi-Fi join QR

User asked for the board's password to be "relayed with the same QR"
used to join PINET's Wi-Fi. Flagged one real constraint before building
it: the Wi-Fi join QR uses the standard `WIFI:T:WPA;S:...;P:...;;` format
that phone camera apps parse natively to auto-join -- stuffing extra
custom fields into that same QR string risks breaking that native
recognition unpredictably across phones/OSes. Agreed instead to show the
board password as separate plaintext right next to the same QR, so
scanning + reading the screen together gives a guest everything in one
glance without touching the QR encoding itself.

Since the app only stores a one-way salted hash (by design), showing the
literal password required a second, deliberate plaintext copy:
`/opt/pinet-board/set_password.py` now also writes
`/etc/pinet-board/board_password_plaintext.txt` (root-owned,
`rupal`-group-readable, mode 640) purely for `dashboard.py`'s
`get_board_password()` to read -- the web app's own auth check never
touches this file, only the hash in `board.conf`. Same "physical display
only" trust model already used for the Wi-Fi password
(`get_hotspot_passphrase()` reads it live, in plaintext, from hostapd's
own config) -- anyone who can read the e-ink panel already has physical
presence, which is the actual security boundary here, not the password's
storage format.

**Layout bug caught in QA, fixed before deploying**: first attempt put
the "Board: <password>" text in the QR's own ~76px-wide column (same
spot as the "scan to join" caption) -- `rupalbgmi2671` truncated to
`Board: rupalbgm..`, unreadable and useless for actually logging in.
Fixed by moving it to its own full-width row (`W - 20 - qr_reserved`
available, not just the QR's narrow column) -- specifically the row
freed up when [[pinet-captive-portal]]'s "Internet: ON/OFF" bridge-status
line was deleted along with that whole feature. Verified via
`icon_gallery`-style ad-hoc render before deploying, both light and dark
mode.

**Also removed while touching this code**: `get_bridge_active()` and its
`bridged` field, dead code left over from the deleted internet-bridge
feature -- `render_hotspot_screen` no longer references anything from
the removed [[pinet-captive-portal]] subsystem at all.

## Operational notes

- Change the board password: `sudo python3 /opt/pinet-board/set_password.py`
  on the Pi (also updates the e-ink display copy automatically).
- Files live at `/opt/pinet-board/uploads/`, messages in
  `/opt/pinet-board/data/board.db` -- no automatic cleanup/retention
  policy exists; if disk fills up, the app's own pre-upload check will
  start rejecting new uploads once free space drops below ~500MB, but
  old content is never auto-deleted.
- `pinet-board.service` is enabled (auto-starts at boot) but, like
  [[pinet-captive-portal]] before it, only matters while PINET
  (`hostapd`) is actually active -- see [[pi-eink-dashboard-hotspot]]
  for the hotspot's own enabled/disabled state.

---

## Update 2026-09-12 -- in-browser file viewing + responsive tabbed UI

Full details in [[fixes session log]] entry 13. Summary:
- **New `/view/<id>` route** serves uploads **inline** (images, PDF, video,
  audio, text render in the browser) instead of only downloading. Uses
  `send_from_directory(as_attachment=False)` + `mimetypes.guess_type`.
- **Security**: scriptable types (`html/htm/xhtml/shtml/svg/svgz/xml/js/mjs`)
  are force-downloaded even from `/view`, and every `/view` response sends
  `X-Content-Type-Options: nosniff` -- prevents an uploaded file executing
  script in the board origin (session-cookie theft). `/download/<id>`
  (attachment) is unchanged. `/view` is behind the same `before_request` auth
  gate as everything else.
- **UI**: real Messages/Files **tabs** (JS-switched, both panels visible if JS
  off), Files shown as a **responsive card grid** with image thumbnails and
  View/Get actions; container widened for desktop, still mobile-friendly.
  Touches `board.html`, `style.css`, `app.js`; adds `_file_kind()`/`_file_ext()`
  helpers + a `filesize_str` filter in `app.py`.
- Verified via Flask test client (authed session) + live curl. Backups
  `.bak-20260912060031`. Reminder: **pinet-board is not under git** -- backups
  are the only history.

---

## Update 2026-09-12 (later) -- guest/admin roles + admin-only file delete

Added a two-tier login. The existing `board.conf` password is now the **admin**
role; a new optional `guest.conf` password is the **guest** role.
- **Login**: single password field, unchanged UX -- whichever password matches
  sets `session["role"]` ("admin" or "guest"). `check_password()` now takes a
  conf path; login tries admin then guest. Absent `guest.conf` = no guest tier
  (graceful). Added `/logout`.
- **Admin-only delete**: new `POST /delete/<id>` route, guarded by `is_admin()`
  (`session["role"]=="admin"`); removes the DB row + the file on disk. POST-only
  so a GET/prefetch/link can't trigger it. A `@app.context_processor` exposes
  `role`/`is_admin` to templates.
- **UI** (`board.html`/`style.css`/`app.js`): a header session bar shows an
  Admin/Guest badge + Log out; file cards show a red Delete button (with a JS
  confirm) **only for admin**. Guests never see it and the route rejects them.
- **Guest password**: set with the new interactive helper
  `sudo /opt/pinet-board/set_guest_password.py` (mirrors `set_password.py`;
  writes `guest.conf` 640 root:pinet-board). Not set yet as of this note, so
  guest login is inactive until the user runs it.
- Verified via Flask test client (as the pinet-board user): admin sees/uses
  delete, guest is blocked at both UI and route level; tested on a throwaway
  file so no real upload was touched. Service restarted clean, NRestarts=0.
  Backups `.bak-<ts>`.

**OPEN SECURITY CONSIDERATION (not yet acted on)**: the e-ink hotspot screen
still displays the *admin* board password (via `board_password_plaintext.txt`,
see [[dashboard.py]]/[[systemd service]]). With admin now able to delete, showing
it on a screen anyone near the Pi can read hands admin to any passer-by. The
e-ink screen should instead show the *guest* password. That needs an e-ink repo
change (guest plaintext file + dashboard.py) -- flagged for the user.

**RESOLVED 2026-09-12**: the "e-ink shows admin password" concern above is
fixed -- guest password set and [[dashboard.py]] `get_board_password()` now
displays the guest password (commit `00c5be0`, e-ink repo). See
[[fixes session log]] entry 18.
