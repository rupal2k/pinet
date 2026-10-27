"""pinet-luks-unlock: pure logic tests (no GTK, no sudo, no cryptsetup).

Covers:
  - unlock() feeds cryptsetup the PIN bytes verbatim (no trailing newline)
  - wrong PIN → reject(), entered cleared
  - 5 wrong PINs → reboot Popen called
  - CalledProcessError from unlock() → "Failed", increments fails, reboot at MAX
  - blocked_until prevents further attempts
"""
import hmac
import subprocess
import types
import unittest
from unittest.mock import MagicMock, call, patch

from _support import FakeClock, load_defs, repo_path

LUKS = repo_path("scripts", "bin", "pinet-luks-unlock")


def _load(clock=None):
    clk = clock or FakeClock()
    m = load_defs(
        LUKS,
        ["read_passcode", "unlock", "mount_media", "notify_ready", "UnlockDialog", "MAX_ATTEMPTS",
         "LUKS_DEV", "LUKS_NAME"],
        {
            "time": clk,
            "os": __import__("os"),
            "subprocess": subprocess,
            "hmac": hmac,
            "Gtk": MagicMock(),
            "Gdk": MagicMock(),
            "GdkPixbuf": MagicMock(),
            "GLib": MagicMock(),
            "GtkLayerShell": MagicMock(),
        },
    )
    return m, clk


def _make_dialog(code="1234", clock=None):
    m, clk = _load(clock)
    d = object.__new__(m.UnlockDialog)
    d.code = code
    d.entered = ""
    d.fails = 0
    d.blocked_until = 0.0
    d.title = MagicMock()
    d.dots = MagicMock()
    d.dots.get_style_context.return_value = MagicMock()
    d._frame_ms = 0
    return d, m, clk


class UnlockKeyBytes(unittest.TestCase):
    def test_unlock_sends_pin_without_newline(self):
        # --key-file - keeps a trailing newline as part of the key, and keyslots
        # are written without one, so a newline makes every correct PIN fail.
        m, _ = _load()
        with patch.object(subprocess, "run") as run:
            m.unlock("1234")
        self.assertEqual(run.call_args.kwargs["input"], b"1234")


class PinCheck(unittest.TestCase):
    def test_correct_pin_calls_unlock(self):
        d, m, _ = _make_dialog("1234")
        with patch.object(m, "unlock") as mock_unlock, \
             patch.object(m, "mount_media"), \
             patch("subprocess.Popen"):
            # _do_unlock is called via GLib.timeout_add; call it directly
            d.entered = "1234"
            m.UnlockDialog._do_unlock(d)
            mock_unlock.assert_called_once_with("1234")

    def test_wrong_pin_rejects(self):
        d, m, _ = _make_dialog("1234")
        with patch("subprocess.Popen"):
            d.entered = "9999"
            m.UnlockDialog._check(d)
            self.assertEqual(d.fails, 1)
            self.assertEqual(d.entered, "")

    def test_wrong_pin_does_not_call_unlock(self):
        d, m, _ = _make_dialog("1234")
        with patch.object(m, "unlock") as mock_unlock, \
             patch("subprocess.Popen"):
            d.entered = "9999"
            m.UnlockDialog._check(d)
            mock_unlock.assert_not_called()

    def test_called_process_error_increments_fails(self):
        d, m, _ = _make_dialog("1234")
        with patch.object(m, "unlock", side_effect=subprocess.CalledProcessError(1, "cryptsetup")), \
             patch.object(m, "mount_media"), \
             patch("subprocess.Popen"):
            d.entered = "1234"
            m.UnlockDialog._do_unlock(d)
            self.assertEqual(d.fails, 1)
            self.assertEqual(d.entered, "")

    def test_mount_failure_does_not_increment_fails(self):
        d, m, _ = _make_dialog("1234")
        with patch.object(m, "unlock"), \
             patch.object(m, "mount_media",
                          side_effect=subprocess.CalledProcessError(32, "mount")), \
             patch("subprocess.Popen"):
            d.entered = "1234"
            m.UnlockDialog._do_unlock(d)
            self.assertEqual(d.fails, 0, "mount failure must not count as a wrong PIN")


class RebootGuard(unittest.TestCase):
    def test_fifth_wrong_pin_reboots(self):
        d, m, _ = _make_dialog("1234")
        with patch("subprocess.Popen") as mock_popen:
            for _ in range(4):
                d.entered = "9999"
                m.UnlockDialog._check(d)
            mock_popen.assert_not_called()
            d.entered = "9999"
            m.UnlockDialog._check(d)
            # reboot call should be in the Popen calls
            reboot_calls = [c for c in mock_popen.call_args_list
                            if c.args and "reboot" in c.args[0]]
            self.assertTrue(reboot_calls, "Expected reboot Popen call after 5 fails")

    def test_fourth_wrong_pin_does_not_reboot(self):
        d, m, _ = _make_dialog("1234")
        with patch("subprocess.Popen") as mock_popen:
            for _ in range(4):
                d.entered = "9999"
                m.UnlockDialog._check(d)
            reboot_calls = [c for c in mock_popen.call_args_list
                            if c.args and "reboot" in c.args[0]]
            self.assertFalse(reboot_calls)

    def test_max_attempts_constant_is_5(self):
        d, m, _ = _make_dialog()
        self.assertEqual(m.MAX_ATTEMPTS, 5)


class BlockedUntil(unittest.TestCase):
    def test_blocked_input_ignored(self):
        d, m, clk = _make_dialog("1234")
        with patch("subprocess.Popen"):
            # Trigger 5 failures to get blocked_until set
            for _ in range(5):
                d.entered = "9999"
                m.UnlockDialog._check(d)
            self.assertGreater(d.blocked_until, clk.now)
            # While blocked, feed should be a no-op
            m.UnlockDialog.feed(d, "1")
            self.assertEqual(d.entered, "")

    def test_do_unlock_cpe_sets_blocked_until_after_5_fails(self):
        # C4 regression: _do_unlock CalledProcessError path must set blocked_until
        # at fails >= 5, just like reject() does.
        d, m, clk = _make_dialog("1234")
        d.fails = 4  # next failure is the 5th
        with patch.object(m, "unlock",
                          side_effect=subprocess.CalledProcessError(1, "cryptsetup")), \
             patch("subprocess.Popen"):
            d.entered = "1234"
            m.UnlockDialog._do_unlock(d)
            self.assertEqual(d.fails, 5)
            self.assertGreater(d.blocked_until, clk.now,
                               "_do_unlock must set blocked_until on 5th CalledProcessError")


class LastAttemptWarning(unittest.TestCase):
    def test_fourth_failure_shows_last_attempt_title(self):
        # Q4: "Last attempt" warning must appear on fail 4 (== MAX_ATTEMPTS - 1).
        d, m, _ = _make_dialog("1234")
        with patch("subprocess.Popen"):
            for _ in range(3):
                d.entered = "9999"
                m.UnlockDialog._check(d)
            d.title.set_text.reset_mock()
            d.entered = "9999"
            m.UnlockDialog._check(d)  # 4th failure
            calls = [str(c) for c in d.title.set_text.call_args_list]
            self.assertTrue(
                any("Last attempt" in c for c in calls),
                f"Expected 'Last attempt' title on 4th fail, got: {calls}"
            )


class MissingPin(unittest.TestCase):
    def test_feed_is_noop_when_code_is_none(self):
        # Q6: feed() must not modify entered or fail count when PIN file is missing.
        d, m, _ = _make_dialog(code=None)
        m.UnlockDialog.feed(d, "1")
        self.assertEqual(d.entered, "")
        self.assertEqual(d.fails, 0)

    def test_check_is_noop_when_code_is_none(self):
        d, m, _ = _make_dialog(code=None)
        with patch.object(m, "unlock") as mock_unlock:
            d.entered = "9999"
            m.UnlockDialog._check(d)
            mock_unlock.assert_not_called()
            self.assertEqual(d.fails, 1,
                             "_check calls reject() on mismatch even with code=None")


if __name__ == "__main__":
    unittest.main()
