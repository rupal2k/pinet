"""pinet-board/app.py: pure helpers only (routes need flask/werkzeug).

Defs are extracted with ast so the module's import-time side effects
(secret key written under /etc, mkdir of /mnt/pinet-media) never run.
"""
import hashlib
import hmac
import os
import re
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from _support import FakeClock, load_defs, repo_path

APP = repo_path("pinet-board", "app.py")
NAMES = [
    "filesize_str", "_file_ext", "_file_kind",
    "_IMAGE_EXT", "_VIDEO_EXT", "_AUDIO_EXT", "_TEXT_EXT",
    "MAX_ATTEMPTS", "LOCKOUT_SECONDS", "_attempts", "_storage_cache",
    "is_locked_out", "record_attempt",
    "UPLOAD_DIR", "free_disk_bytes", "storage_stats", "NOTICES", "LOW_FREE_BYTES",
]


def load(clock=None, os_mod=os):
    return load_defs(APP, NAMES, {"time": clock or FakeClock(), "os": os_mod, "Path": Path})


class FileSizeStr(unittest.TestCase):
    def setUp(self):
        self.f = load().filesize_str

    def test_bytes(self):
        self.assertEqual(self.f(0), "0 B")
        self.assertEqual(self.f(1023), "1023 B")

    def test_kilobytes(self):
        self.assertEqual(self.f(1024), "1.0 KB")
        self.assertEqual(self.f(1536), "1.5 KB")

    def test_megabytes_and_gigabytes(self):
        self.assertEqual(self.f(5 * 1024**2), "5.0 MB")
        self.assertEqual(self.f(3 * 1024**3), "3.0 GB")

    def test_gb_is_the_largest_unit(self):
        self.assertEqual(self.f(2048 * 1024**3), "2048.0 GB")

    def test_accepts_string_numbers(self):
        self.assertEqual(self.f("2048"), "2.0 KB")

    def test_no_1024_rollover(self):
        self.assertEqual(self.f(1024**2 - 1), "1.0 MB")
        self.assertEqual(self.f(1024**3 - 1), "1.0 GB")


class FileKind(unittest.TestCase):
    def setUp(self):
        self.m = load()

    def test_file_ext(self):
        e = self.m._file_ext
        self.assertEqual(e("photo.JPG"), "jpg")
        self.assertEqual(e("archive.tar.gz"), "gz")
        self.assertEqual(e("README"), "")
        self.assertEqual(e(".bashrc"), "bashrc")
        self.assertEqual(e("trailing."), "")

    def test_viewable_kinds(self):
        k = self.m._file_kind
        self.assertEqual(k("a.png"), "image")
        self.assertEqual(k("a.HEIC"), "image")
        self.assertEqual(k("a.mp4"), "video")
        self.assertEqual(k("a.flac"), "audio")
        self.assertEqual(k("a.pdf"), "pdf")
        self.assertEqual(k("a.json"), "text")

    def test_download_only_kinds(self):
        k = self.m._file_kind
        self.assertEqual(k("a.7z"), "archive")
        self.assertEqual(k("a.docx"), "doc")
        self.assertEqual(k("a.exe"), "other")
        self.assertEqual(k("noext"), "other")

    def test_active_content_is_never_viewable(self):
        k = self.m._file_kind
        for name in ("x.html", "x.svg", "x.js", "x.xml", "x.xhtml"):
            self.assertEqual(k(name), "other", name)


class Lockout(unittest.TestCase):
    IP = "10.10.10.23"

    def setUp(self):
        self.clock = FakeClock()
        self.m = load(self.clock)

    def fail_n(self, n, ip=IP):
        for _ in range(n):
            self.m.record_attempt(ip, False)

    def test_four_failures_do_not_lock(self):
        self.fail_n(4)
        self.assertEqual(self.m.is_locked_out(self.IP), (False, 0))

    def test_fifth_failure_locks_for_60s(self):
        self.fail_n(5)
        self.assertEqual(self.m.is_locked_out(self.IP), (True, 60))
        self.clock.now += 59
        self.assertEqual(self.m.is_locked_out(self.IP), (True, 1))
        self.clock.now += 1
        self.assertEqual(self.m.is_locked_out(self.IP), (False, 0))

    def test_counter_persists_after_lockout_expiry(self):
        # After lockout expires the count is remembered: any new failure
        # immediately re-triggers the lockout (count 6 >= MAX_ATTEMPTS).
        self.fail_n(5)
        self.clock.now += 61
        self.fail_n(1)
        locked, remaining = self.m.is_locked_out(self.IP)
        self.assertTrue(locked)
        self.assertEqual(self.m._attempts[self.IP][0], 6)

    def test_success_clears(self):
        self.fail_n(4)
        self.m.record_attempt(self.IP, True)
        self.assertNotIn(self.IP, self.m._attempts)
        self.fail_n(4)
        self.assertEqual(self.m.is_locked_out(self.IP), (False, 0))

    def test_lockout_is_per_ip(self):
        self.fail_n(5)
        self.assertEqual(self.m.is_locked_out("10.10.10.99"), (False, 0))

    def test_locked_never_reports_zero_seconds(self):
        self.fail_n(5)
        self.clock.now += 59.6
        locked, remaining = self.m.is_locked_out(self.IP)
        self.assertTrue(locked)
        self.assertGreaterEqual(remaining, 1)


class StorageStats(unittest.TestCase):
    def fake_os(self, blocks, bavail, frsize=4096):
        calls = []

        def statvfs(path):
            calls.append(path)
            return SimpleNamespace(f_blocks=blocks, f_bavail=bavail, f_frsize=frsize)
        return SimpleNamespace(statvfs=statvfs), calls

    def test_stats_use_upload_dir(self):
        fos, calls = self.fake_os(blocks=1024**2, bavail=256 * 1024)  # 4 GiB total, 1 GiB free
        m = load(os_mod=fos)
        s = m.storage_stats()
        self.assertEqual(calls, ["/mnt/pinet-media/uploads"])
        self.assertAlmostEqual(s["total_gb"], 4.0)
        self.assertAlmostEqual(s["free_gb"], 1.0)
        self.assertEqual(s["used_pct"], 75.0)
        self.assertEqual(m.free_disk_bytes(), 1024**3)

    def test_zero_total_does_not_divide_by_zero(self):
        fos, _ = self.fake_os(blocks=0, bavail=0)
        s = load(os_mod=fos).storage_stats()
        self.assertEqual(s["used_pct"], 0.0)

    def test_cache_avoids_repeated_statvfs_within_15s(self):
        clock = FakeClock()
        fos, calls = self.fake_os(blocks=1024**2, bavail=256 * 1024)
        m = load(clock=clock, os_mod=fos)
        m._storage_cache[:] = [0.0, {}]  # ensure clean state
        m.storage_stats()
        self.assertEqual(len(calls), 1, "first call must hit statvfs")
        m.storage_stats()
        self.assertEqual(len(calls), 1, "second call within 15s must use cache")
        clock.now += 16
        m.storage_stats()
        self.assertEqual(len(calls), 2, "call after cache expiry must re-query")



class CheckPassword(unittest.TestCase):
    """check_password() is the auth gate; a bug here is auth bypass or DoS."""

    def _make_conf(self, password):
        salt = os.urandom(16).hex()
        h = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 200_000).hex()
        tmp = tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".conf")
        tmp.write(f"{salt}:{h}\n")
        tmp.flush()
        tmp.close()
        return tmp.name

    def setUp(self):
        # check_password has a default arg `conf_path=PASSWORD_CONF`, so we must
        # inject PASSWORD_CONF (as a dummy) into the load_defs namespace.
        self.m = load_defs(APP, ["check_password"],
                           {"hashlib": hashlib, "hmac": hmac, "PASSWORD_CONF": ""})
        self.conf = self._make_conf("hunter2")

    def tearDown(self):
        try:
            os.unlink(self.conf)
        except OSError:
            pass

    def test_correct_password_returns_true(self):
        self.assertTrue(self.m.check_password("hunter2", self.conf))

    def test_wrong_password_returns_false(self):
        self.assertFalse(self.m.check_password("wrong", self.conf))

    def test_missing_file_returns_false(self):
        self.assertFalse(self.m.check_password("hunter2", "/nonexistent/path.conf"))

    def test_malformed_conf_returns_false(self):
        tmp = tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".conf")
        tmp.write("no-colon-here\n")
        tmp.close()
        try:
            self.assertFalse(self.m.check_password("hunter2", tmp.name))
        finally:
            os.unlink(tmp.name)


class SessionValid(unittest.TestCase):
    """_session_valid() is the single gate now shared by require_login() and the
    login GET short-circuit. Both callers must reject a cookie issued under an
    old password, so the check is tested once, here."""

    def setUp(self):
        import hashlib
        import tempfile
        self.tmp = Path(tempfile.mkdtemp())
        self.admin = self.tmp / "board.conf"
        self.guest = self.tmp / "guest.conf"
        self.admin.write_text("hash-for-admin\n")
        self.guest.write_text("hash-for-guest\n")
        self.session = {}
        self.mod = load_defs(
            APP, ["_cred_tag", "_conf_for", "_session_valid"],
            {"hashlib": hashlib, "Path": Path, "session": self.session,
             "PASSWORD_CONF": str(self.admin), "GUEST_CONF": str(self.guest)},
        )

    def sign_in(self, role):
        conf = self.admin if role == "admin" else self.guest
        self.session.update(authed=True, role=role,
                            cred=self.mod._cred_tag(str(conf)))

    def test_fresh_admin_and_guest_sessions_are_valid(self):
        for role in ("admin", "guest"):
            with self.subTest(role=role):
                self.session.clear()
                self.sign_in(role)
                self.assertTrue(self.mod._session_valid())

    def test_rotating_the_password_invalidates_the_cookie(self):
        self.sign_in("admin")
        self.assertTrue(self.mod._session_valid())
        self.admin.write_text("a-new-password-hash\n")
        # Advance mtime by 1s so ext4's 1s resolution sees the change.
        m = self.admin.stat().st_mtime
        os.utime(str(self.admin), (m + 1, m + 1))
        self.assertFalse(self.mod._session_valid())

    def test_guest_cookie_is_not_valid_as_admin(self):
        self.sign_in("guest")
        self.session["role"] = "admin"          # tamperer flips the role claim
        self.assertFalse(self.mod._session_valid())

    def test_missing_conf_file_is_not_valid(self):
        self.sign_in("guest")
        self.guest.unlink()
        self.assertFalse(self.mod._session_valid())

    def test_unauthed_session_is_not_valid(self):
        self.assertFalse(self.mod._session_valid())
        self.sign_in("admin")
        self.session["authed"] = False
        self.assertFalse(self.mod._session_valid())


class BoardTemplate(unittest.TestCase):
    """board.html and app.js against the routes/notices app.py actually defines."""

    def setUp(self):
        self.src = APP.read_text()
        self.html = repo_path("pinet-board", "templates", "board.html").read_text()
        self.partial = repo_path("pinet-board", "templates", "_message.html").read_text()
        self.file_partial = repo_path("pinet-board", "templates", "_file.html").read_text()
        self.js = repo_path("pinet-board", "static", "app.js").read_text()

    def test_every_form_action_has_a_route(self):
        actions = set(re.findall(r'action="(/[a-z-]*)', self.html + self.partial + self.file_partial))
        self.assertIn("/post", actions)
        self.assertIn("/delete-message", actions)
        for action in actions:
            self.assertIn(f'@app.route("{action}', self.src, f"no route for {action}")

    def test_every_ok_redirect_has_a_notice(self):
        keys = set(re.findall(r'url_for\("board", ok="([^"]+)"\)', self.src))
        js_keys = set(re.findall(r'"/\?ok=([a-z-]+)', self.js))
        self.assertTrue(keys and js_keys)
        self.assertEqual((keys | js_keys) - set(load().NOTICES), set())

    def test_delete_controls_are_admin_only(self):
        # Both the markup and the routes gate deletion on the admin role.
        for marker, html in (("/delete/", self.file_partial), ("/delete-message/", self.partial)):
            before = html.split(marker)[0]
            self.assertIn("{% if is_admin %}", before.rsplit("{% endif %}", 1)[-1],
                          f"{marker} is not inside an is_admin block")
        self.assertEqual(self.src.count("if not is_admin():"), 2)
        self.assertEqual(self.src.count("abort(403)"), 2)


class LiveMessages(unittest.TestCase):
    """The poller, its endpoint and the row partial all have to agree."""

    def setUp(self):
        self.src = APP.read_text()
        self.html = repo_path("pinet-board", "templates", "board.html").read_text()
        self.js = repo_path("pinet-board", "static", "app.js").read_text()

    def test_one_partial_renders_both_paths(self):
        # Board rows and polled rows must come from the same template, or the
        # two can drift apart.
        for partial in ("_message.html", "_file.html"):
            self.assertIn('{%% include "%s" %%}' % partial, self.html)
            self.assertIn('render_template("%s"' % partial, self.src)

    def test_poller_endpoint_matches_and_401s_a_dead_session(self):
        path = re.search(r'"(/api/[a-z]+)\?since=', self.js).group(1)
        self.assertIn(f'@app.route("{path}")', self.src)
        # Without this the poll would parse the login page as JSON forever.
        self.assertIn('if request.endpoint == "api_state":', self.src)
        self.assertIn('return "", 401', self.src)


class Stylesheet(unittest.TestCase):
    def test_icon_button_resets_the_generic_button_padding(self):
        # button/.btn is 13px 20px; a 44px-wide .icon-btn keeps 4px of content
        # box without this reset, and the eye icon shrinks to a sliver.
        css = repo_path("pinet-board", "static", "style.css").read_text()
        block = css.split(".icon-btn {", 1)[1].split("}", 1)[0]
        self.assertIn("padding: 0", block)


if __name__ == "__main__":
    unittest.main()


class LiveState(unittest.TestCase):
    """/api/state carries what the header and both lists need to stay current."""

    def setUp(self):
        self.src = APP.read_text()
        self.js = repo_path("pinet-board", "static", "app.js").read_text()
        self.html = repo_path("pinet-board", "templates", "board.html").read_text()

    def test_storage_text_is_formatted_once(self):
        # The header and the poller must not format the same figures apart.
        self.assertIn('"storage_text"', self.src)
        self.assertIn("{{ storage_text }}", self.html)
        self.assertIn("st.storage_text", self.js)

    def test_low_space_threshold_is_the_servers(self):
        self.assertIn("LOW_FREE_BYTES", self.src)
        self.assertIn("{% if storage_low %}", self.html)
        self.assertNotIn("free_gb < 1", self.html)

    def test_relative_times_use_the_servers_clock(self):
        self.assertIn('data-now="{{ now }}"', self.html)
        self.assertIn('"now": time.time()', self.src)
        self.assertIn("serverNow", self.js)


class NeedsHttps(unittest.TestCase):
    # The hotspot is open (2026-10-07): plain HTTP from another device must be
    # sent to HTTPS; the Pi's own kiosk on loopback is exempt.
    def setUp(self):
        self.f = load_defs(APP, ["LOOPBACK", "needs_https"], {}).needs_https

    def test_guest_over_http_is_sent_to_https(self):
        self.assertTrue(self.f(False, "10.10.10.57", True))

    def test_https_loopback_and_https_off_pass(self):
        self.assertFalse(self.f(True, "10.10.10.57", True))     # already HTTPS
        self.assertFalse(self.f(False, "127.0.0.1", True))      # the Pi's kiosk
        self.assertFalse(self.f(False, "::1", True))
        self.assertFalse(self.f(False, "10.10.10.57", False))   # no certs: HTTP only


class ForcedDownloadExt(unittest.TestCase):
    """Scriptable file types must trigger a forced download, not inline rendering.

    A browser that renders an uploaded .html or .js file as a same-origin page
    can run its scripts with full cookie access -- a stored-XSS with no CSP
    escape.  view_file() sets as_attachment=True for these types.
    """

    def setUp(self):
        m = load_defs(APP, ["_FORCE_DOWNLOAD_EXT", "_file_ext"])
        self.exts = m._FORCE_DOWNLOAD_EXT
        self.file_ext = m._file_ext

    def test_scriptable_types_are_forced(self):
        for name in ("page.html", "page.htm", "page.xhtml", "page.shtml",
                     "image.svg", "image.svgz", "data.xml", "script.js",
                     "module.mjs"):
            with self.subTest(name=name):
                self.assertIn(self.file_ext(name), self.exts,
                              f"{name!r} should be forced to download")

    def test_safe_types_are_not_forced(self):
        for name in ("photo.jpg", "photo.jpeg", "photo.png", "doc.pdf",
                     "clip.mp4", "note.txt", "archive.zip"):
            with self.subTest(name=name):
                self.assertNotIn(self.file_ext(name), self.exts,
                                 f"{name!r} should display inline")


class OpenRedirectValidation(unittest.TestCase):
    """The ?next= redirect after login must not bounce to an external site.

    The guard in login() is:
        if not nxt.startswith("/") or urlsplit(nxt.replace("\\\\", "/")).netloc:
            nxt = url_for("board")

    These tests pin that exact logic so a refactor can't silently remove it.
    """

    @staticmethod
    def _is_safe(nxt):
        from urllib.parse import urlsplit
        return nxt.startswith("/") and not urlsplit(nxt.replace("\\", "/")).netloc

    def test_local_paths_are_allowed(self):
        self.assertTrue(self._is_safe("/"))
        self.assertTrue(self._is_safe("/board"))
        self.assertTrue(self._is_safe("/board?ok=file-uploaded"))

    def test_external_url_is_rejected(self):
        self.assertFalse(self._is_safe("http://evil.com"))
        self.assertFalse(self._is_safe("https://evil.com/steal"))

    def test_protocol_relative_url_is_rejected(self):
        # "//evil.com" starts with "/" but has a netloc after urlsplit.
        self.assertFalse(self._is_safe("//evil.com"))
        self.assertFalse(self._is_safe("//evil.com/path"))

    def test_backslash_bypass_is_rejected(self):
        # "\\evil.com" becomes "//evil.com" after replace, giving a netloc.
        self.assertFalse(self._is_safe("\\\\evil.com"))
        self.assertFalse(self._is_safe("/\\evil.com"))

    def test_empty_and_relative_paths_are_rejected(self):
        self.assertFalse(self._is_safe(""))
        self.assertFalse(self._is_safe("board"))
        self.assertFalse(self._is_safe("../etc/passwd"))
