"""scripts/sbin/pi-power-manager: shed/restore state machine.

The extension-less script is imported whole (stdlib only). systemctl,
vcgencmd and time are replaced with fakes; /run paths point into a temp dir.
"""
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from _support import FakeClock, load_script, repo_path

PM_PATH = repo_path("scripts", "sbin", "pi-power-manager")


class StopLoop(Exception):
    pass


class FakeSystemd:
    def __init__(self, active):
        self.active = set(active)
        self.calls = []
        self.on_start = None

    def __call__(self, scope, *args):
        self.calls.append((scope,) + args)
        verb, unit = args[0], args[-1]
        if verb == "is-active":
            return 0 if unit in self.active else 3
        if verb == "stop":
            self.active.discard(unit)
        elif verb == "start":
            self.active.add(unit)
            if self.on_start:
                self.on_start(unit)
        return 0

    def verbs(self, verb):
        return [c[-1] for c in self.calls if c[1] == verb]


class PowerManagerCase(unittest.TestCase):
    RUNNING = ["dsi-photo-frame.service", "pinet-board.service", "dnsmasq.service",
               "hostapd.service", "wayvnc.service", "bluetooth.service"]

    def setUp(self):
        self.pm = load_script(PM_PATH, "pi_power_manager_under_test")
        self.tmp = Path(tempfile.mkdtemp(prefix="pinet-pm-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.pm.RUN_DIR = self.tmp / "run"
        self.pm.RUN_DIR.mkdir()
        self.pm.STATE = self.pm.RUN_DIR / "stopped.json"
        self.pm.MODE = self.pm.RUN_DIR / "mode"
        self.pm.KIOSK_FLAG = self.tmp / "kiosk-mode"
        # Paths added by fix/power-coordination; absent on main, so set only if present.
        if hasattr(self.pm, "LOCK"):
            self.pm.LOCK = self.tmp / "power-shed.lock"
        if hasattr(self.pm, "HANDOFF"):
            self.pm.HANDOFF = self.pm.RUN_DIR / "handoff.list"
        if hasattr(self.pm, "KIOSK_DIR"):
            self.pm.KIOSK_DIR = self.tmp / "kiosk-mode.d"
            self.pm.KIOSK_DIR.mkdir()
        self.sd = FakeSystemd(self.RUNNING)
        self.pm.systemctl = self.sd
        self.uv = []  # queued under-voltage readings; empty -> False
        self.pm.under_voltage_now = lambda: self.uv.pop(0) if self.uv else False
        self.clock = FakeClock()
        self.pm.time = self.clock
        self.pm.print = lambda *a, **k: None

    def state(self):
        return [tuple(x) for x in json.loads(self.pm.STATE.read_text())]


class ShedRestore(PowerManagerCase):
    def test_shed_stops_only_running_units_in_order(self):
        self.pm.shed()
        order = [u for s, u in self.pm.SHED_UNITS]
        stopped = self.sd.verbs("stop")
        self.assertEqual(stopped, [u for u in order if u in self.RUNNING])
        self.assertEqual(self.state(), [(s, u) for s, u in self.pm.SHED_UNITS if u in self.RUNNING])
        self.assertEqual(self.pm.MODE.read_text(), "kiosk\n")
        self.assertEqual(self.sd.active, set())

    def test_bluetooth_masked_while_shed(self):
        self.pm.shed()
        self.assertEqual(self.sd.verbs("mask"), ["bluetooth.service"])
        mask_i = self.sd.calls.index(("system", "mask", "--runtime", "bluetooth.service"))
        stop_i = self.sd.calls.index(("system", "stop", "bluetooth.service"))
        self.assertLess(mask_i, stop_i)
        self.pm.restore()
        unmask_i = self.sd.calls.index(("system", "unmask", "--runtime", "bluetooth.service"))
        start_i = self.sd.calls.index(("system", "start", "--no-block", "bluetooth.service"))
        self.assertLess(unmask_i, start_i)

    def test_restore_reverse_order_hostapd_before_dnsmasq(self):
        self.pm.shed()
        self.assertTrue(self.pm.restore())
        started = self.sd.verbs("start")
        self.assertEqual(started, list(reversed(self.sd.verbs("stop"))))
        self.assertLess(started.index("hostapd.service"), started.index("dnsmasq.service"))
        self.assertFalse(self.pm.STATE.exists())
        self.assertEqual(self.pm.MODE.read_text(), "normal\n")
        self.assertEqual(self.sd.active, set(self.RUNNING))

    def test_restore_waits_for_voltage_but_gives_up_after_max(self):
        self.sd.active = {"hostapd.service"}
        self.pm.shed()
        self.uv = [True] * 20
        self.pm.restore()
        self.assertEqual(self.clock.sleeps, [1] * self.pm.VOLTAGE_WAIT_MAX_SECONDS + [self.pm.RESTORE_GAP_SECONDS])

    def test_restore_waits_only_while_under_voltage(self):
        self.sd.active = {"hostapd.service"}
        self.pm.shed()
        self.uv = [True, True, False]
        self.pm.restore()
        self.assertEqual(self.clock.sleeps, [1, 1, self.pm.RESTORE_GAP_SECONDS])

    def test_kiosk_reopened_mid_restore_keeps_rest_stopped(self):
        self.pm.shed()
        self.sd.on_start = lambda unit: self.pm.KIOSK_FLAG.touch()
        self.assertFalse(self.pm.restore())
        self.assertEqual(self.sd.verbs("start"), ["bluetooth.service"])
        self.assertNotIn(("system", "bluetooth.service"), self.state())
        self.assertIn(("system", "hostapd.service"), self.state())

    def test_shed_merges_with_interrupted_restore(self):
        self.pm.save_stopped([("system", "hostapd.service")])
        self.sd.active = {"bluetooth.service", "dnsmasq.service"}
        self.pm.shed()
        self.assertEqual(self.state(), [("system", "dnsmasq.service"), ("system", "hostapd.service"),
                                        ("system", "bluetooth.service")])

    def test_startup_resumes_restore_when_no_kiosk(self):
        self.sd.active = {"hostapd.service"}
        self.pm.shed()
        self.pm.POLL_SECONDS = 99

        def sleep(s):
            if s == 99:
                raise StopLoop
        self.pm.time = SimpleNamespace(sleep=sleep)
        with self.assertRaises(StopLoop):
            self.pm.main()
        self.assertIn("hostapd.service", self.sd.active)
        self.assertFalse(self.pm.STATE.exists())
        self.assertEqual(self.pm.MODE.read_text(), "normal\n")

    def test_under_voltage_now_parses_live_bit_only(self):
        pm = load_script(PM_PATH, "pi_power_manager_uv")
        pm.PWR_LED = Path("/nonexistent/leds/PWR")
        for out, want in (("throttled=0x50005\n", True), ("throttled=0x50000\n", False), ("", False)):
            pm.subprocess = SimpleNamespace(run=lambda *a, _o=out, **k: SimpleNamespace(stdout=_o))
            self.assertEqual(pm.under_voltage_now(), want, out)

        def missing(*a, **k):
            raise FileNotFoundError("vcgencmd")
        pm.subprocess = SimpleNamespace(run=missing)
        self.assertFalse(pm.under_voltage_now())


    def test_pwr_led_catches_what_avoid_warnings_hides(self):
        pm = load_script(PM_PATH, "pi_power_manager_led")
        led = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, led, True)
        (led / "trigger").write_text("none [input] default-on\n")
        pm.PWR_LED = led
        (led / "brightness").write_text("0\n")
        self.assertTrue(pm.pwr_led_says_low())
        (led / "brightness").write_text("255\n")
        self.assertFalse(pm.pwr_led_says_low())
        (led / "trigger").write_text("[none] input default-on\n")   # LED repurposed: no signal
        (led / "brightness").write_text("0\n")
        self.assertFalse(pm.pwr_led_says_low())

    # QA-7: MODE stays "kiosk" during the whole restore, so a kiosk reopening mid-restore
    # passes dsi-kiosk.sh's MODE gate while restored units are already running.
    def test_mode_not_kiosk_while_restored_units_are_running(self):
        self.pm.shed()
        seen = []

        def on_start(unit):
            running = [u for u in self.RUNNING if u in self.sd.active]
            seen.append((self.pm.MODE.read_text(), running))
        self.sd.on_start = on_start
        self.pm.restore()
        for mode, running in seen:
            if running:
                self.assertNotEqual(mode, "kiosk\n", f"MODE={mode!r} while running={running}")

    # QA-8a: a corrupt stopped.json reads as []; restore() reports success and writes MODE
    # normal, but hostapd stays down until reboot.
    def test_corrupt_state_does_not_forget_stopped_units(self):
        self.sd.active = {"hostapd.service"}
        self.pm.shed()
        self.pm.STATE.write_text('[["system", "hostapd.serv')  # torn write
        self.pm.restore()
        self.assertIn("hostapd.service", self.sd.active, f"active={self.sd.active}")

    # QA-8b: a state file naming a unit no longer in SHED_UNITS makes shed() raise ValueError;
    # a non-list JSON value (5, null) raises TypeError. The daemon crashes.
    def test_corrupt_state_bad_shapes_do_not_crash_shed(self):
        errors = []
        for content in ('[["system", "gone.service"]]', "5", "null"):
            self.pm.STATE.write_text(content)
            self.sd.active = {"hostapd.service"}
            try:
                self.pm.shed()
            except Exception as exc:  # noqa: BLE001 - any crash is the defect
                errors.append(f"{content}: {type(exc).__name__}: {exc}")
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
