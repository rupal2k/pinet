# Security Audit — PINET

**Scope:** full repository  
**Date:** 2026-10-26  
**Method:** pm-ai-shipping:security-audit-static, intended-vs-implemented  
**Primary files reviewed:** `pinet-board/app.py`, `scripts/sbin/pi-power-manager`, `scripts/sbin/pinet-ups-guard`, `scripts/sbin/eth-share`, `scripts/sbin/wifi-pentest-start`, `etc/nftables/pinet-ap.nft`, `systemd/pinet-board.service`  
**Intent baseline:** `docs/architecture.md`, `docs/flows.md`, `docs/permissions.md`, `docs/variables.md`

---

## Findings

### `pinet-board/app.py`

**1. [LOW] Brute-force lockout state resets on process restart**

Evidence: `pinet-board/app.py:66`
```python
_attempts = {}  # ip -> (count, locked_until_monotonic)
```
Risk Level: Low  
Attack Scenario: An attacker makes 4 failed login attempts, then sends a crafted oversized request or causes a crash that triggers `Restart=on-failure` (3 s delay). After restart the `_attempts` dict is empty and they have a fresh 5-attempt window. Repeating this: 4 attempts + crash = effectively unlimited login attempts without triggering the lockout.  
Impact: Lockout bypass on the open hotspot; however, PBKDF2 with 200 k rounds makes each attempt slow (~0.2–0.5 s on a Pi 3B). Sustained brute-force is still expensive.  
Solution: Persist the lockout state to a small file in `/run/pinet-board/` (tmpfs) on every failed attempt. File survives in-process restarts; reboots clear it (acceptable on a single-device appliance). Or use `RestartPreventExitStatus=` to avoid restarting on crash paths that don't warrant retry.

---

**2. [LOW] Non-admin delete silently redirects instead of returning 403**

Evidence: `pinet-board/app.py:479`, `pinet-board/app.py:496`
```python
if not is_admin():
    return redirect(url_for("board"))
```
Risk Level: Low  
Attack Scenario: A guest calls `POST /delete/<id>` or `POST /delete-message/<id>`. The route returns a 302 to `/` rather than 403. The delete does not happen — the guard is correct — but the response gives no indication of failure. A programmatic client follows the redirect and gets a 200 with the board HTML, appearing to succeed.  
Impact: No data loss (delete is blocked). However HTTP semantics are incorrect — a 403 is the expected response. Automated security scanners or integration tests may miss this boundary as a result.  
Solution: Return `abort(403)` instead of `redirect(url_for("board"))` on the unauthorized delete paths. The Jinja2 template already hides delete controls from guests; the 403 path is only reached by direct API calls.

---

**3. [LOW] No Content-Security-Policy header**

Evidence: `pinet-board/app.py` — no `after_request` hook or response header setting CSP.  
Risk Level: Low  
Attack Scenario: The anonymous message board accepts user text posted to the database. Jinja2's autoescaping prevents straightforward stored XSS; however, if a stored message or filename were rendered through a template that disabled autoescaping (`| safe`), or in an `<a href>` attribute with `javascript:` injection, the browser has no CSP backstop.  
Impact: No confirmed XSS vector found. Defense-in-depth gap.  
Solution: Add a permissive-but-explicit CSP via `@app.after_request`:
```python
resp.headers["Content-Security-Policy"] = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'"
)
```
`unsafe-inline` is needed for the existing inline `<style>` blocks in templates; tighten later by moving styles to the stylesheet.

---

**4. [LOW] Upload disk guard skips when `Content-Length` header is absent**

Evidence: `pinet-board/app.py:309`
```python
if request.endpoint == "upload_file" and request.content_length:
    needed = request.content_length * 2 + MIN_FREE_BYTES
    if free_disk_bytes() < needed:
        return ..., 413
```
Risk Level: Low  
Attack Scenario: A client sends a multipart upload without a `Content-Length` header (e.g. chunked transfer encoding). The pre-upload disk check is skipped. Werkzeug still enforces `MAX_CONTENT_LENGTH = 1 GiB`, and the upload goes to `TMPDIR` on `/mnt/pinet-media` — same filesystem — before the app saves it. If the disk has between 500 MB and 1 GB free, the upload could exhaust the remaining disk space.  
Impact: Potential disk exhaustion on `/mnt/pinet-media` if an attacker can stream a large upload without declaring `Content-Length`.  
Solution: After `f.save(dest)`, re-check `free_disk_bytes() < MIN_FREE_BYTES` and delete the just-saved file + DB row if the margin is violated. This is a post-save guard that doesn't depend on `Content-Length`.

---

**5. [INFO] `wlan0` guest-to-guest traffic unrestricted**

Evidence: `etc/nftables/pinet-ap.nft` — only drops TCP 22 and 5900 inbound to the Pi; no rules on guest-to-guest traffic.  
Risk Level: Info  
Attack Scenario: Two mobile devices on the PINET hotspot can ARP-scan and communicate directly with each other. On a public event hotspot this would allow guest enumeration and local network attacks between guests.  
Impact: For a personal device used in trusted company, this is acceptable. For a public venue deployment, it allows guest-to-guest attacks (ARP poisoning, local service probing).  
Solution: Add a forward-drop rule for wlan0→wlan0 if deployment context requires it:
```
chain forward {
    type filter hook forward priority filter; policy accept;
    iifname "wlan0" oifname "wlan0" drop
}
```

---

**6. [INFO] TLS certificate is self-signed; no HSTS**

Evidence: `pinet-board/app.py:44–47` (`TLS_CERT`, `TLS_KEY`); `docs/variables.md`  
Risk Level: Info  
Attack Scenario: Mobile captive portal UIs show a certificate warning. A guest on the open hotspot (already a fully attacker-controlled RF environment) could present their own cert instead. No HSTS header prevents downgrade. However the `secure.html` redirect page is served over HTTP to guide guests to HTTPS — this page itself cannot be HTTPS.  
Impact: Acceptable for a single-device personal appliance. Not a code defect.  
Solution: Document in `variables.md` pre-deploy checklist (done). Add `Strict-Transport-Security` header to HTTPS responses to prevent downgrade for returning clients.

---

## What is well-built

- **PBKDF2-SHA256 with 200 k rounds** (`pinet-board/app.py:193`) — strong for a Pi 3B; each attempt takes ~0.2–0.5 s.
- **`hmac.compare_digest`** for password comparison — timing-safe.
- **Credential tag invalidation** (`_cred_tag`) — changing the password file immediately ends all sessions without a server restart or revocation list.
- **`secure_filename()`** for uploads — strips path traversals; random token prefix prevents enumeration.
- **`X-Content-Type-Options: nosniff`** on all file responses — prevents MIME-sniffing of uploads.
- **Forced download for scriptable types** (`_FORCE_DOWNLOAD_EXT`) — `.html`, `.svg`, `.js` etc. are always sent as attachments.
- **`TMPDIR` override** — Werkzeug spool goes to `/mnt/pinet-media/tmp` (real disk), not the 463 MB tmpfs.
- **`pinet-board` system user** — process has no root capabilities beyond `CAP_NET_BIND_SERVICE`.
- **nftables `pinet_ap` table** — SSH and VNC dropped at the firewall before reaching the service.
- **Power manager flock mutex** — `pi-power-manager` and `kali-power-shed` coordinate via `flock /run/power-shed.lock`; no power-shed race condition possible.
- **Atomic state writes** — `stopped.json`, `UV_STATUS`, `LOW_FLAG` all use tmp + `replace()` pattern.
- **`eth-share` pre-flight gate** — pure `start_block_reason()` prevents routing start during pentest mode, UPS low, or insufficient battery.
- **`set -e` in `wifi-pentest-start`** with `restore_managed` ERR trap — failed monitor mode switch hands `wlan1` back to NetworkManager rather than leaving it down.

## OWASP Top 10 coverage

| Category | Status | Notes |
|---|---|---|
| A01 Broken Access Control | ✅ audited | Finding #2: silent redirect vs. 403 |
| A02 Cryptographic Failures | ✅ no issues | PBKDF2-SHA256, hmac.compare_digest, credential tag |
| A03 Injection | ✅ no issues | SQLite parameterized queries; secure_filename on uploads |
| A04 Insecure Design | ✅ finding #1 | Lockout persistence gap |
| A05 Security Misconfiguration | ⚠️ finding #3 | No CSP header |
| A06 Vulnerable Components | ✅ no issues at review date | Flask, Werkzeug — no known CVEs observed |
| A07 Authentication and Session | ✅ well-implemented | PBKDF2, cred tag, session.permanent |
| A08 Software/Data Integrity | ✅ no issues | Atomic writes; upload token prefixes |
| A09 Logging and Monitoring | ⚠️ low concern | No structured auth audit log; Flask default logging only |
| A10 SSRF | ✅ not applicable | No outbound requests from pinet-board |

## What could not be verified

- **Jinja2 template XSS safety**: the templates (`board.html`, `_message.html`, `_file.html`) were not read in full. Jinja2 autoescaping is on by default for `.html` templates; any `| safe` usage in templates would bypass it.
- **Pi-hole FTL API trust**: `eth-share` reads `http://127.0.0.1:8089/api/stats/summary` and passes values to `print()`. If FTL returns unexpected JSON structure, `_dig()` returns `None` safely. No injection risk found, but FTL's API authentication was not verified.
- **NetworkManager profile security**: `eth-share` creates a NetworkManager connection profile named `"PINET Ethernet Share"`. If another process creates a profile with the same name, `_ensure_profile()` would skip creation and `nmcli con up` would use the attacker's profile. Risk is low (root-only access to NetworkManager).
