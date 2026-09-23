"""pinet-board/app.py: pure helpers only (routes need flask/werkzeug).

Defs are extracted with ast so the module's import-time side effects
(secret key written under /etc, mkdir of /mnt/pinet-media) never run.
"""
import os
import re
import unittest
from pathlib import Path
from types import SimpleNamespace

from _support import FakeClock, load_defs, repo_path

APP = repo_path("pinet-board", "app.py")
NAMES = [
    "filesize_str", "_file_ext", "_file_kind",
    "_IMAGE_EXT", "_VIDEO_EXT", "_AUDIO_EXT", "_TEXT_EXT",
    "MAX_ATTEMPTS", "LOCKOUT_SECONDS", "_attempts",
    "is_locked_out", "record_attempt",
    "UPLOAD_DIR", "free_disk_bytes", "storage_stats", "NOTICES",
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

    def test_counter_resets_when_lock_is_set(self):
        self.fail_n(5)
        self.clock.now += 61
        self.fail_n(1)  # 6th failure after expiry counts as 1, not 6
        self.assertEqual(self.m.is_locked_out(self.IP), (False, 0))
        self.assertEqual(self.m._attempts[self.IP][0], 1)

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


if __name__ == "__main__":
    unittest.main()


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
        self.js = repo_path("pinet-board", "static", "app.js").read_text()

    def test_every_form_action_has_a_route(self):
        actions = set(re.findall(r'action="(/[a-z-]*)', self.html + self.partial))
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
        for marker, html in (("/delete/", self.html), ("/delete-message/", self.partial)):
            before = html.split(marker)[0]
            self.assertIn("{% if is_admin %}", before.rsplit("{% endif %}", 1)[-1],
                          f"{marker} is not inside an is_admin block")
        self.assertEqual(self.src.count("if not is_admin():"), 2)


class LiveMessages(unittest.TestCase):
    """The poller, its endpoint and the row partial all have to agree."""

    def setUp(self):
        self.src = APP.read_text()
        self.html = repo_path("pinet-board", "templates", "board.html").read_text()
        self.js = repo_path("pinet-board", "static", "app.js").read_text()

    def test_one_partial_renders_both_paths(self):
        # Board rows and polled rows must come from the same template, or the
        # two can drift apart.
        self.assertIn('{% include "_message.html" %}', self.html)
        self.assertIn('render_template("_message.html"', self.src)

    def test_poller_endpoint_matches_and_401s_a_dead_session(self):
        path = re.search(r'fetch\("([^"?]+)\?since=', self.js).group(1)
        self.assertIn(f'@app.route("{path}")', self.src)
        # Without this the poll would parse the login page as JSON forever.
        self.assertIn('if request.endpoint == "api_messages":', self.src)
        self.assertIn('return "", 401', self.src)
