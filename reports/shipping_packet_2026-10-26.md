# Shipping Packet — PINET

**Repository:** `D:\Agentic projects\pinet`  
**Date:** 2026-10-26  
**Method:** pm-ai-shipping:ship-check — Steps 1–7 completed inline

---

## Documentation Inventory

| Doc | Path | Status | Notes |
|---|---|---|---|
| Architecture | `docs/architecture.md` | **created** this session | System overview, stack, trust boundaries, known risks |
| Flows | `docs/flows.md` | **created** this session | 6 flows: login, upload, delete, power-shed, battery-guard, eth-share, pentest |
| Permissions | `docs/permissions.md` | **created** this session | Role matrix, nftables rules, code-enforced checks |
| Variables | `docs/variables.md` | **created** this session | Secrets, env vars, /run flags, pre-deploy checklist |
| Tests | `docs/tests.md` | **created** this session | Coverage map: existing/proposed/gaps |
| Agent instructions | `CLAUDE.md` | **updated** this session | Trust boundaries, corrected subsystems table, docs table |
| Security report | `reports/security_audit_2026-10-26.md` | **created** this session | 4 LOW + 2 INFO findings |
| Performance report | `reports/performance_audit_2026-10-26.md` | **created** this session | 4 findings |
| Device overview | `docs/Device Overview.md` | pre-existing | — |
| emails.md | — | **n/a** | pinet-board sends no email |
| cron.md | — | **n/a** | No scheduled jobs; systemd units are event-driven |
| seo.md | — | **n/a** | pinet-board is a private LAN portal, not indexable |
| automation.md | — | **n/a** | No embedded AI agents or LLM calls |

---

## Agent Context

**File edited:** `CLAUDE.md` — updated (this session)  
**Changes:** Added "Trust boundaries — do not bypass" section (5 invariants); corrected subsystems table with privilege column and missing rows (`pinet-ups-guard`, `pinet-board`); added system documentation table pointing to the 4 new docs.

The CLAUDE.md is the single agent instruction file for this repo (no separate `AGENTS.md`). It is the canonical operating context for the next AI coding session.

---

## Test Coverage

**Current suite:** 301 tests across 12 files — all stdlib `unittest`, Linux-only.  
**Gate:** local `python3 -B -m unittest discover -s tests -v` + `bash -n` per `CONTRIBUTING.md`. No CI configured.

**Existing coverage highlights:**
- Full lockout logic (5 attempts, 60 s, per-IP, success-clears)
- Session validity and cred-tag invalidation on password change
- Role claim tampering caught by `_session_valid()`
- HTTPS redirect (non-loopback) and exemptions
- Scriptable file extensions never viewable inline
- Admin-only delete: template markup verified; route count verified
- Disk space math and zero-total divide-by-zero
- Live-poll 401 on expired session
- Power manager shed/restore state machine
- Battery guard `decide()` logic
- eth-share `start_block_reason()` all conditions
- Repository path consistency (no dangling `.desktop`/systemd/script references)
- Shell script syntax (`bash -n`)

**Proposed (8 cases — see `docs/tests.md`):**
- Open redirect `?next=` validation (P1)
- Guest delete returns redirect not 403 at route level (P2)
- Post-save disk guard when no `Content-Length` (P3)
- `/view` forces download for scriptable extensions (P4)
- Power manager skips PINET units when `/run/pinet-stopped` exists (P5)
- Pentest handoff appended on restore when kiosk open (P6)
- Battery guard hysteresis requires two consecutive good readings (P7)
- eth-share blocked when eth carrier absent (P8)

**Top unverified gaps:**
1. `/view/<id>` scriptable forced-download at route level (stored XSS vector)
2. `?next=` open redirect validation
3. Brute-force lockout persistence across restarts
4. nftables `pinet_ap` table loaded on boot

---

## Correctness Summary

Reviewed: `pinet-board/app.py`, `scripts/sbin/pi-power-manager`, `scripts/sbin/pinet-ups-guard`, `scripts/sbin/eth-share`. Dimensions: authority reconciliation, identity correlation.

**Finding C1 — `permissions.md` doc error corrected (not a code bug)**  
*Expectation:* `permissions.md` stated guest delete → 403.  
*Trigger:* Guest calls `POST /delete/<file_id>`.  
*Defect:* Code returns `redirect(url_for("board"))` (302), not `abort(403)`.  
*Impact:* No data loss (delete is blocked). Incorrect HTTP semantics; automated scanners may mark it as success.  
*Remedy:* Return `abort(403)` on both unauthorized delete routes; update `permissions.md` (doc already corrected this session).  
*Participants:* `pinet-board/app.py:479`, `pinet-board/app.py:496`.

No authority reconciliation bugs found. No identity correlation bugs found (file IDs are SQLite integer PKs; no unstable key joins).

---

## Security Summary

**4 LOW + 2 INFO findings.** No Critical or High.

| # | Severity | Finding | File | Fix |
|---|---|---|---|---|
| 1 | LOW | Brute-force lockout state lost on process restart (`_attempts = {}` in-memory) | `app.py:66` | Persist lockout to `/run/pinet-board/` tmpfs on every failed attempt |
| 2 | LOW | Non-admin delete returns 302 redirect, not 403 | `app.py:479,496` | `abort(403)` instead of `redirect(url_for("board"))` |
| 3 | LOW | No Content-Security-Policy header | `app.py` | Add `@app.after_request` hook setting CSP header |
| 4 | LOW | Upload disk guard skips when `Content-Length` absent | `app.py:309` | Post-save: if `free_disk_bytes() < MIN_FREE_BYTES`, delete saved file + rollback DB row |
| 5 | INFO | Guest-to-guest wlan0 traffic unrestricted | `pinet-ap.nft` | Add `iifname wlan0 oifname wlan0 drop` forward chain if public venue deployment |
| 6 | INFO | Self-signed TLS cert; no HSTS | `app.py:44–47` | Add `Strict-Transport-Security` header on HTTPS responses |

**OWASP coverage:** A01–A10 audited. A05 (no CSP) and A09 (no auth audit log) are the only gaps; no Critical/High in any category.

**What is well-built:** PBKDF2-SHA256 (200k rounds), `hmac.compare_digest`, cred-tag session invalidation, `secure_filename` + random-token upload prefix, `X-Content-Type-Options: nosniff`, forced-download for scriptable types, `pinet-board` system user (no root), nftables SSH/VNC drop on wlan0, power manager flock mutex, atomic `/run` writes.

Full report: `reports/security_audit_2026-10-26.md`

---

## Performance Summary

**4 findings — no blockers.**

| Finding | File | Recommendation | Effort | Priority |
|---|---|---|---|---|
| `COUNT(*)` on every live poll | `app.py:391–401` | Use `MAX(id)` (B-tree scan vs. full scan) | Low | Medium |
| `os.statvfs()` on every poll | `app.py:storage_stats` | Cache result for 15 s; invalidate after write | Low | Low |
| Initial board loads 200 rows | `app.py:357–363` | Reduce to 50; poller fills in the rest | Low | Low |
| `/mnt/pinet-media/tmp` not auto-created | `pinet-board.service` | Add `ExecStartPre=mkdir -p` directive | Low | Medium |

**Bonus recommendation:** `PRAGMA journal_mode=WAL` in `get_db()` — prevents concurrent read stalls during upload inserts under multiple polling guests.

**What is already efficient:** No N+1 queries; incremental polling with `WHERE id > ?`; streaming file save; raw SQLite; no ORM.

Full report: `reports/performance_audit_2026-10-26.md`

---

## Independent Review

**Step 6 — Independent Unsteered Review**

Not run in this session. A second model-family session was not available during this ship-check pass. This section would normally contain findings from a fresh session (no prior context, no checklist) of a model from a different family — e.g. Gemini 2.5 Pro via CLI or another vendor's tool.

**Owner action required:** Before the next production deploy, run an independent review with:
```
git log --oneline HEAD~10..HEAD
git diff HEAD~10..HEAD
git status
```
Pass the diff (not this audit's findings) to a fresh session of a different model family and apply the code-review skill's keep/drop rule to any findings that come back.

---

## Audit Provenance

| Step | Model | Notes |
|---|---|---|
| Steps 1–2: Documentation + agent context | Claude Sonnet 4.6 (this session) | All docs derived from reading source files directly |
| Step 3: Correctness review | Claude Sonnet 4.6 (this session) | Inline; no subagent |
| Step 4: Security audit | Claude Sonnet 4.6 (this session) | Inline; intended-vs-implemented against docs just written |
| Step 5: Performance audit | Claude Sonnet 4.6 (this session) | Inline; static review only |
| Step 6: Independent review | **Not run** | Second model-family session unavailable; see owner action above |
| Step 7: Test derivation | Claude Sonnet 4.6 (this session) | Coverage map derived from existing test files + docs |

---

## Launch Blockers

No Critical or High security findings. No correctness bugs that allow unauthorized access or data loss.

**Pre-deploy blockers (operational, not code defects):**

1. **nftables rule not loaded on boot** — if `pinet-ap-network.service` fails to load `pinet-ap.nft`, SSH (port 22) and VNC (port 5900) are reachable by hotspot guests. Verify: `sudo nft list ruleset | grep pinet_ap` before going live.

2. **`/mnt/pinet-media/tmp` must exist** — upload spooling fails silently with a 500 if this directory is absent. Add `ExecStartPre=mkdir -p /mnt/pinet-media/tmp` to `pinet-board.service` (see performance finding).

3. **TLS certs and secret_key must be generated** — the pre-deploy checklist in `variables.md` covers these; verify before first exposure to guests.

4. **Step 6 independent review not run** — a ship of this codebase to a new context (event, public venue) should include a fresh independent review before that context's first use.

**Not launch blockers (but recommended):**
- Lockout persistence (LOW security #1) — meaningful only if the process can be crashed by a guest
- CSP header (LOW security #3) — defense-in-depth; no confirmed XSS vector
- Proposed tests P1–P8 — should be written before the next AI-editing session on pinet-board

---

## Recommended Next Actions

**Immediately (before next deploy):**
1. Verify nftables rule: `sudo nft list ruleset | grep pinet_ap` on the Pi.
2. Add `ExecStartPre=mkdir -p /mnt/pinet-media/tmp` to `pinet-board.service`.
3. Run pre-deploy checklist in `docs/variables.md`.

**Short-term (next AI editing session):**
4. Change non-admin delete routes to `abort(403)` (`pinet-board/app.py:479`, `pinet-board/app.py:496`).
5. Add post-save disk guard: delete file + rollback DB row if `free_disk_bytes() < MIN_FREE_BYTES` after save.
6. Add `PRAGMA journal_mode=WAL` in `get_db()`.
7. Write proposed tests P1 (open redirect), P2 (delete → 302), P4 (`/view` forced-download) — these pin the three highest-exposure unverified rules.

**Before the next public-venue deployment:**
8. Run independent unsteered review (Step 6) with a different model family.
9. Add CSP header (`after_request` hook).
10. Consider lockout persistence to `/run/pinet-board/` tmpfs.
