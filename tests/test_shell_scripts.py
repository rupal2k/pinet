"""Shell scripts: syntax of everything, plus behaviour of kali-power-shed,
dsi-install-guard, wifi-pentest-stop and dsi-backlight.sh against PATH stubs.

Each behavioural test runs a copy of the real script whose hard-coded /run,
/sys and /usr/local paths are rewritten into a temp dir (see ShellHarness).
"""
import py_compile
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from _support import REPO, ShellHarness, bash_scripts, python_files


class Syntax(unittest.TestCase):
    def test_bash_n_on_all_scripts(self):
        scripts = bash_scripts()
        self.assertGreaterEqual(len(scripts), 22)
        bad = []
        for p in scripts:
            r = subprocess.run(["/bin/bash", "-n", str(p)], capture_output=True, text=True)
            if r.returncode:
                bad.append(f"{p.relative_to(REPO)}: {r.stderr.strip()}")
        self.assertEqual(bad, [])

    def test_py_compile_all_python(self):
        files = python_files()
        self.assertGreaterEqual(len(files), 17)
        tmp = Path(tempfile.mkdtemp(prefix="pinet-pyc-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        bad = []
        for i, p in enumerate(files):
            try:
                py_compile.compile(str(p), cfile=str(tmp / f"{i}.pyc"), doraise=True)
            except py_compile.PyCompileError as exc:
                bad.append(str(exc))
        self.assertEqual(bad, [])


class HarnessCase(unittest.TestCase):
    SCRIPT = None
    REWRITES = {}

    def setUp(self):
        self.h = ShellHarness(self.SCRIPT, self.REWRITES)
        self.addCleanup(self.h.cleanup)


class KaliPowerShed(HarnessCase):
    SCRIPT = "scripts/sbin/kali-power-shed"
    REWRITES = {"/run/pentest-mode": "{tmp}/pentest-mode", "/run/pentest-shed.list": "{tmp}/pentest-shed.list"}
    RUNNING = ("dsi-photo-frame.service", "rpi-connect-wayvnc.service", "stunnel@pinet-board.service",
               "pinet-board.service", "dnsmasq.service", "hostapd.service", "wayvnc.service",
               "bluetooth.service")

    @property
    def flag(self):
        return self.h.dir / "pentest-mode"

    @property
    def state(self):
        return self.h.dir / "pentest-shed.list"

    def test_requires_root(self):
        r = self.h.run("start", env={"FAKE_UID": "1000"})
        self.assertEqual(r.returncode, 1)
        self.assertIn("Run with sudo", r.stderr)
        self.assertFalse(self.flag.exists())

    def test_usage(self):
        r = self.h.run()
        self.assertEqual(r.returncode, 2)
        self.assertIn("usage", r.stderr)

    def test_start_records_running_units_and_sets_flag(self):
        self.h.set_active("hostapd.service", "dsi-photo-frame.service", "bluetooth.service")
        r = self.h.run("start")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.state.read_text(),
                         "user:dsi-photo-frame.service\nsys:hostapd.service\nsys:bluetooth.service\n")
        self.assertTrue(self.flag.exists())
        self.assertEqual(self.h.active(), [])
        self.assertIn("systemctl mask --runtime bluetooth.service", self.h.calls())

    def test_start_when_already_flagged_is_noop(self):
        self.flag.touch()
        self.h.set_active("hostapd.service")
        r = self.h.run("start")
        self.assertIn("Already in pentest power mode", r.stdout)
        self.assertEqual(self.h.active(), ["hostapd.service"])

    def test_round_trip_restores_everything_and_clears(self):
        self.h.set_active(*self.RUNNING)
        self.h.run("start")
        r = self.h.run("stop")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(sorted(self.h.active()), sorted(self.RUNNING))
        self.assertEqual(self.h.started()[0], "bluetooth.service")
        self.assertIn("systemctl unmask --runtime bluetooth.service", self.h.calls())
        self.assertFalse(self.flag.exists())
        self.assertFalse(self.state.exists())

    def test_restore_tolerates_blank_lines_spaces_and_colons(self):
        self.state.write_text("sys:hostapd.service\n\nuser:odd name:with colon.service\n")
        self.flag.touch()
        r = self.h.run("stop")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.h.started(), ["odd name:with colon.service", "hostapd.service"])

    # QA-9: header promises "PINET before VNC" on restore, but wayvnc restarts before
    # hostapd and pinet-board.
    def test_restore_brings_pinet_back_before_vnc(self):
        self.h.set_active(*self.RUNNING)
        self.h.run("start")
        self.h.run("stop")
        s = [u for u in self.h.started() if u in ("wayvnc.service", "hostapd.service", "pinet-board.service")]
        self.assertEqual(s[-1], "wayvnc.service", f"restore order {s}")

    # QA-10: if a start died before creating the flag, the next start truncates STATE, so
    # stop never restarts the units the first run stopped.
    def test_interrupted_start_does_not_lose_record(self):
        # First start was killed after stopping hostapd but before `touch $FLAG`.
        self.state.write_text("sys:hostapd.service\n")
        self.h.set_active("bluetooth.service")
        self.h.run("start")
        after_start = self.state.read_text()
        self.h.run("stop")
        self.assertIn("hostapd.service", self.h.started(),
                      f"STATE after 2nd start was {after_start!r}")


class DsiInstallGuard(HarnessCase):
    SCRIPT = "scripts/sbin/dsi-install-guard"
    REWRITES = {"/run/dsi-install-guard": "{tmp}/guard-state", "/sys/class/backlight": "{tmp}/backlight"}

    def setUp(self):
        super().setUp()
        bl = self.h.dir / "backlight" / "10-0045"
        bl.mkdir(parents=True)
        (bl / "bl_power").write_text("0\n")  # screen on
        self.stfile = self.h.dir / "guard-state"

    def test_pre_post_round_trip(self):
        self.h.set_active("dsi-photo-frame.service")
        r = self.h.run("pre")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.stfile.read_text(), "screen=on\nslideshow=yes\n")
        self.assertEqual(self.h.active(), [])
        self.assertTrue(any(c.startswith("dsi-sleep.sh") for c in self.h.calls()))
        r = self.h.run("post")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.h.active(), ["dsi-photo-frame.service"])
        self.assertTrue(any(c.startswith("dsi-wake.sh") for c in self.h.calls()))
        self.assertFalse(self.stfile.exists())

    def test_screen_off_and_no_slideshow_restore_nothing(self):
        (self.h.dir / "backlight" / "10-0045" / "bl_power").write_text("1\n")
        self.h.run("pre")
        self.assertEqual(self.stfile.read_text(), "screen=off\nslideshow=no\n")
        r = self.h.run("post")
        self.assertEqual(r.returncode, 0)
        self.assertEqual(self.h.started(), [])
        self.assertFalse(any(c.startswith("dsi-wake.sh") for c in self.h.calls()))

    def test_nested_pre_keeps_first_state_and_post_without_state_is_noop(self):
        self.stfile.write_text("screen=on\nslideshow=yes\n")
        self.assertEqual(self.h.run("pre").returncode, 0)
        self.assertEqual(self.stfile.read_text(), "screen=on\nslideshow=yes\n")
        self.stfile.unlink()
        r = self.h.run("post")
        self.assertEqual((r.returncode, self.h.calls()), (0, []))

    # QA-11: an empty/partial state file makes `post` die on an unbound variable (exit 1,
    # reported by apt as a Post-Invoke failure) after the state is already deleted.
    def test_empty_state_post_does_not_abort(self):
        self.stfile.write_text("")
        r = self.h.run("post")
        self.assertEqual(r.returncode, 0, r.stderr.strip())


class WifiPentestStop(HarnessCase):
    SCRIPT = "scripts/sbin/wifi-pentest-stop"

    def test_normal_stop_restores_power_mode(self):
        r = self.h.run()
        self.assertEqual(r.returncode, 0, r.stderr)
        calls = self.h.calls()
        self.assertIn("kali-power-shed stop", calls)
        self.assertLess(calls.index("iw dev wlan1 set type managed"), calls.index("kali-power-shed stop"))

    def test_requires_root(self):
        r = self.h.run(env={"FAKE_UID": "1000"})
        self.assertEqual(r.returncode, 1)
        self.assertNotIn("kali-power-shed stop", self.h.calls())

    # QA-13: under set -e, a failing `ip link set wlan1 down` (adapter unplugged) exits before
    # `kali-power-shed stop`; PINET/VNC/BT stay shed and the e-ink stays on PENTEST.
    def test_restores_power_mode_even_if_wlan1_is_gone(self):
        r = self.h.run(env={"FAKE_NO_WLAN1": "1"})
        self.assertIn("kali-power-shed stop", self.h.calls(),
                      f"rc={r.returncode} stderr={r.stderr.strip()!r}")


class DsiBacklight(HarnessCase):
    SCRIPT = "scripts/bin/dsi-backlight.sh"
    REWRITES = {"/sys/class/backlight": "{tmp}/backlight", "/etc/default/dsi-screen": "{tmp}/dsi-screen"}

    def make_device(self):
        bl = self.h.dir / "backlight" / "10-0045"
        bl.mkdir(parents=True)
        (bl / "bl_power").write_text("1\n")
        (bl / "brightness").write_text("0\n")
        return bl

    def test_on_off_write_sysfs(self):
        bl = self.make_device()
        (self.h.dir / "dsi-screen").write_text("BRIGHTNESS=80\n")
        r = self.h.run("on")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(((bl / "bl_power").read_text(), (bl / "brightness").read_text()), ("0\n", "80\n"))
        self.h.run("on", "200")
        self.assertEqual((bl / "brightness").read_text(), "200\n")
        self.h.run("off")
        self.assertEqual(((bl / "bl_power").read_text(), (bl / "brightness").read_text()), ("1\n", "0\n"))

    def test_usage(self):
        self.make_device()
        r = self.h.run("dim")
        self.assertEqual(r.returncode, 1)
        self.assertIn("usage", r.stderr)

    # QA-14: with no backlight device, `set -euo pipefail` makes the ls|head substitution exit 2
    # silently; the "no backlight device found" branch never runs.
    @unittest.expectedFailure
    def test_missing_backlight_prints_its_error(self):
        r = self.h.run("on")
        self.assertEqual(r.returncode, 1, f"rc={r.returncode} stderr={r.stderr!r}")
        self.assertIn("no backlight device found", r.stderr)



class PinetConfirm(unittest.TestCase):
    """pinet-confirm decides from the live unit state, so a stray double-click
    can't tear the hotspot down under whoever is connected. zenity is absent
    from the stub PATH, so have_gui() is false and the status branch runs
    headless -- which is exactly the part worth asserting."""

    UNITS = ["pinet-ap-network.service", "hostapd.service", "dnsmasq.service",
             "pinet-board.service", "stunnel@pinet-board.service"]

    def setUp(self):
        self.h = ShellHarness("scripts/bin/pinet-confirm")
        self.addCleanup(self.h.cleanup)
        # sudo drops its flags and runs the rest; pinet-start/stop just log.
        self.h._write_exec(self.h.bin / "sudo",
                           '#!/bin/bash\nwhile [ "${1:0:1}" = - ]; do shift; done\nexec "$@"\n')
        for name in ("pinet-start", "pinet-stop"):
            self.h._write_exec(
                self.h.bin / name,
                f'#!/bin/bash\necho "{name} ran" >> "$FAKE_DIR/calls.log"\necho "PINET {name}ed"\n')

    def ran(self, name):
        return any(line.startswith(name + " ran") for line in self.h.calls())

    def test_start_when_already_up_does_not_rerun(self):
        self.h.set_active(*self.UNITS)
        r = self.h.run("start")
        self.assertEqual(r.returncode, 0)
        self.assertFalse(self.ran("pinet-start"))

    def test_start_when_down_runs_it(self):
        self.h.set_active()
        r = self.h.run("start")
        self.assertEqual(r.returncode, 0)
        self.assertTrue(self.ran("pinet-start"))

    def test_start_when_partly_up_runs_it(self):
        self.h.set_active(*self.UNITS[:2])
        self.h.run("start")
        self.assertTrue(self.ran("pinet-start"))

    def test_stop_when_already_down_does_not_rerun(self):
        self.h.set_active()
        r = self.h.run("stop")
        self.assertEqual(r.returncode, 0)
        self.assertFalse(self.ran("pinet-stop"))

    def test_stop_when_up_runs_it(self):
        self.h.set_active(*self.UNITS)
        r = self.h.run("stop")
        self.assertEqual(r.returncode, 0)
        self.assertTrue(self.ran("pinet-stop"))

    def test_stop_when_partly_up_still_runs_it(self):
        self.h.set_active(self.UNITS[0])
        self.h.run("stop")
        self.assertTrue(self.ran("pinet-stop"))

    def test_bad_argument_is_usage_error(self):
        r = self.h.run("restart")
        self.assertEqual(r.returncode, 2)
        self.assertIn("usage", r.stderr)
        self.assertFalse(self.ran("pinet-start"))
        self.assertFalse(self.ran("pinet-stop"))

    def test_failure_is_reported_as_nonzero(self):
        self.h.set_active()
        self.h._write_exec(self.h.bin / "pinet-start",
                           '#!/bin/bash\necho "FAILED hostapd.service" >&2\nexit 1\n')
        r = self.h.run("start")
        self.assertEqual(r.returncode, 1)


if __name__ == "__main__":
    unittest.main()
