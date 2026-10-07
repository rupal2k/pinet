#!/usr/bin/env python3
"""PINET message board + file drop -- anonymous (no accounts, no per-post
identity) but gated behind the dedicated portal password (never the Pi's
root password), same reasoning as the earlier bridge portal. Requires no
sudo/privileged actions at all -- a plain Flask app, no NAT/iptables, no
sudoers rule, which removes a whole class of risk the earlier
internet-bridge feature carried.

IMPORTANT: this process must be started with TMPDIR pointed at a real
disk directory (see pinet-board.service's Environment=), not the
system default -- /tmp on this Pi is a 463MB RAM-backed tmpfs, and
Werkzeug spools large multipart uploads to a temp file before this code
ever sees them. Without the override, any upload approaching the 1GB cap
would blow past the tmpfs and fail (or exhaust RAM) well before reaching
this app's own disk-space check below.
"""
import hashlib
import hmac
import mimetypes
import os
import secrets
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

from flask import (
    Flask, g, redirect, render_template, request,
    send_from_directory, session, url_for,
)
from flask.sessions import SecureCookieSessionInterface
from werkzeug.utils import secure_filename

BASE_DIR = Path("/opt/pinet-board")
DATA_DIR = BASE_DIR / "data"  # writable by pinet-board; BASE_DIR itself is root-owned
UPLOAD_DIR = Path("/mnt/pinet-media/uploads")
DB_PATH = DATA_DIR / "board.db"
PASSWORD_CONF = "/etc/pinet-board/board.conf"
GUEST_CONF = "/etc/pinet-board/guest.conf"  # optional guest tier; absent = no guest login
SECRET_KEY_PATH = "/etc/pinet-board/secret_key"
# HTTPS is served by this app itself (it replaced stunnel 2026-10-07), so the
# login lockout sees each guest's own IP, not stunnel's 127.0.0.1.
TLS_CERT = "/etc/pinet-board/tls-fullchain.pem"
TLS_KEY = "/etc/pinet-board/tls.key"
HTTPS_PORT = 443
SECURE_ORIGIN = "https://10.10.10.1"   # the cert covers 10.10.10.1 and pinet.local
LOOPBACK = ("127.0.0.1", "::1")

MAX_CONTENT_LENGTH = 1024 * 1024 * 1024  # 1 GiB per upload
MIN_FREE_BYTES = 500 * 1024 * 1024  # always keep this much free afterward
LOW_FREE_BYTES = 1024 ** 3  # below this the header warns: the next upload may not fit
MAX_MESSAGE_LEN = 2000

# Short confirmations rendered as a banner after a redirect (?ok=...), so an
# action is acknowledged instead of just looking like the page reloaded.
NOTICES = {
    "post": "Message posted.",
    "upload": "File shared.",
    "file-deleted": "File deleted.",
    "message-deleted": "Message deleted.",
}

MAX_ATTEMPTS = 5
LOCKOUT_SECONDS = 60
_attempts = {}  # ip -> (count, locked_until_monotonic)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH
app.config["HTTPS_ON"] = False   # set in __main__ once the TLS listener is up


class _PerSchemeCookieSession(SecureCookieSessionInterface):
    """Mark the session cookie Secure whenever it is issued over HTTPS, so a
    guest's browser never sends it over plain HTTP on the open hotspot. The
    Pi's own kiosk (http://localhost) still gets a working cookie."""
    def get_cookie_secure(self, app):
        return request.is_secure


app.session_interface = _PerSchemeCookieSession()


def needs_https(is_secure, remote_addr, https_on):
    """Plain HTTP from another device, while HTTPS is available: the PINET
    hotspot is an open network, so nothing with a password or session may
    travel over it unencrypted. Loopback (the Pi's own kiosk) is exempt."""
    return https_on and not is_secure and remote_addr not in LOOPBACK


@app.template_filter("timestamp_str")
def timestamp_str(ts):
    return datetime.fromtimestamp(ts).strftime("%b %d, %H:%M")


@app.template_filter("filesize_str")
def filesize_str(num):
    num = float(num)
    for unit in ("B", "KB", "MB", "GB"):
        # Compare what will actually be printed: 1048575 B rounds to 1024.0 KB,
        # which must roll over to 1.0 MB rather than render as "1024.0 KB".
        if round(num, 1) < 1024 or unit == "GB":
            return f"{num:.0f} {unit}" if unit == "B" else f"{num:.1f} {unit}"
        num /= 1024


# Extensions browsers can render inline -- drives the "View" action and the
# image thumbnails on the Files tab. Anything not here is download-only.
_IMAGE_EXT = {"jpg", "jpeg", "png", "gif", "webp", "bmp", "heic"}
_VIDEO_EXT = {"mp4", "webm", "mov", "m4v", "ogv"}
_AUDIO_EXT = {"mp3", "wav", "ogg", "oga", "m4a", "aac", "flac"}
_TEXT_EXT = {"txt", "md", "log", "csv", "json"}
_VIEWABLE_KINDS = ("image", "video", "audio", "pdf", "text")

# Serving an uploaded file inline could run script in this origin (stealing the
# session cookie) if the browser treats it as active content. Force these to
# download even from /view, and always send X-Content-Type-Options: nosniff.
_FORCE_DOWNLOAD_EXT = {"html", "htm", "xhtml", "shtml", "svg", "svgz", "xml", "js", "mjs"}


def _file_ext(filename):
    return filename.rsplit(".", 1)[-1].lower() if "." in filename else ""


def _file_kind(filename):
    ext = _file_ext(filename)
    if ext in _IMAGE_EXT:
        return "image"
    if ext in _VIDEO_EXT:
        return "video"
    if ext in _AUDIO_EXT:
        return "audio"
    if ext == "pdf":
        return "pdf"
    if ext in _TEXT_EXT:
        return "text"
    if ext in {"zip", "rar", "7z", "tar", "gz"}:
        return "archive"
    if ext in {"doc", "docx"}:
        return "doc"
    return "other"


def _file_row(fid, filename, size, created):
    kind = _file_kind(filename)
    return {"id": fid, "filename": filename, "size": size, "created": created,
            "kind": kind, "viewable": kind in _VIEWABLE_KINDS}


def _load_secret_key():
    try:
        return Path(SECRET_KEY_PATH).read_bytes()
    except Exception:
        key = secrets.token_bytes(32)
        Path(SECRET_KEY_PATH).write_bytes(key)
        os.chmod(SECRET_KEY_PATH, 0o640)
        return key


app.secret_key = _load_secret_key()
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.execute(
            "CREATE TABLE IF NOT EXISTS messages ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, body TEXT NOT NULL, created REAL NOT NULL)"
        )
        g.db.execute(
            "CREATE TABLE IF NOT EXISTS files ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, filename TEXT NOT NULL, "
            "stored_name TEXT NOT NULL, size INTEGER NOT NULL, created REAL NOT NULL)"
        )
    return g.db


@app.teardown_appcontext
def close_db(exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def check_password(password, conf_path=PASSWORD_CONF):
    try:
        with open(conf_path) as f:
            salt, expected = f.read().strip().split(":", 1)
    except Exception:
        return False
    calc = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 200_000).hex()
    return hmac.compare_digest(calc, expected)


def _cred_tag(conf_path):
    # Digest of the credential file a session was issued under. Changing a
    # password (or deleting guest.conf) changes it, which ends every session
    # issued under the old one -- the signed cookie alone can't be revoked.
    try:
        return hashlib.sha256(Path(conf_path).read_bytes()).hexdigest()
    except OSError:
        return None


def _conf_for(role):
    return PASSWORD_CONF if role == "admin" else GUEST_CONF


def _session_valid():
    tag = _cred_tag(_conf_for(session.get("role")))
    return bool(session.get("authed")) and tag is not None and session.get("cred") == tag


def is_admin():
    return session.get("role") == "admin"


@app.context_processor
def inject_role():
    # Exposes `role` and `is_admin` to every template; board.html shows the
    # delete controls only when is_admin is true.
    return {"role": session.get("role"), "is_admin": is_admin()}


def is_locked_out(ip):
    entry = _attempts.get(ip)
    if not entry:
        return False, 0
    count, locked_until = entry
    remaining = locked_until - time.monotonic()
    if remaining <= 0:
        return False, 0
    # Round up: with 0.4s left the user must not be told to retry in 0s.
    return True, int(remaining) + (1 if remaining % 1 else 0)


def record_attempt(ip, success):
    if success:
        _attempts.pop(ip, None)
        return
    count, _ = _attempts.get(ip, (0, 0))
    count += 1
    locked_until = time.monotonic() + LOCKOUT_SECONDS if count >= MAX_ATTEMPTS else 0
    _attempts[ip] = (count if count < MAX_ATTEMPTS else 0, locked_until)


def free_disk_bytes():
    # Uploads (and their TMPDIR spool, see pinet-board.service) both live on
    # /mnt/pinet-media, a separate filesystem from BASE_DIR's SD card -- this
    # must statvfs UPLOAD_DIR itself, not BASE_DIR, or both the displayed
    # free-space figure and the pre-upload capacity guard below silently
    # check the wrong disk.
    st = os.statvfs(str(UPLOAD_DIR))
    return st.f_bavail * st.f_frsize


def storage_stats():
    st = os.statvfs(str(UPLOAD_DIR))
    free = st.f_bavail * st.f_frsize
    total = st.f_blocks * st.f_frsize
    used_pct = round((1 - free / total) * 100, 1) if total else 0.0
    free_gb, total_gb = free / (1024**3), total / (1024**3)
    return {
        "free_gb": free_gb,
        "total_gb": total_gb,
        "used_pct": used_pct,
        # Formatted once here so the header and the poller can never disagree.
        "storage_text": f"{free_gb:.1f}GB free of {total_gb:.0f}GB",
        "storage_low": free < LOW_FREE_BYTES,
    }


@app.before_request
def https_only_on_the_air():
    # Registered first, so it runs before require_login. Plain-HTTP visitors
    # (including every OS's captive-portal probe) get a small page that sends
    # them to HTTPS; a bare redirect can dead-end in a phone's sign-in popup,
    # which may refuse the self-signed PINET certificate.
    if request.endpoint == "static":
        return   # the page's own CSS and logo
    if needs_https(request.is_secure, request.remote_addr, app.config["HTTPS_ON"]):
        return render_template("secure.html", url=SECURE_ORIGIN + "/login"), 200


@app.before_request
def require_login():
    # The whole board (view/post/upload/download) sits behind one
    # session cookie, set after a single correct password entry --
    # simpler and more usable than asking for the password on every
    # individual post or download, and matches "keep the portal
    # password, gate the whole thing" from the auth-scope decision.
    if request.endpoint in ("login", "static"):
        return
    if not _session_valid():
        session.clear()
        if request.endpoint == "api_state":
            return "", 401  # the poller stops on this instead of parsing a login page
        return redirect(url_for("login", next=request.path))

    # Reject oversized uploads by their declared Content-Length before
    # spooling any of the body -- Werkzeug's own MAX_CONTENT_LENGTH check
    # already rejects anything over 1GB, but this also protects the
    # disk-space margin, accounting for the fact that Werkzeug spools the
    # upload to a temp file (now on real disk, see TMPDIR) and this app
    # then copies it again into UPLOAD_DIR -- briefly needing roughly 2x
    # the file's size free, not just 1x.
    if request.endpoint == "upload_file" and request.content_length:
        needed = request.content_length * 2 + MIN_FREE_BYTES
        if free_disk_bytes() < needed:
            return render_template(
                "board.html", messages=[], files=[], now=time.time(), **storage_stats(),
                error="Not enough free space on the Pi for a file that size right now.",
            ), 413


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    retry = 0
    # Already signed in (the kiosk shortcut, or a guest re-opening the
    # captive link): go straight to the board instead of asking again.
    if request.method == "GET" and _session_valid():
        # Keep ?kiosk=1 so app.js on the board can still remember the kiosk.
        return redirect(url_for("board", kiosk="1" if request.args.get("kiosk") == "1" else None))
    if request.method == "POST":
        ip = request.remote_addr
        locked, remaining = is_locked_out(ip)
        if locked:
            error = f"Too many attempts -- try again in {remaining}s."
            retry = remaining
        else:
            pw = request.form.get("password", "")
            role = "admin" if check_password(pw, PASSWORD_CONF) else (
                "guest" if check_password(pw, GUEST_CONF) else None)
            if role:
                record_attempt(ip, True)
                session["authed"] = True
                session["role"] = role
                session["cred"] = _cred_tag(_conf_for(role))
                session.permanent = True
                # Only follow a local path: "//host", "http://host" and
                # "/\host" would bounce a fresh login to another site.
                nxt = request.args.get("next", "")
                if not nxt.startswith("/") or urlsplit(nxt.replace("\\", "/")).netloc:
                    nxt = url_for("board")
                return redirect(nxt)
            record_attempt(ip, False)
            error = "Wrong password."
    return render_template("login.html", error=error, retry=retry)


@app.route("/", methods=["GET"])
def board():
    db = get_db()
    messages = db.execute(
        "SELECT id, body, created FROM messages ORDER BY id DESC LIMIT 200"
    ).fetchall()
    file_rows = db.execute(
        "SELECT id, filename, size, created FROM files ORDER BY id DESC LIMIT 200"
    ).fetchall()
    files = [_file_row(*row) for row in file_rows]
    return render_template(
        "board.html", messages=messages, files=files, error=None, now=time.time(),
        notice=NOTICES.get(request.args.get("ok")), **storage_stats(),
    )


@app.route("/api/state")
def api_state():
    # What an open board needs to stay current: messages and files added since
    # the caller's newest ids, rendered with the same partials board.html uses
    # (so a live row is identical to a reloaded one), plus the counts, the disk
    # figures and the Pi's clock -- the hotspot is offline, so phone clocks can
    # be minutes off and relative times are measured against this instead.
    db = get_db()
    since = request.args.get("since", type=int) or 0
    since_file = request.args.get("since_file", type=int) or 0
    msgs = db.execute(
        "SELECT id, body, created FROM messages WHERE id > ? ORDER BY id DESC LIMIT 50",
        (since,),
    ).fetchall()
    files = db.execute(
        "SELECT id, filename, size, created FROM files WHERE id > ? ORDER BY id DESC LIMIT 50",
        (since_file,),
    ).fetchall()
    return {
        "now": time.time(),
        "messages": {
            "total": db.execute("SELECT COUNT(*) FROM messages").fetchone()[0],
            "newest": msgs[0][0] if msgs else since,
            "html": "".join(render_template("_message.html", mid=mid, body=body, created=created)
                            for mid, body, created in msgs),
        },
        "files": {
            "total": db.execute("SELECT COUNT(*) FROM files").fetchone()[0],
            "newest": files[0][0] if files else since_file,
            "html": "".join(render_template("_file.html", f=_file_row(*row)) for row in files),
        },
        "storage": storage_stats(),
    }


@app.route("/post", methods=["POST"])
def post_message():
    body = (request.form.get("body") or "").strip()[:MAX_MESSAGE_LEN]
    if body:
        db = get_db()
        db.execute("INSERT INTO messages (body, created) VALUES (?, ?)", (body, time.time()))
        db.commit()
    return redirect(url_for("board", ok="post"))


@app.route("/upload", methods=["POST"])
def upload_file():
    f = request.files.get("file")
    if not f or not f.filename:
        return redirect(url_for("board"))

    safe_name = secure_filename(f.filename) or "file"
    stored_name = f"{secrets.token_hex(8)}_{safe_name}"
    dest = UPLOAD_DIR / stored_name
    f.save(dest)  # streams to disk in chunks, never buffers the whole file in memory

    size = dest.stat().st_size
    db = get_db()
    db.execute(
        "INSERT INTO files (filename, stored_name, size, created) VALUES (?, ?, ?, ?)",
        (safe_name, stored_name, size, time.time()),
    )
    db.commit()
    return redirect(url_for("board", ok="upload"))


@app.route("/download/<int:file_id>")
def download_file(file_id):
    db = get_db()
    row = db.execute("SELECT filename, stored_name FROM files WHERE id=?", (file_id,)).fetchone()
    if not row:
        return "Not found", 404
    filename, stored_name = row
    return send_from_directory(UPLOAD_DIR, stored_name, as_attachment=True, download_name=filename)


@app.errorhandler(413)
def too_large(e):
    return render_template(
        "board.html", messages=[], files=[], now=time.time(), **storage_stats(),
        error="That file is too large (1GB max) or there isn't enough free space right now.",
    ), 413


@app.route("/view/<int:file_id>")
def view_file(file_id):
    # Open a file inline in the browser (images, PDF, video, audio, text)
    # instead of forcing a download. Reuses the same auth gate as everything
    # else via before_request; the download route stays for save-to-disk.
    db = get_db()
    row = db.execute("SELECT filename, stored_name FROM files WHERE id=?", (file_id,)).fetchone()
    if not row:
        return "Not found", 404
    filename, stored_name = row
    as_attachment = _file_ext(filename) in _FORCE_DOWNLOAD_EXT
    mimetype = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    resp = send_from_directory(
        UPLOAD_DIR, stored_name, as_attachment=as_attachment,
        download_name=filename, mimetype=mimetype,
    )
    # Never let the browser MIME-sniff an upload into something scriptable.
    resp.headers["X-Content-Type-Options"] = "nosniff"
    return resp


@app.route("/delete/<int:file_id>", methods=["POST"])
def delete_file(file_id):
    # Admin-only: remove an uploaded file (DB row + the file on disk). POST-only
    # so it can't be triggered by a GET/prefetch or a plain link.
    if not is_admin():
        return redirect(url_for("board"))
    db = get_db()
    row = db.execute("SELECT stored_name FROM files WHERE id=?", (file_id,)).fetchone()
    if row:
        try:
            (UPLOAD_DIR / row[0]).unlink(missing_ok=True)
        except Exception:
            pass  # a missing file is fine; still drop the DB row below
        db.execute("DELETE FROM files WHERE id=?", (file_id,))
        db.commit()
    return redirect(url_for("board", ok="file-deleted") + "#files")


@app.route("/delete-message/<int:msg_id>", methods=["POST"])
def delete_message(msg_id):
    # Admin-only moderation for the anonymous board, mirroring delete_file:
    # POST-only so a GET or a prefetch can never remove a message.
    if not is_admin():
        return redirect(url_for("board"))
    db = get_db()
    db.execute("DELETE FROM messages WHERE id=?", (msg_id,))
    db.commit()
    return redirect(url_for("board", ok="message-deleted"))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# Captive-portal catch-all: any unmatched path/host lands here too, same
# mechanism as the earlier bridge portal -- keeps the auto-popup
# captive-portal behavior working regardless of which probe URL an OS uses.
@app.route("/<path:path>")
def catch_all(path):
    return redirect(url_for("board" if session.get("authed") else "login"))


def start_https():
    """Serve HTTPS on 443 next to the plain-HTTP listener. Missing or
    unreadable certs leave HTTPS off, so the board still works (over HTTP)."""
    import ssl
    import threading
    from werkzeug.serving import make_server
    try:
        ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        ctx.load_cert_chain(TLS_CERT, TLS_KEY)
        server = make_server("0.0.0.0", HTTPS_PORT, app, threaded=True, ssl_context=ctx)
    except (OSError, ssl.SSLError) as exc:
        print(f"pinet-board: HTTPS off ({exc}); serving HTTP only", flush=True)
        return
    threading.Thread(target=server.serve_forever, daemon=True).start()
    app.config["HTTPS_ON"] = True


if __name__ == "__main__":
    start_https()
    app.run(host="0.0.0.0", port=80, threaded=True)
