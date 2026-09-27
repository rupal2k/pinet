"""pinet-ups-guard: when the low-battery countdown starts, cancels and fires."""
import importlib.machinery
import importlib.util
import unittest

from _support import repo_path


def _load(name, *path):
    loader = importlib.machinery.SourceFileLoader(name, str(repo_path(*path)))
    mod = importlib.util.module_from_spec(importlib.util.spec_from_loader(name, loader))
    loader.exec_module(mod)
    return mod


guard = _load("pinet_ups_guard", "scripts", "sbin", "pinet-ups-guard")
batt = _load("pinet_battery_for_guard", "scripts", "bin", "pinet-battery")

ON_BATTERY, CHARGING = -0.6, 2.2


def run(readings):
    state, actions = {"low_for": 0, "ok": 0}, []
    for volts, amps in readings:
        actions.append(guard.decide(state, volts, amps, batt))
    return actions


class Guard(unittest.TestCase):
    def test_low_on_battery_warns_once_then_shuts_down_after_the_grace(self):
        n = guard.GRACE // guard.INTERVAL
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
        n = guard.GRACE // guard.INTERVAL
        actions = run([(3.2, ON_BATTERY)] * 5 + [(3.2, CHARGING)] + [(3.2, ON_BATTERY)] * n)
        self.assertNotIn("cancel", actions)
        self.assertEqual(actions.count("warn"), 1)
        self.assertIn("shutdown", actions)

    def test_low_while_charging_is_fine(self):
        self.assertEqual(set(run([(3.1, CHARGING)] * 60)), {None})

    def test_a_small_recovery_does_not_cancel(self):
        actions = run([(3.2, ON_BATTERY)] * 3 + [(3.35, ON_BATTERY)] + [(3.2, ON_BATTERY)])
        self.assertNotIn("cancel", actions)

    def test_the_countdown_keeps_running_through_a_small_recovery(self):
        # Review finding: readings between 3.3 and 3.4 V used to freeze the
        # countdown while the e-ink's deadline ran out.
        n = guard.GRACE // guard.INTERVAL
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


if __name__ == "__main__":
    unittest.main()
