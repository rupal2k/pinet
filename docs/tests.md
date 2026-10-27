# Test Coverage — PINET

> Which documented rules are pinned by tests today, which are proposed, and which have no verification.

**Suite:** `tests/` — 301 stdlib `unittest` tests, 12 files  
**Run:** `python3 -B -m unittest discover -s tests -v`  
**Gate:** run on Linux/WSL2 only (POSIX shell stubs, forward-slash paths)

---

## Existing coverage

Rules the test suite pins today.

| Use case | Rule | Expected behavior (+ deny case) | Evidence | Type | Status |
|---|---|---|---|---|---|
| Login lockout | 5 failures → 60 s lockout per IP | 5th failure locks; after 60 s unlocks; success clears counter | `pinet-board/app.py:is_locked_out,record_attempt` / `tests/test_pinet_board.py:Lockout` | unit | **existing** |
| Login lockout | Lockout is per-IP | IP A locked; IP B is not locked | `tests/test_pinet_board.py:Lockout.test_lockout_is_per_ip` | unit | **existing** |
| Login lockout | Locked state never reports 0 s remaining | Remaining ≥ 1 s when locked | `tests/test_pinet_board.py:Lockout.test_locked_never_reports_zero_seconds` | unit | **existing** |
| Session validity | Cred tag matches live conf file | Valid after login; invalid after password change | `pinet-board/app.py:_cred_tag,_session_valid` / `tests/test_pinet_board.py:SessionValid` | unit | **existing** |
| Session validity | Role claim cannot be elevated by tamper | Guest cookie with `role=admin` fails `_session_valid()` | `tests/test_pinet_board.py:SessionValid.test_guest_cookie_is_not_valid_as_admin` | unit | **existing** |
| Session validity | Missing conf file ends session | `guest.conf` deleted → session invalid | `tests/test_pinet_board.py:SessionValid.test_missing_conf_file_is_not_valid` | unit | **existing** |
| HTTPS redirect | Non-loopback HTTP is redirected | HTTP from 10.10.10.x with HTTPS on → redirect | `pinet-board/app.py:needs_https` / `tests/test_pinet_board.py:NeedsHttps` | unit | **existing** |
| HTTPS redirect | Loopback and HTTPS-off exempt | 127.0.0.1, ::1, HTTPS_ON=False → no redirect | `tests/test_pinet_board.py:NeedsHttps` | unit | **existing** |
| File type classification | Scriptable extensions never viewable inline | `.html`, `.svg`, `.js`, `.xml` → `_file_kind = "other"` | `tests/test_pinet_board.py:FileKind.test_active_content_is_never_viewable` | unit | **existing** |
| Admin-only delete | Delete controls hidden from guests in template | `{% if is_admin %}` wraps delete form | `tests/test_pinet_board.py:BoardTemplate.test_delete_controls_are_admin_only` | unit | **existing** |
| Admin-only delete | Route checks `is_admin()` twice | `if not is_admin(): return redirect` in both delete routes | `tests/test_pinet_board.py:BoardTemplate.test_delete_controls_are_admin_only` (route count) | unit | **existing** |
| Disk space guard | `storage_stats` uses correct path and math | `os.statvfs` called on UPLOAD_DIR; total/free/used_pct correct | `tests/test_pinet_board.py:StorageStats` | unit | **existing** |
| Disk space guard | Zero total does not divide by zero | 0 total → `used_pct = 0.0`, no exception | `tests/test_pinet_board.py:StorageStats.test_zero_total_does_not_divide_by_zero` | unit | **existing** |
| Live poll | Poller endpoint matches route; returns 401 on expired session | `/api/state` endpoint returns `"", 401` when `api_state` endpoint | `tests/test_pinet_board.py:LiveMessages.test_poller_endpoint_matches_and_401s_a_dead_session` | unit | **existing** |
| Power shed | Shed stops running units; persists stopped list | `shed()` writes `stopped.json`; only active units stopped | `tests/test_pi_power_manager.py:PowerManagerCase` | unit | **existing** |
| Battery guard | `decide()` returns correct action at threshold | `cell_v < 3.3 V` → `warn`; `>= 3.4 V × 2` → `cancel`; deadline elapsed → `shutdown` | `tests/test_pinet_ups_guard.py` | unit | **existing** |
| eth-share gate | `start_block_reason()` blocks on pentest/ups-low/battery-low | Each block condition returns non-None reason | `tests/test_eth_share.py` | unit | **existing** |
| Battery math | INA219 voltage→percentage interpolation | Voltage at 4.2 V → 100%; 3.3 V → 0%; midpoints interpolated | `tests/test_pinet_battery.py` | unit | **existing** |
| Shell script syntax | All bash scripts pass `bash -n` | No syntax errors | `tests/test_shell_scripts.py` | unit | **existing** |
| Repository consistency | Paths in `.desktop`, `systemd`, scripts exist in repo | No dangling references | `tests/test_consistency.py` | unit | **existing** |

---

## Proposed tests

Recommended cases not yet written. Grouped by the doc/flow they defend.

### pinet-board: auth and session (defends `flows.md` — login flow, `permissions.md`)

**P1 — `open_redirect_validation` (unit)**  
*Rule:* `?next=` must start with `/` and have no netloc.  
Arrange: `needs_https` already tested; this tests the `POST /login` redirect validation.  
Assert:  
- `next=//evil.com` → redirect to `/` (board), not `//evil.com`
- `next=\evil.com` → redirect to `/`
- `next=/safe/path` → redirect to `/safe/path`
- `next=http://evil.com` → redirect to `/`  
Negative: `next=` absent → redirect to `/` (default).

**P2 — `delete_returns_redirect_not_403` (unit, route-level)**  
*Rule:* `permissions.md` documents that guest delete → redirect to board (not 403).  
Arrange: Flask test client with a guest session.  
Assert: `POST /delete/<id>` returns 302 → `/`, not 200 or 403.  
Negative: Admin session → actual delete + redirect to `/?ok=file-deleted`.  
*Note:* Prevents future refactors from silently allowing the delete or changing response semantics.

**P3 — `post_save_disk_guard` (integration, requires temp filesystem)**  
*Rule:* Upload blocked if `free_disk_bytes() < MIN_FREE_BYTES` after save (the `Content-Length`-absent path).  
Arrange: Mock `os.statvfs` to report < 500 MiB free after `f.save()`.  
Assert: File deleted from `UPLOAD_DIR`; DB row not committed; response is 413.  
Negative: Sufficient space → upload succeeds.  
*Why not existing:* The pre-upload `Content-Length` guard is tested implicitly; the post-save guard is not.

### pinet-board: file handling (defends `flows.md` — upload, `permissions.md`)

**P4 — `force_download_at_view_route` (route-level)**  
*Rule:* Files with scriptable extensions must be sent as attachments from `/view/<id>`.  
Arrange: Upload a `.html` file; fetch `/view/<id>`.  
Assert: `Content-Disposition` header starts with `attachment`; `X-Content-Type-Options: nosniff` present.  
Negative: `.png` file at `/view/<id>` → `Content-Disposition: inline` (or absent).  
*Note:* `_file_kind("x.html") == "other"` is already tested; this tests the route wires `as_attachment` correctly.

### Power manager (defends `flows.md` — power shedding)

**P5 — `restore_skips_pinet_when_pinet_stopped` (unit)**  
*Rule:* `flows.md` step 8: PINET units left down if `/run/pinet-stopped` exists.  
Arrange: `stopped.json` contains `pinet-board.service`, `hostapd.service`, `dnsmasq.service`; `/run/pinet-stopped` present.  
Assert: After `restore()`, those three units are NOT passed to `systemctl start`.  
Negative: Without `/run/pinet-stopped`, all units are started.

**P6 — `pentest_handoff_appended_on_restore` (unit)**  
*Rule:* `flows.md` pentest transition step 6: pentest-held units handed to `HANDOFF` when kiosk also open.  
Arrange: `pentest-shed.list` present; `/run/pentest-mode` absent; kiosk still open.  
Assert: `restore()` appends pentest units to `HANDOFF` instead of starting them directly.

### Battery guard (defends `flows.md` — battery guard flow)

**P7 — `decide_hysteresis_requires_two_good_readings` (unit)**  
*Rule:* `flows.md` step 3: `>= 3.4 V × 2 consecutive readings` before cancel.  
Arrange: `decide()` called with `warn` state, then one `cell_v = 3.4 V`, then one `cell_v = 3.4 V`.  
Assert: First call with 3.4 V returns `"ok"` (not yet cancel); second call returns `"cancel"`.  
*Note:* Verify the `ok_count >= 2` guard is tested, not just a single-reading cancel.

### eth-share (defends `flows.md` — ethernet sharing)

**P8 — `start_blocked_when_eth_carrier_absent` (unit)**  
*Rule:* `start_block_reason()` blocks when `wlan1` has no uplink.  
Arrange: stub `eth_carrier` to return False.  
Assert: `start_block_reason()` returns a non-None string.  
*Note:* May already be covered in `test_eth_share.py` — verify before writing.

---

## Gate

**Stated policy:** `CONTRIBUTING.md` — `python3 -B -m unittest discover -s tests -v` + `bash -n` for shell scripts. Human go-ahead required; no CI configured.

**Deterministic local set:** all 301 existing tests (units + shell syntax). No live services required.

**Recommended CI** (not currently installed): a GitHub Actions workflow running the test suite on Ubuntu-latest (Linux required for POSIX stubs) on every push to `main` and every pull request. A minimal `ci.yml`:

```yaml
name: tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - run: python3 -B -m unittest discover -s tests -v
      - run: bash -n scripts/bin/* scripts/sbin/* 2>&1 | grep -v "^$" && true
```

This is a suggestion for the owner's approval — no workflow file has been created.

---

## Gaps — documented rules with no verification

Ranked by what crossing them exposes.

| Rule | Doc | Gap type | Exposure if violated |
|---|---|---|---|
| **Admin-only delete returns redirect (not 403) at the route level** | `permissions.md` | No route-level test for response type | Future refactor accidentally allows guest delete, or changes 302→200 masking a bypass |
| **`?next=` redirect validation** | `flows.md` — login | No test for `//evil.com`, `\evil.com` cases | Open redirect: after login, user sent to attacker's domain |
| **`/view/<id>` forces download for scriptable extensions** | `flows.md` — upload | `_file_kind` tested; route behavior not tested | Stored XSS via uploaded `.html` served inline |
| **Brute-force lockout not reset on restart** | `permissions.md` (noted as gap) | No test for persistence across restart | Lockout bypass by triggering process restart |
| **`flock /run/power-shed.lock` mutex** | `CLAUDE.md` trust boundaries | No test for concurrent lock contention | Race between pi-power-manager and kali-power-shed on `stopped.json` |
| **`TMPDIR` exists at upload time** | `variables.md` pre-deploy | Manual checklist only; no service-level guard | All uploads fail with 500 after USB drive remount |
| **SQLite WAL mode** | Not documented | Not configured; not tested | Concurrent read stall during write under multiple polling guests |
| **nftables `pinet_ap` table loaded on boot** | `permissions.md` | Manual: `nft list ruleset \| grep pinet_ap` | SSH/VNC exposed to hotspot guests if rule not loaded |
| **INA219 I²C address `0x43` reachable** | `variables.md` / `docs/Device Overview.md` | No integration test (requires hardware) | Battery guard never fires; no graceful shutdown on battery drain |
| **Session cookie `Secure` flag on HTTPS** | `flows.md` — login | Not tested; behavior depends on `HTTPS_ON` flag | Session cookie transmitted in plaintext on open hotspot when TLS not configured |
