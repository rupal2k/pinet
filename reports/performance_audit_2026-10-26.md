# Performance Audit — PINET

**Scope:** full repository  
**Date:** 2026-10-26  
**Method:** pm-ai-shipping:performance-audit-static — N+1 queries, over-fetching, missing indexes, caching  
**Primary files reviewed:** `pinet-board/app.py`, `pinet-board/static/app.js`

---

## Overview

PINET is a single-device appliance. The PINET hotspot serves ≤ 254 clients on a /24. The board database holds messages and files; uploads are bounded by the USB drive capacity. Scaling to millions of rows is not a goal. Performance findings here concern:
- the real constraints: Pi 3B CPU (1.2 GHz quad), SD card I/O, and the 463 MB tmpfs.
- the appliance ceiling: a Pi 3B can serve ~100 concurrent connections; the hotspot caps well below that.

At this scale most web-framework anti-patterns (N+1 queries, absent caching) are invisible. The findings below are genuine bottlenecks or correctness-adjacent risks, not theoretical inefficiencies.

---

## Findings

### `/api/state` — two COUNT(*) queries on every live poll

**Finding:** `api_state()` executes `SELECT COUNT(*) FROM messages` and `SELECT COUNT(*) FROM files` on every poll cycle. The JavaScript poller in `app.js` fires on page focus and on a periodic interval.

**Evidence:** `pinet-board/app.py:391–401`
```python
"total": db.execute("SELECT COUNT(*) FROM messages").fetchone()[0],
...
"total": db.execute("SELECT COUNT(*) FROM files").fetchone()[0],
```

**Impact:** Each `COUNT(*)` does a full table scan in SQLite without a covering index. On a Pi 3B with SD-card I/O, this is measurable at thousands of rows. It is also a write-amplification path: every poll writes nothing, but forces SQLite to do read work per active guest tab.

**Recommendation:** Include the newest message/file ID in the count instead of `COUNT(*)`:
```python
"total": db.execute("SELECT MAX(id) FROM messages").fetchone()[0] or 0,
```
`MAX(id)` on an `INTEGER PRIMARY KEY` column uses the B-tree max key — O(log n) vs. O(n). For exact counts the client can track total by incrementing when it sees new items arrive — it already has `"newest"` to compare.

**Effort:** Low  
**Priority:** Medium  
**Expected effect:** Reduces poll read amplification from O(n) to O(log n). Meaningful at 10k+ rows.

---

### `storage_stats()` — `os.statvfs()` called on every board page load and every API poll

**Finding:** `storage_stats()` calls `os.statvfs(UPLOAD_DIR)` on every `GET /` board render and every `/api/state` poll response.

**Evidence:** `pinet-board/app.py:147–152` (implied by `storage_stats()` called from `board()` and `api_state()`)

**Impact:** `statvfs` is a kernel syscall on an SD card. On a Pi 3B this is ~1–2 ms per call. For a poll running every few seconds across several active guest tabs, this adds up. More importantly: the SD card I/O bandwidth is shared with SQLite reads/writes and the upload path — polling statvfs adds contention.

**Recommendation:** Cache the `statvfs` result for 10–30 seconds via a simple module-level dict:
```python
_STATVFS_CACHE = {"time": 0, "result": None}

def storage_stats():
    now = time.monotonic()
    if now - _STATVFS_CACHE["time"] > 15:
        st = os.statvfs(UPLOAD_DIR)
        _STATVFS_CACHE.update(time=now, result=st)
    ...  # use _STATVFS_CACHE["result"]
```
Invalidation: call `_STATVFS_CACHE["time"] = 0` at the end of `upload_file()` and `delete_file()` to force a fresh read after a write.

**Effort:** Low  
**Priority:** Low  
**Expected effect:** Reduces SD card I/O on polls from every-call to once per 15 s + after writes.

---

### Message and file list — no server-side pagination on initial board load

**Finding:** `board()` fetches the 200 most-recent messages and 200 most-recent files on every full board load:
```python
"SELECT id, body, created FROM messages ORDER BY id DESC LIMIT 200"
"SELECT id, filename, size, created FROM files ORDER BY id DESC LIMIT 200"
```

**Evidence:** `pinet-board/app.py:357–363`

**Impact:** 200 messages + 200 file rows rendered into the initial HTML. Each file row includes size formatting. This is fine at launch; at a heavily-used event (200+ files uploaded) the initial page HTML grows and the Pi 3B's Jinja2 rendering time increases.

**Recommendation:** `LIMIT 50` for the initial render; rely on the `/api/state` poller for real-time additions. The existing poller already caps at 50 per call. The stored total in `storage_stats` gives the user context on how many items exist.

**Effort:** Low  
**Priority:** Low  
**Expected effect:** Cuts initial HTML size by 4× when board is heavily used; poller fills in missing items automatically.

---

### Upload spool — `TMPDIR` not created on first install

**Finding:** The service unit sets `TMPDIR=/mnt/pinet-media/tmp`. If that directory doesn't exist when the service starts, Werkzeug's `FileStorage.save()` will fail to spool the upload and the user gets a 500 instead of a friendly error.

**Evidence:** `systemd/pinet-board.service` (TMPDIR env); `pinet-board/app.py:424` (`f.save(dest)`); `docs/variables.md` pre-deploy checklist item: "Confirm `/mnt/pinet-media/tmp` directory exists."

**Impact:** Not a correctness bug in the code — the checklist covers it. But it is a silent operational footgun: if the USB drive is remounted or the SD card replaced, `tmp/` disappears and uploads start failing with a 500.

**Recommendation:** Add a `ExecStartPre=mkdir -p /mnt/pinet-media/tmp` directive to `pinet-board.service`. This is idempotent, runs as root (before `User=pinet-board` takes effect), and self-heals after remounts.

**Effort:** Low  
**Priority:** Medium (operational reliability, not performance per se)  
**Expected effect:** Eliminates a class of silent upload failures after storage remounts.

---

## What is already efficient

- **No N+1 queries** — all list views use a single `SELECT` with `LIMIT`. No per-row fetches.
- **Incremental polling** — `/api/state` uses `WHERE id > ?` (since_id) to return only new rows. The client does not re-fetch the full list.
- **`f.save(dest)` streaming** — Werkzeug streams file uploads in chunks, never buffers the whole file in memory. Correct for a Pi 3B with limited RAM.
- **No ORM** — raw SQLite with parameterized queries; no ORM overhead or lazy-load traps.
- **`secure_filename` + token prefix** — no directory listing queries needed; files are served directly from `send_from_directory` by stored name.
- **`_FORCE_DOWNLOAD_EXT` check at serve time** — a dict lookup, not a DB query.
- **Jinja2 templates pre-compiled** — Flask caches compiled templates; first-request overhead is minimal.

## What needs runtime profiling to confirm

- **SD card I/O contention** under simultaneous upload + multiple polling guests — this cannot be assessed statically. Suggest `iostat -x 1 30` during a test session with 5 guests polling and one upload in progress.
- **Werkzeug spool-to-disk latency** for large uploads (100 MB+) — the `TMPDIR` is on the USB drive, which may vary from 10–40 MB/s on a Pi 3B over USB 2.0.
- **SQLite write-ahead log** — WAL mode is not explicitly configured. Under default journal mode, concurrent reads block on a write. With multiple polling guests, a large upload (which inserts a file row) could briefly stall all `/api/state` polls.

**Recommendation:** Add `db.execute("PRAGMA journal_mode=WAL")` in `get_db()` to allow concurrent readers during write transactions.
