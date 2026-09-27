"""pinet-ups-guard: when the low-battery countdown starts, cancels and fires;
and the systemd-shutdown hook that arms boot-on-power."""
import importlib.machinery
import importlib.util
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from _support import repo_path


def _load(name, *path):
    loader = importlib.machinery.SourceFileLoader(name, str(repo_path(*path)))
    mod = importlib.util.module_from_spec(importlib.util.spec_from_loader(name, loader))
    loader.exec_module(mod)
    return mod


guard = _load("pinet_ups_guard", "scripts", "sbin", "pinet-ups-guard")
batt = _load("pinet_battery_for_guard", "scripts", "bin", "pinet-battery")

ON_BATTERY, CHARGING = -0.6, 2.2


def run(readings, dt=guard.INTERVAL):
    """One reading every `dt` seconds of monotonic time, starting at 0."""
    state, actions = guard.new_state(), []
    for i, (volts, amps) in enumerate(readings):
        actions.append(guard.decide(state, volts, amps, batt, i * dt))
    return actions


# Readings (one per INTERVAL) that take the countdown from its warning to the
# power-off: the warning at t=0, the power-off at t=GRACE.
N = guard.GRACE // guard.INTERVAL + 1


class Guard(unittest.TestCase):
    def test_low_on_battery_warns_once_then_shuts_down_after_the_grace(self):
        n = N
        actions = run([(3.2, ON_BATTERY)] * n)
        self.assertEqual(actions[0], "warn")
        self.assertEqual(actions[-1], "shutdown")
        self.assertEqual(actions.count("warn"), 1)
        self.assertNotIn("shutdown", actions[:-1])

    def test_plugging_the_charger_in_cancels(self):
        actions = run([(3.2, ON_BATTERY)] * 5 + [(3.25, CHARGING)] * 2 + [(3.2, ON_BATTERY)] * 3)
        self.assertEqual(actions[5:7], [None, "cancel"])   # two readings to be sure
        self.assertEqual(actions[7], "warn")   # a fresh countdown, not the old one
        self.assertNotIn("shutdown", actions)

    def test_one_odd_reading_does_not_cancel(self):
        # Seen live: a load spike flipped the current for one reading.
        n = N
        actions = run([(3.2, ON_BATTERY)] * 5 + [(3.2, CHARGING)] + [(3.2, ON_BATTERY)] * n)
        self.assertNotIn("cancel", actions)
        self.assertEqual(actions.count("warn"), 1)
        self.assertIn("shutdown", actions)

    def test_the_countdown_is_clock_time_not_a_count_of_readings(self):
        # Review finding: slow or failing reads used to stretch it past the
        # deadline the e-ink shows. Readings 7 s apart: still off at ~GRACE.
        actions = run([(3.2, ON_BATTERY)] * 20, dt=7)
        first = actions.index("shutdown")
        self.assertGreaterEqual(first * 7, guard.GRACE)
        self.assertLess((first - 1) * 7, guard.GRACE)

    def test_warn_sets_the_deadline_the_e_ink_is_given(self):
        state = guard.new_state()
        self.assertEqual(guard.decide(state, 3.2, ON_BATTERY, batt, 100.0), "warn")
        self.assertEqual(state["deadline"], 100.0 + guard.GRACE)

    def test_low_while_charging_is_fine(self):
        self.assertEqual(set(run([(3.1, CHARGING)] * 60)), {None})

    def test_a_small_recovery_does_not_cancel(self):
        actions = run([(3.2, ON_BATTERY)] * 3 + [(3.35, ON_BATTERY)] + [(3.2, ON_BATTERY)])
        self.assertNotIn("cancel", actions)

    def test_the_countdown_keeps_running_through_a_small_recovery(self):
        # Review finding: readings between 3.3 and 3.4 V used to freeze the
        # countdown while the e-ink's deadline ran out.
        n = N
        actions = run([(3.28, ON_BATTERY)] + [(3.35, ON_BATTERY)] * (n - 1))
        self.assertEqual(actions[0], "warn")
        self.assertEqual(actions[-1], "shutdown")

    def test_a_real_recovery_cancels(self):
        actions = run([(3.28, ON_BATTERY)] * 3 + [(3.45, ON_BATTERY)] * 2)
        self.assertEqual(actions[-1], "cancel")

    def test_two_cells_in_series_are_judged_per_cell(self):
        self.assertEqual(run([(6.4, ON_BATTERY)])[0], "warn")      # 3.2 V a cell
        self.assertEqual(set(run([(7.4, ON_BATTERY)] * 60)), {None})

    def test_a_bad_read_is_ignored(self):
        self.assertEqual(set(run([(0.0, 0.0)] * 60)), {None})

    def test_healthy_battery_does_nothing(self):
        self.assertEqual(set(run([(3.7, ON_BATTERY)] * 60)), {None})



class ShutdownHook(unittest.TestCase):
    """systemd/system-shutdown/pinet-ups-arm, with a fake i2cset."""
    def run_hook(self, verb, marked):
        d = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: subprocess.run(["rm", "-rf", str(d)]))
        fake = d / "i2cset"
        fake.write_text(f'#!/bin/bash\necho "$*" > {d}/called\n')
        fake.chmod(0o755)
        mark = d / "mark"
        if marked:
            mark.touch()
        env = dict(os.environ, UPS_ARM_MARK=str(mark), I2CSET=str(fake))
        subprocess.run([str(repo_path("systemd", "system-shutdown", "pinet-ups-arm")), verb],
                       env=env, check=True)
        return (d / "called").read_text().strip() if (d / "called").exists() else None

    def test_arms_on_a_guard_power_off(self):
        self.assertEqual(self.run_hook("poweroff", True), "-y 1 0x2d 0x01 0x55")

    def test_leaves_ordinary_shutdowns_alone(self):
        self.assertIsNone(self.run_hook("poweroff", False))   # not the guard's
        self.assertIsNone(self.run_hook("reboot", True))      # a reboot comes back anyway


if __name__ == "__main__":
    unittest.main()
