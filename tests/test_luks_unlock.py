"""pinet-luks-unlock: pure logic tests (no GTK, no sudo, no cryptsetup).

Covers:
  - correct PIN → unlock() called with pin+"\n" (once newline fix applied)
  - wrong PIN → reject(), entered cleared
  - 5 wrong PINs → reboot Popen called
  - CalledProcessError from unlock() → "Failed", increments fails, reboot at MAX
  - blocked_until prevents further attempts
"""
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
        ["read_passcode", "unlock", "mount_media", "UnlockDialog", "MAX_ATTEMPTS"],
        {
            "time": clk,
            "os": __import__("os"),
            "subprocess": subprocess,
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


if __name__ == "__main__":
    unittest.main()
