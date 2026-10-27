# PINET Flows

> Permission-relevant journeys: auth checks, trust-boundary crossings, side effects.

## pinet-board login

**Actor:** any device on the PINET hotspot (10.10.10.0/24)  
**Precondition:** pinet-board.service running; TLS listener up on port 443  
**Outcome:** session cookie set; board accessible

1. Device connects to open `PINET` Wi-Fi (`wlan0`). dnsmasq wildcard DNS (`address=/#/10.10.10.1`) triggers captive portal on mobile OS.
2. Browser issues HTTP request → `https_only_on_the_air()` intercepts → serves `secure.html` pointing to `https://10.10.10.1/login`.
   - **Trust boundary:** HTTP → HTTPS. Loopback (`127.0.0.1`, `::1`) exempt (Pi's own kiosk browser).
3. `GET /login` → login form rendered.
4. `POST /login`:
   - Lockout check: `is_locked_out(request.remote_addr)` — 5 attempts / 60 s per IP (in-memory `_attempts` dict).
   - PBKDF2-SHA256 compare: admin password (`/etc/pinet-board/board.conf`) checked first, then guest (`guest.conf`). `hmac.compare_digest` for timing safety.
   - On success: `session["authed"] = True`, `session["role"]` (`"admin"` or `"guest"`), `session["cred"] = sha256(conf_bytes)`.
   - On failure: `record_attempt(ip, False)` — 5th failure sets `locked_until` 60 s from now.
5. Redirect to `?next=` path (validated: must start with `/`, no netloc).
6. Every subsequent request: `require_login()` calls `_session_valid()` — re-derives `_cred_tag` from live conf file; session ends automatically if the password file is replaced.

**Deny cases:**
- IP locked out → 429-style error with retry countdown.
- Wrong password → flash error, attempt recorded.
- HTTP from non-loopback while HTTPS is on → redirect page (not bare 301).
- `_session_valid()` fails after password change → `session.clear()` + redirect to login.

---

## pinet-board file upload

**Actor:** authenticated user (guest or admin)  
**Precondition:** valid session  
**Outcome:** file stored on USB drive at `/mnt/pinet-media/uploads/<token>_<safe_name>`

1. `require_login()` validates session; upload endpoint not exempt.
2. Pre-upload disk check: if `Content-Length` present, `free_disk_bytes() < content_length * 2 + MIN_FREE_BYTES` → 413 before spooling.
   - **Why 2×:** Werkzeug spools to `TMPDIR` (`/mnt/pinet-media/tmp`, same filesystem as uploads) before the app reads it; briefly 2× the file size is needed.
3. `MAX_CONTENT_LENGTH = 1 GiB` enforced by Werkzeug before body reaches app code.
4. `secure_filename()` (Werkzeug) strips path traversals from the user-supplied filename.
5. File saved as `<random_token>_<safe_filename>` to prevent enumeration. DB row inserted.
6. Files with scriptable extensions (`.html`, `.svg`, `.js`, etc.) are forced-download on `/view` with `X-Content-Type-Options: nosniff` to block stored XSS.

**Deny cases:**
- Unauthenticated → redirect to login.
- Disk full (2× guard) → 413 with error message.
- Werkzeug body limit exceeded → 413 before app code.

---

## pinet-board file delete (admin-only)

**Actor:** admin  
**Precondition:** admin session  
**Outcome:** file removed from disk and DB

1. `require_login()` validates session.
2. `is_admin()` checks `session["role"] == "admin"` — guest sessions get 403.
3. File row fetched from SQLite by ID; `stored_name` used to build the path.
4. `os.unlink(UPLOAD_DIR / stored_name)` + `db.execute("DELETE FROM files WHERE id = ?")`.

**Deny cases:**
- Guest session → 403.
- Non-existent ID → 404.

---

## Power shedding (kiosk mode)

**Actor:** `dsi-kiosk.sh` (user) / `pi-power-manager` (root daemon)  
**Precondition:** pi-power-manager running; kiosk-mode.d directory writable  
**Outcome:** 9 services stopped while kiosk runs; restored in reverse order after exit

1. `dsi-kiosk.sh` acquires `flock /run/power-shed.lock` (LOCK_EX) — prevents race with `kali-power-shed`.
2. Creates entry in `/run/user/1000/kiosk-mode.d/<kiosk-name>`.
3. `pi-power-manager` polls every 2 s; `kiosk_open()` returns True → calls `shed()`.
4. `shed()` (under LOCK):
   - Merges any pending `HANDOFF` from `kali-power-shed`.
   - Checks each `SHED_UNITS` entry with `systemctl is-active`; stops running ones.
   - `bluetooth.service` runtime-masked before stop (D-Bus activation re-starts a plain-stopped bluetoothd within ~0.1 s).
   - Persists stopped list to `/run/pi-power-manager/stopped.json` (atomic: tmp + rename).
   - Writes `"kiosk"` to `mode` file — e-ink reads this to show "KIOSK MODE ON".
5. Kiosk browser runs.
6. On kiosk exit: `dsi-kiosk.sh` removes its entry from `kiosk-mode.d`; releases LOCK.
7. `pi-power-manager` detects kiosk gone → calls `restore()`.
8. `restore()` (under LOCK, one unit per iteration):
   - Checks `PWR_LOW_N` GPIO pin (debugfs). If under-voltage, waits up to 5 s.
   - Pops last unit from stopped list, unmasks if needed, `systemctl start --no-block`.
   - 2 s gap between units to pace inrush current.
   - PINET units (pinet-board, dnsmasq, hostapd) left down if `/run/pinet-stopped` exists (deliberate `pinet-stop` was run).
   - Pentest units left in `/run/pentest-shed.list` if `/run/pentest-mode` exists — `wifi-pentest-stop` restores them.

**Side effects:** `stopped.json` written atomically; `mode` file updated; `UV_STATUS` file updated for e-ink.

---

## Battery guard / clean shutdown

**Actor:** `pinet-ups-guard` (root daemon)  
**Precondition:** INA219 UPS HAT present on I²C `0x43`  
**Outcome:** orderly shutdown with boot-on-power armed, or countdown cancelled if charger arrives

1. Reads INA219 voltage + current every 2 s via `smbus2`.
2. `decide()`: if `cell_v < 3.3 V` on battery for 60 s continuously:
   - `"warn"` action: writes deadline to `/run/pinet-ups-low` (atomic); `eth-share stop` (drops routing load); `wall` message to all terminals.
   - e-ink reads `/run/pinet-ups-low` deadline and shows countdown.
3. Subsequent readings: if `cell_v >= 3.4 V` (3.3 + 0.1 hysteresis) for 2 consecutive readings → `"cancel"` — removes `/run/pinet-ups-low`, `wall` message.
4. If deadline reached → `"shutdown"`:
   - Creates `/run/pinet-ups-arm-boot` marker file.
   - `systemctl poweroff`.
   - systemd-shutdown hook `pinet-ups-arm` writes `0x55` to MCU register `0x01` (arms boot-on-power) as the very last step before power cut.
5. MCU watches charging port; pulls GPIO3 low when charger connected → Pi reboots automatically.

**Trust boundary:** `pinet-ups-guard` reads debugfs (root-only) for voltage; publishes `UV_STATUS` to `/run` for the unprivileged e-ink daemon.

---

## Ethernet sharing

**Actor:** user (via `eth-share-gui` GUI or `eth-share` CLI with pkexec)  
**Precondition:** `wlan1` connected with a default route; Ethernet cable present  
**Outcome:** eth0 becomes a NAT router (10.42.0.0/24); optionally with Pi-hole ad-blocking

1. `eth-share start` → `_require_root()` (exits if `os.geteuid() != 0`).
2. `start_block_reason()` gate — pure function, unit-tested:
   - Pentest mode active (`/run/pentest-mode` exists) → blocked.
   - `wlan1` not connected or no default route → blocked.
   - `/run/pinet-ups-low` exists → blocked.
   - Battery on-battery AND < 25% → blocked.
3. `_ensure_profile()`: creates NetworkManager "PINET Ethernet Share" profile (shared IPv4 method) if absent.
4. `nmcli con up "PINET Ethernet Share"` — NM sets IP, runs dnsmasq, enables IP forwarding, sets up nftables NAT masquerade to wlan1.
5. Writes `/run/eth-share` flag file.
6. Optional: `eth-share adfree-on` starts `pihole-FTL`, drops a dnsmasq forward-to-FTL conf under `/etc/NetworkManager/dnsmasq-shared.d/`, reactivates the NM connection.

**Deny cases:** any `start_block_reason()` condition → stderr message + exit 3; no NM profile created yet on first run if `nmcli` fails.

---

## Pentest mode transition

**Actor:** user (`wifi-pentest-start` / `wifi-pentest-stop`)  
**Precondition:** `wlan1` present  
**Outcome:** `wlan1` in monitor mode; power shed; e-ink pirate banner

1. `wifi-pentest-start`: acquires `flock /run/power-shed.lock` (same LOCK as pi-power-manager).
2. `kali-power-shed`: stops `USER_UNITS` and `SYS_UNITS` (overlapping with `SHED_UNITS` in pi-power-manager); writes `/run/pentest-shed.list`.
3. Creates `/run/pentest-mode` flag.
4. Calls `iw dev wlan1 set type monitor` + `ip link set wlan1 up`.
5. Updates e-ink to pirate screen (reads `/run/pentest-mode`).
6. `wifi-pentest-stop`: restores units from `/run/pentest-shed.list`; removes `/run/pentest-mode`; `iw dev wlan1 set type managed`.
   - If a kiosk is also open: appends pentest-held units to `HANDOFF` → `pi-power-manager` restores them when kiosk closes.
