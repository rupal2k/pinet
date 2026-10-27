"""dsi-tap-wake.py: pure helpers and double-tap timing constants.

evdev is hardware-only; we extract defs via AST so the top-level
``import evdev`` and ``os.environ.setdefault`` side effects never run.
"""
import os
import tempfile
import unittest
from pathlib import Path

from _support import load_defs, repo_path

SCRIPT = repo_path("scripts", "bin", "dsi-tap-wake.py")


def _load(extra=None):
    names = [
        "DOUBLE_TAP_WINDOW", "COOLDOWN", "STATE_POLL",
        "set_grab", "_lock_running", "_output_on", "_log",
    ]
    g = {"os": os, "sys": __import__("sys"), "subprocess": __import__("subprocess")}
    g.update(extra or {})
    return load_defs(SCRIPT, names, g)


class DoubleTapConstants(unittest.TestCase):
    """The timing constants are the spec -- tests pin them so a typo is caught."""

    def setUp(self):
        self.m = _load()

    def test_double_tap_window_is_half_second(self):
        self.assertAlmostEqual(self.m.DOUBLE_TAP_WINDOW, 0.5)

    def test_cooldown_prevents_immediate_re_wake(self):
        # COOLDOWN > DOUBLE_TAP_WINDOW so a cooldown-blocked tap can never
        # itself count as the first tap of a new double-tap sequence.
        self.assertGreater(self.m.COOLDOWN, self.m.DOUBLE_TAP_WINDOW)

    def test_state_poll_interval_is_positive(self):
        self.assertGreater(self.m.STATE_POLL, 0)


class SetGrab(unittest.TestCase):
    """set_grab(dev, want, grabbed) manages the evdev exclusive grab."""

    def _make_dev(self):
        calls = []

        class FakeDev:
            def grab(self):
                calls.append("grab")

            def ungrab(self):
                calls.append("ungrab")

        return FakeDev(), calls

    def setUp(self):
        self.m = _load()

    def test_grab_when_not_yet_grabbed(self):
        dev, calls = self._make_dev()
        result = self.m.set_grab(dev, want=True, grabbed=False)
        self.assertEqual(calls, ["grab"])
        self.assertTrue(result)

    def test_ungrab_when_currently_grabbed(self):
        dev, calls = self._make_dev()
        result = self.m.set_grab(dev, want=False, grabbed=True)
        self.assertEqual(calls, ["ungrab"])
        self.assertFalse(result)

    def test_no_op_when_state_already_matches(self):
        dev, calls = self._make_dev()
        self.assertTrue(self.m.set_grab(dev, want=True, grabbed=True))
        self.assertFalse(self.m.set_grab(dev, want=False, grabbed=False))
        self.assertEqual(calls, [], "no grab/ungrab call when state already matches")

    def test_oserror_leaves_state_unchanged(self):
        class ErrorDev:
            def grab(self):
                raise OSError("device busy")

        result = self.m.set_grab(ErrorDev(), want=True, grabbed=False)
        self.assertFalse(result, "OSError must not flip grabbed state")


class LockRunning(unittest.TestCase):
    """_lock_running() detects whether dsi-lock.py is alive via its PID file."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.pidfile = self.tmp / "dsi-lock.pid"
        # Inject LOCK_PIDFILE so load_defs resolves the module-level constant.
        self.m = load_defs(SCRIPT, ["_lock_running"],
                           {"os": os, "LOCK_PIDFILE": str(self.pidfile)})

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_returns_false_when_no_pidfile(self):
        self.assertFalse(self.m._lock_running())

    def test_returns_false_when_pidfile_contains_garbage(self):
        # ValueError path: int("notapid") raises, caught → False.
        self.pidfile.write_text("notapid\n")
        self.assertFalse(self.m._lock_running())

    def test_returns_false_for_stale_pid(self):
        # PID 999999999 almost certainly does not exist.
        self.pidfile.write_text("999999999\n")
        self.assertFalse(self.m._lock_running())

    def test_returns_true_for_own_pid(self):
        # os.getpid() is always alive while this test runs.
        self.pidfile.write_text(str(os.getpid()) + "\n")
        self.assertTrue(self.m._lock_running())


if __name__ == "__main__":
    unittest.main()
