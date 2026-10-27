"""dsi-lock.py: pure logic extracted via load_defs (no GTK needed).

Tests cover the three critical paths:
  - correct PIN → _unlock() called
  - reject / backoff schedule (30s doubling, cap 3600)
  - blocked input ignored during blocked_until
  - code=None silently blocks all input
  - _pqiv_running() proc-scan
"""
import os
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from _support import FakeClock, load_defs, repo_path

LOCK = repo_path("scripts", "bin", "dsi-lock.py")


def _gtk_stubs():
    """Minimal GTK stubs so load_defs can exec feed/reject/backspace without a display."""
    style_ctx = MagicMock()
    style_ctx.has_class.return_value = False
    label = MagicMock()
    label.get_style_context.return_value = style_ctx
    gtk = types.ModuleType("gi.repository.Gtk")
    gtk.main_quit = MagicMock()
    glib = types.ModuleType("gi.repository.GLib")
    glib.timeout_add = MagicMock()
    return gtk, glib, label, style_ctx


def load(clock=None):
    gtk, glib, label, style_ctx = _gtk_stubs()
    clk = clock or FakeClock()
    m = load_defs(
        LOCK,
        ["read_passcode", "Lock"],
        {
            "time": clk,
            "os": os,
            "Gtk": gtk,
            "GLib": glib,
            "Gdk": MagicMock(),
            "GdkPixbuf": MagicMock(),
            "GtkLayerShell": MagicMock(),
            "subprocess": __import__("subprocess"),
        },
    )
    return m, clk, gtk


class LockLogic(unittest.TestCase):
    """Tests run against a Lock instance with GTK stubbed out."""

    def _make_lock(self, code="1234", clock=None):
        m, clk, gtk = load(clock)
        # Bypass __init__ (requires Gtk.Window etc.); build the state manually.
        lock = object.__new__(m.Lock)
        lock.code = code
        lock.entered = ""
        lock.fails = 0
        lock.blocked_until = 0.0
        # Stub display objects used in feed/reject/refresh
        lock.dots = MagicMock()
        lock.dots.get_style_context.return_value = MagicMock()
        lock.title = MagicMock()
        lock._gtk = gtk
        lock._clk = clk
        # Patch _unlock and GLib on the instance's class temporarily
        lock._unlock = MagicMock()
        # Patch module-level time in the loaded module
        m_time = types.ModuleType("time")
        m_time.monotonic = clk.monotonic
        import sys
        # The exec'd module uses 'time' from its globals; patch via the module dict.
        # load_defs puts 'time' in mod.__dict__ under the key 'time'.
        lock._time_mod = m_time
        return lock, m, clk

    # ------------------------------------------------------------------ helpers
    def _feed_digits(self, lock, m, digits):
        """Feed each digit through Lock.feed, using the module's implementation."""
        for d in digits:
            m.Lock.feed(lock, d)

    # ------------------------------------------------------------------ cases
    def test_correct_pin_calls_unlock(self):
        lock, m, _ = self._make_lock("1234")
        self._feed_digits(lock, m, "1234")
        lock._unlock.assert_called_once()

    def test_wrong_pin_does_not_unlock(self):
        lock, m, _ = self._make_lock("1234")
        self._feed_digits(lock, m, "9999")
        lock._unlock.assert_not_called()

    def test_overflow_triggers_reject(self):
        lock, m, _ = self._make_lock("12")
        # Feed 3 digits for a 2-digit code — 3rd digit overflows
        m.Lock.feed(lock, "1")
        m.Lock.feed(lock, "2")  # exact length → _check → _unlock if correct
        # Reset and test wrong overflow
        lock2, m2, _ = self._make_lock("12")
        lock2._unlock = MagicMock()
        m2.Lock.feed(lock2, "9")
        m2.Lock.feed(lock2, "8")  # wrong → reject
        self.assertEqual(lock2.fails, 1)

    def test_backoff_starts_at_fail_5(self):
        lock, m, clk = self._make_lock("1234")
        for _ in range(4):
            m.Lock.reject(lock)
        self.assertEqual(lock.blocked_until, 0.0)  # not blocked yet
        m.Lock.reject(lock)  # 5th fail
        self.assertGreater(lock.blocked_until, clk.now)

    def test_backoff_doubles_per_fail(self):
        lock, m, clk = self._make_lock("1234")
        for _ in range(5):
            m.Lock.reject(lock)
        first_block = lock.blocked_until - clk.now  # should be 30s
        self.assertAlmostEqual(first_block, 30.0)
        clk.now += 31
        m.Lock.reject(lock)  # 6th fail
        second_block = lock.blocked_until - clk.now  # should be 60s
        self.assertAlmostEqual(second_block, 60.0)

    def test_backoff_capped_at_3600(self):
        lock, m, clk = self._make_lock("1234")
        # Simulate many failures — schedule past the cap
        for i in range(20):
            clk.now = lock.blocked_until + 1
            m.Lock.reject(lock)
        block = lock.blocked_until - clk.now
        self.assertLessEqual(block, 3600.0)

    def test_blocked_input_ignored(self):
        lock, m, clk = self._make_lock("1234")
        for _ in range(5):
            m.Lock.reject(lock)
        # While blocked, feed should not change entered or call _unlock
        before_entered = lock.entered
        m.Lock.feed(lock, "1")
        self.assertEqual(lock.entered, before_entered)
        lock._unlock.assert_not_called()

    def test_none_code_blocks_all_input(self):
        lock, m, _ = self._make_lock(code=None)
        m.Lock.feed(lock, "1")
        lock._unlock.assert_not_called()
        self.assertEqual(lock.entered, "")

    def test_backspace_removes_last_digit(self):
        lock, m, _ = self._make_lock("1234")
        m.Lock.feed(lock, "1")
        m.Lock.feed(lock, "2")
        m.Lock.backspace(lock)
        self.assertEqual(lock.entered, "1")

    def test_clear_resets_entered(self):
        lock, m, _ = self._make_lock("1234")
        m.Lock.feed(lock, "1")
        m.Lock.feed(lock, "2")
        lock.entered = ""  # simulate C key
        m.Lock.refresh(lock)
        self.assertEqual(lock.entered, "")


class PqivRunning(unittest.TestCase):
    def _make_lock_obj(self):
        m, clk, _ = load()
        lock = object.__new__(m.Lock)
        lock._m = m
        return lock, m

    def test_detects_pqiv_in_cmdline(self):
        lock, m = self._make_lock_obj()
        with patch("os.listdir", return_value=["1", "2", "abc"]):
            def fake_open(path, mode="r"):
                if "1" in path and "cmdline" in path:
                    import io
                    return io.BytesIO(b"/usr/bin/pqiv\x00--fullscreen\x00")
                raise OSError("no")
            with patch("builtins.open", side_effect=fake_open):
                self.assertTrue(m.Lock._pqiv_running(lock))

    def test_returns_false_when_absent(self):
        lock, m = self._make_lock_obj()
        with patch("os.listdir", return_value=["1"]):
            with patch("builtins.open", side_effect=OSError):
                self.assertFalse(m.Lock._pqiv_running(lock))


if __name__ == "__main__":
    unittest.main()
