"""Shell scripts: syntax of everything, plus behaviour of kali-power-shed,
dsi-install-guard, wifi-pentest-stop and dsi-backlight.sh against PATH stubs.

Each behavioural test runs a copy of the real script whose hard-coded /run,
/sys and /usr/local paths are rewritten into a temp dir (see ShellHarness).
"""
import fcntl
import py_compile
import shutil
import signal
import subprocess
import tempfile
import time
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
    RUNNING = ("dsi-photo-frame.service", "rpi-connect-wayvnc.service",
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

    def test_set_saves_level_and_clamps(self):
        bl = self.make_device()
        (bl / "bl_power").write_text("0\n")   # screen on
        conf = self.h.dir / "dsi-screen"
        conf.write_text("# level\nBRIGHTNESS=255\n")
        r = self.h.run("set", "120")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual((bl / "brightness").read_text(), "120\n")
        self.assertEqual(conf.read_text(), "# level\nBRIGHTNESS=120\n")
        self.h.run("set", "3")
        self.assertEqual((bl / "brightness").read_text(), "26\n")   # 10% floor
        self.h.run("set", "99999")
        self.assertIn("BRIGHTNESS=255\n", conf.read_text())

    def test_set_while_asleep_only_saves(self):
        bl = self.make_device()                # bl_power=1: asleep
        conf = self.h.dir / "dsi-screen"
        conf.write_text("BRIGHTNESS=255\n")
        self.assertEqual(self.h.run("set", "60").returncode, 0)
        self.assertEqual(((bl / "brightness").read_text(), conf.read_text()), ("0\n", "BRIGHTNESS=60\n"))
        self.h.run("on")
        self.assertEqual((bl / "brightness").read_text(), "60\n")

    def test_set_rejects_non_numbers(self):
        self.make_device()
        conf = self.h.dir / "dsi-screen"
        conf.write_text("BRIGHTNESS=255\n")
        for bad in ("", "-5", "12; reboot", "abc"):
            r = self.h.run("set", bad)
            self.assertEqual(r.returncode, 1, bad)
        self.assertEqual(conf.read_text(), "BRIGHTNESS=255\n")

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



class PinetKeyboard(unittest.TestCase):
    """The taskbar icon and the pull-down tab both go through pinet-kbd; it
    must open exactly one keyboard -- even on a second tap while the first is
    still starting -- and close it every time."""

    def setUp(self):
        self.h = ShellHarness("scripts/bin/pinet-kbd")
        self.addCleanup(self.h.cleanup)
        for name in ("pkill", "setsid"):
            self.h._write_exec(self.h.bin / name,
                               f'#!/bin/bash\necho "{name} $*" >> "$FAKE_DIR/calls.log"\n')

    def open_tab(self):
        """Stand in for a running pinet-kbd-button: hold the lock, pid inside."""
        tab = subprocess.Popen(["sleep", "30"])
        self.addCleanup(tab.kill)
        lock = open(self.h.dir / "pinet-kbd.lock", "a+")
        self.addCleanup(lock.close)
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        lock.write(str(tab.pid)); lock.flush()
        return tab

    def run_kbd(self, *args):
        r = self.h.run(*args, env={"XDG_RUNTIME_DIR": str(self.h.dir)})
        for _ in range(25):  # setsid runs in the background
            if self.h.calls():
                break
            time.sleep(0.02)
        return r, " ".join(self.h.calls())

    def test_show_opens_the_keyboard(self):
        r, calls = self.run_kbd("show")
        self.assertEqual(r.returncode, 0)
        self.assertIn("pinet-kbd-button", calls)

    def test_second_tap_while_starting_opens_nothing(self):
        self.open_tab()
        r, calls = self.run_kbd("show")
        self.assertEqual((r.returncode, calls), (0, ""))

    def test_hide_closes_a_keyboard_still_starting(self):
        tab = self.open_tab()
        _, calls = self.run_kbd("hide")
        self.assertIn("pkill -x wvkbd-mobintl", calls)
        self.assertIsNotNone(tab.wait(timeout=5))

    def test_toggle_both_ways(self):
        tab = self.open_tab()
        _, calls = self.run_kbd("toggle")
        self.assertIn("pkill -x wvkbd-mobintl", calls)
        tab.wait(timeout=5)
        (self.h.dir / "calls.log").write_text("")
        (self.h.dir / "pinet-kbd.lock").unlink()
        _, calls = self.run_kbd("toggle")
        self.assertIn("pinet-kbd-button", calls)

    def test_stale_lock_file_is_not_open(self):
        (self.h.dir / "pinet-kbd.lock").write_text("999999")
        _, calls = self.run_kbd("show")
        self.assertIn("pinet-kbd-button", calls)

    def test_bad_argument_is_usage_error(self):
        r, calls = self.run_kbd("wiggle")
        self.assertEqual((r.returncode, calls), (2, ""))


class PinetConfirm(unittest.TestCase):
    """pinet-confirm decides from the live unit state, so a stray double-click
    can't tear the hotspot down under whoever is connected. zenity is absent
    from the stub PATH, so have_gui() is false and the status branch runs
    headless -- which is exactly the part worth asserting."""

    UNITS = ["pinet-ap-network.service", "hostapd.service", "dnsmasq.service",
             "pinet-board.service"]

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

    def test_state_reports_on_partly_off_without_touching_anything(self):
        for active, expected in (([], "off"), (self.UNITS[:2], "partly"), (self.UNITS, "on")):
            self.h.set_active(*active)
            r = self.h.run("state")
            self.assertEqual(r.stdout.strip(), expected)
        self.assertFalse(self.ran("pinet-start") or self.ran("pinet-stop"))

    def test_toggle_starts_what_is_down_and_stops_what_is_up(self):
        self.h.set_active()
        self.h.run("toggle")
        self.assertTrue(self.ran("pinet-start"))
        self.h.set_active(*self.UNITS)
        self.h.run("toggle")
        self.assertTrue(self.ran("pinet-stop"))

    def test_toggle_on_a_partly_up_service_starts_the_rest(self):
        self.h.set_active(*self.UNITS[:2])
        self.h.run("toggle")
        self.assertTrue(self.ran("pinet-start"))
        self.assertFalse(self.ran("pinet-stop"))

    def test_unknown_group_is_usage_error(self):
        r = self.h.run("start", "hifi")
        self.assertEqual(r.returncode, 2)
        self.assertIn("usage", r.stderr)

    def test_summary_lists_every_service_and_its_state(self):
        # The dialog after the action is the whole point: it must name all four
        # services and say which are up, not just echo pinet-start's last line.
        # (HTTPS is served by the board itself since stunnel went, 2026-10-07.)
        self.h.set_active(*self.UNITS[:3])
        r = self.h.run("stop")
        for label in ("Hotspot network", "Access point", "DHCP + DNS", "Message board"):
            self.assertIn(label, r.stdout)
        self.assertIn("stopped", r.stdout)

    def test_summary_is_printed_even_when_nothing_was_done(self):
        self.h.set_active()
        r = self.h.run("stop")
        self.assertIn("PINET is already stopped.", r.stdout)
        self.assertIn("Message board", r.stdout)

    def test_state_is_reread_after_the_action_not_assumed(self):
        # pinet-start "succeeds" but leaves two units down; the summary has to
        # show that rather than claiming PINET is up.
        self.h.set_active()
        self.h._write_exec(
            self.h.bin / "pinet-start",
            '#!/bin/bash\necho "pinet-start ran" >> "$FAKE_DIR/calls.log"\n'
            'for u in pinet-ap-network.service hostapd.service dnsmasq.service; do\n'
            '  echo "$u" >> "$FAKE_DIR/active"\ndone\nexit 0\n')
        r = self.h.run("start")
        self.assertEqual(r.returncode, 0)
        self.assertIn("only partly", r.stdout)
        self.assertIn("3 of 4", r.stdout)

    def test_zenity_is_forced_onto_the_cairo_renderer(self):
        # GTK4 zenity picks the GL renderer by default and the Pi 3B cannot
        # provide a GL context under labwc -- the dialog silently never
        # appears. Without this export the whole feature is invisible.
        src = (REPO / "scripts/bin/pinet-confirm").read_text()
        self.assertRegex(src, r"export .*GSK_RENDERER=cairo")

    def test_dialog_text_has_no_literal_backslash_n(self):
        # bash leaves a literal backslash-n alone inside double quotes, and zenity
        # prints it as one. Line breaks must come from $'...' or printf.
        src = (REPO / "scripts/bin/pinet-confirm").read_text()
        for line in src.splitlines():
            stripped = line.strip()
            if stripped.startswith(("prompt=\"", "headline=\"")):
                self.assertNotIn("\\n", stripped, line)
        self.h.set_active()
        self.h._write_exec(
            self.h.bin / "pinet-start",
            '#!/bin/bash\necho "pinet-start ran" >> "$FAKE_DIR/calls.log"\n'
            'for u in ' + " ".join(self.UNITS) + '; do\n'
            '  echo "$u" >> "$FAKE_DIR/active"\ndone\nexit 0\n')
        r = self.h.run("start")
        self.assertIn("PINET is up.", r.stdout)
        self.assertNotIn("\\n", r.stdout)

    def test_failure_is_reported_as_nonzero(self):
        self.h.set_active()
        self.h._write_exec(self.h.bin / "pinet-start",
                           '#!/bin/bash\necho "FAILED hostapd.service" >&2\nexit 1\n')
        r = self.h.run("start")
        self.assertEqual(r.returncode, 1)


if __name__ == "__main__":
    unittest.main()

class SpotifyConfirm(unittest.TestCase):
    """The same wrapper drives Spotify: one system unit, one user unit."""

    UNITS = ["raspotify.service", "raspotify-bt-guard.service"]

    def setUp(self):
        self.h = ShellHarness("scripts/bin/pinet-confirm")
        self.addCleanup(self.h.cleanup)
        self.h._write_exec(self.h.bin / "sudo",
                           '#!/bin/bash\nwhile [ "${1:0:1}" = - ]; do shift; done\nexec "$@"\n')
        self.h._write_exec(
            self.h.bin / "wpctl",
            '#!/bin/bash\nprintf "Sinks:\\n *   90. Dubstep Pop 600   [vol: 1.00]\\n"\n')

    def started(self, unit):
        return any(l.startswith(f"systemctl start {unit}")
                   or l.startswith(f"systemctl --user start {unit}") for l in self.h.calls())

    def test_start_brings_up_both_units(self):
        self.h.set_active()
        r = self.h.run("start", "spotify")
        self.assertEqual(r.returncode, 0)
        for unit in self.UNITS:
            self.assertTrue(self.started(unit), f"{unit} not started")

    def test_start_when_already_running_does_nothing(self):
        self.h.set_active(*self.UNITS)
        r = self.h.run("start", "spotify")
        self.assertEqual(r.returncode, 0)
        self.assertIn("already running", r.stdout)
        self.assertFalse(any(" start " in l for l in self.h.calls()))

    def test_stop_takes_the_guard_down_first(self):
        # The guard's ExecStop un-pauses librespot, so raspotify must not go
        # down before it -- that would leave a frozen process behind.
        self.h.set_active(*self.UNITS)
        r = self.h.run("stop", "spotify")
        self.assertEqual(r.returncode, 0)
        stops = [l for l in self.h.calls() if " stop " in l]
        self.assertTrue(stops[0].endswith("raspotify-bt-guard.service"), stops)
        self.assertTrue(stops[1].endswith("raspotify.service"), stops)

    def test_stop_when_already_off_does_nothing(self):
        self.h.set_active()
        r = self.h.run("stop", "spotify")
        self.assertIn("already stopped", r.stdout)
        self.assertFalse(any(" stop " in l for l in self.h.calls()))

    def test_report_says_where_the_sound_goes(self):
        # "running, running" tells you nothing when the speaker is off.
        self.h.set_active(*self.UNITS)
        r = self.h.run("start", "spotify")
        self.assertIn("Playing to", r.stdout)
        self.assertIn("Dubstep Pop 600", r.stdout)


class RaspotifyGuard(unittest.TestCase):
    """The speaker guard freezes librespot only when freezing is the answer:
    playing, with the sound going nowhere useful. A real background process
    stands in for librespot, so the SIGSTOP/SIGCONT are really sent and the
    assertions read its actual state out of /proc."""

    def setUp(self):
        self.h = ShellHarness("scripts/bin/raspotify-bt-guard")
        self.addCleanup(self.h.cleanup)
        self.proc = subprocess.Popen(["sleep", "60"])
        self.addCleanup(self.stop_proc)
        self.h._write_exec(self.h.bin / "pgrep", f"#!/bin/bash\necho {self.proc.pid}\n")
        self.h._write_exec(self.h.bin / "logger",
                           '#!/bin/bash\necho "logger $*" >> "$FAKE_DIR/calls.log"\n')
        self.h._write_exec(self.h.bin / "sudo",
                           '#!/bin/bash\nwhile [ "${1:0:1}" = - ]; do shift; done\nexec "$@"\n')
        self.sink("Built-in Audio Stereo")

    def stop_proc(self):
        self.proc.send_signal(signal.SIGCONT)   # never leave it stopped
        self.proc.kill()
        self.proc.wait()

    def sink(self, name, streams=""):
        """wpctl status with *name* as the default sink."""
        body = f"Sinks:\\n *   90. {name}   [vol: 1.00]\\nStreams:\\n{streams}"
        self.h._write_exec(self.h.bin / "wpctl", f'#!/bin/bash\nprintf "{body}\\n"\n')

    def say(self, state):
        (self.h.dir / "raspotify-nowplaying").write_text(f"state={state}\n")

    def guard(self, ticks=1, **env):
        return self.h.run(env={"XDG_RUNTIME_DIR": str(self.h.dir),
                               "GUARD_TICKS": str(ticks), **env})

    def proc_state(self):
        return Path(f"/proc/{self.proc.pid}/stat").read_text().rsplit(") ", 1)[1].split()[0]

    def frozen(self):
        return self.proc_state() == "T"

    def restarted(self):
        return any("restart raspotify.service" in c for c in self.h.calls())

    def test_playing_into_the_builtin_card_is_frozen(self):
        self.say("playing")
        self.guard()
        self.assertTrue(self.frozen())

    def test_a_speaker_resumes_it(self):
        self.proc.send_signal(signal.SIGSTOP)
        self.say("playing")
        self.sink("Dubstep Pop 600")
        self.guard()
        self.assertFalse(self.frozen())

    def test_any_speaker_counts_not_just_one_name(self):
        # The old guard was pinned to one speaker's name, so playing to the
        # other paired speaker froze librespot for as long as it played.
        self.say("playing")
        self.sink("Aavante Bar 1550")
        self.guard()
        self.assertFalse(self.frozen())

    def test_bt_speaker_pins_it_to_one_sink(self):
        self.say("playing")
        self.sink("Aavante Bar 1550")
        self.guard(BT_SPEAKER="Dubstep Pop 600")
        self.assertTrue(self.frozen())

    def test_idle_is_left_running_so_spotify_still_sees_the_pi(self):
        self.say("idle")
        self.guard()
        self.assertFalse(self.frozen())

    def test_without_a_state_file_it_still_freezes(self):
        # No --onevent hook writing state: fall back to the old behaviour
        # rather than never pausing and playing into the built-in card.
        self.guard()
        self.assertTrue(self.frozen())

    def test_a_long_freeze_restarts_raspotify(self):
        # A speaker that never comes back would otherwise leave librespot
        # frozen mid-track and missing from Spotify for good.
        self.say("playing")
        self.guard(FREEZE_LIMIT="0")
        self.assertTrue(self.restarted())

    def test_playing_with_no_stream_restarts_raspotify(self):
        self.proc.send_signal(signal.SIGSTOP)
        self.say("playing")
        self.sink("Dubstep Pop 600")            # resumed, but no stream on it
        self.guard(STREAM_GRACE="0")
        self.assertTrue(self.restarted())

    def test_a_connected_speaker_is_routed_instead_of_pausing(self):
        # Right after a reconnect the speaker is usually not the default sink.
        # Pausing then would strand a player that has somewhere to go.
        self.h._write_exec(self.h.bin / "spotify-audio-route",
                           "#!/bin/bash\necho \"router ran\" >> \"$FAKE_DIR/calls.log\"\n"
                           "echo \"Aavante Bar 1550 at 150%\"\n")
        self.say("playing")
        self.guard()
        self.assertIn("router ran", self.h.calls())
        self.assertFalse(self.frozen())

    def test_it_still_pauses_when_no_speaker_can_be_routed(self):
        self.h._write_exec(self.h.bin / "spotify-audio-route",
                           "#!/bin/bash\necho \"router ran\" >> \"$FAKE_DIR/calls.log\"\nexit 1\n")
        self.say("playing")
        self.guard()
        self.assertIn("router ran", self.h.calls())
        self.assertTrue(self.frozen())

    def test_playing_with_a_stream_is_left_alone(self):
        self.proc.send_signal(signal.SIGSTOP)
        self.say("playing")
        self.sink("Dubstep Pop 600", streams=" *   95. librespot")
        self.guard(STREAM_GRACE="0")
        self.assertFalse(self.restarted())
        self.assertFalse(self.frozen())



WPCTL_STUB = """#!/bin/bash
echo "wpctl $*" >> "$FAKE_DIR/calls.log"
case "${1:-}" in
  status)  cat "$FAKE_DIR/status" ;;
  inspect) cat "$FAKE_DIR/inspect-${2:-}" 2>/dev/null ;;
esac
exit 0
"""

SINKS = (" |- Sinks:\n"
         " |      68. Built-in Audio Stereo     [vol: 0.88]\n"
         " |  *   90. Dubstep Pop 600           [vol: 1.00]\n"
         " |  \n"
         " |- Sources:\n")


class SpotifyAudioRoute(unittest.TestCase):
    """spotify-audio-route picks a *connected Bluetooth* sink -- whichever one
    is switched on -- makes it the default and pins its level, so the phone's
    own slider decides the loudness instead of whatever the speaker
    remembered from last time."""

    def setUp(self):
        self.h = ShellHarness("scripts/bin/spotify-audio-route")
        self.addCleanup(self.h.cleanup)
        self.h._write_exec(self.h.bin / "wpctl", WPCTL_STUB)
        self.status(SINKS)
        self.node(68, "alsa_output.platform-3f00b840.mailbox.stereo-fallback", "Built-in Audio Stereo")
        self.node(90, "bluez_output.5E_2B_AA_77_66_A8.1", "Dubstep Pop 600")

    def status(self, text):
        (self.h.dir / "status").write_text(text)

    def node(self, sink_id, name, description):
        (self.h.dir / f"inspect-{sink_id}").write_text(
            f'  * node.name = "{name}"\n  * node.description = "{description}"\n')

    def route(self, *args, **env):
        return self.h.run(*args, env={"XDG_RUNTIME_DIR": str(self.h.dir), **env})

    def test_routes_to_the_connected_bluetooth_sink(self):
        r = self.route()
        self.assertEqual(r.returncode, 0)
        self.assertIn("wpctl set-default 90", self.h.calls())
        self.assertIn("wpctl set-volume 90 1.5", self.h.calls())

    def test_never_routes_to_the_builtin_card(self):
        self.route()
        self.assertNotIn("wpctl set-default 68", self.h.calls())

    def test_says_what_it_picked_and_how_loud(self):
        r = self.route()
        self.assertIn("Dubstep Pop 600", r.stdout)
        self.assertIn("150%", r.stdout)

    def test_reports_the_level_the_phone_is_asking_for(self):
        (self.h.dir / "raspotify-nowplaying").write_text("state=playing\nvolume_pct=72\n")
        self.assertIn("phone at 72%", self.route().stdout)

    def test_bt_speaker_picks_between_two_speakers(self):
        self.status(SINKS.replace(" |  \n",
                                  " |      92. Aavante Bar 1550          [vol: 0.40]\n |  \n"))
        self.node(92, "bluez_output.F4_4E_FD_2D_42_3D.1", "Aavante Bar 1550")
        self.route(BT_SPEAKER="Aavante Bar 1550")
        self.assertIn("wpctl set-default 92", self.h.calls())

    def test_no_speaker_connected_is_a_clean_failure(self):
        self.status(" |- Sinks:\n |      68. Built-in Audio Stereo     [vol: 0.88]\n")
        r = self.route()
        self.assertEqual(r.returncode, 1)
        self.assertIn("no Bluetooth speaker", r.stderr)
        self.assertFalse([c for c in self.h.calls() if "set-" in c])

    def test_print_changes_nothing(self):
        r = self.route("--print")
        self.assertEqual(r.stdout.strip(), "Dubstep Pop 600")
        self.assertFalse([c for c in self.h.calls() if "set-" in c])


class NowPlayingHook(unittest.TestCase):
    """The --onevent hook carries librespot's volume, so the router can say
    what the phone is asking for. librespot sends it with volume_changed and
    with nothing else, so it has to survive the other events."""

    def setUp(self):
        self.h = ShellHarness("scripts/bin/raspotify-nowplaying-hook")
        self.addCleanup(self.h.cleanup)

    def fire(self, event, **env):
        self.h.run(env={"XDG_RUNTIME_DIR": str(self.h.dir), "PLAYER_EVENT": event, **env})
        text = (self.h.dir / "raspotify-nowplaying").read_text()
        return dict(l.split("=", 1) for l in text.splitlines() if "=" in l)

    def test_volume_is_recorded_as_a_percentage(self):
        self.assertEqual(self.fire("volume_changed", VOLUME="65535")["volume_pct"], "100")
        self.assertEqual(self.fire("volume_changed", VOLUME="32768")["volume_pct"], "50")
        self.assertEqual(self.fire("volume_changed", VOLUME="0")["volume_pct"], "0")

    def test_volume_survives_events_that_do_not_carry_it(self):
        self.fire("volume_changed", VOLUME="32768")
        self.assertEqual(self.fire("playing")["volume_pct"], "50")
        self.assertEqual(self.fire("paused")["state"], "paused")



class IconState(unittest.TestCase):
    """pinet-icon-state rewrites the Icon= line of the desktop toggles so the
    icon is green while the service runs. pcmanfm reloads a .desktop when it
    changes -- which is also why the rewrite must not leave a temp file in the
    desktop folder, or that temp file shows up as a desktop item."""

    ENTRY = ("[Desktop Entry]\nType=Application\nName={name}\n"
             "Exec=/usr/local/bin/pinet-confirm toggle {group}\n"
             "Icon={icons}/{group}-off.svg\nTerminal=false\n")

    def setUp(self):
        self.h = ShellHarness("scripts/bin/pinet-icon-state")
        self.addCleanup(self.h.cleanup)
        self.desktop = self.h.dir / "Desktop"
        self.icons = self.h.dir / "icons"
        self.desktop.mkdir()
        self.icons.mkdir()
        for group, name in (("pinet", "PINET"), ("spotify", "Spotify")):
            (self.desktop / f"{group}.desktop").write_text(
                self.ENTRY.format(name=name, group=group, icons=self.icons))
        self.says("off")

    def says(self, state):
        """Stand in for pinet-confirm state <group>."""
        self.h._write_exec(self.h.bin / "pinet-confirm",
                           f"#!/bin/bash\necho {state}\n")

    def icon_of(self, group):
        for line in (self.desktop / f"{group}.desktop").read_text().splitlines():
            if line.startswith("Icon="):
                return Path(line.split("=", 1)[1]).name
        return None

    def run_it(self, **env):
        return self.h.run(env={"DESKTOP_DIR": str(self.desktop),
                               "ICON_DIR": str(self.icons), **env})

    def test_running_service_gets_the_green_icon(self):
        self.says("on")
        self.run_it()
        self.assertEqual(self.icon_of("pinet"), "pinet-on.svg")
        self.assertEqual(self.icon_of("spotify"), "spotify-on.svg")

    def test_partly_up_counts_as_running(self):
        self.says("partly")
        self.run_it()
        self.assertEqual(self.icon_of("pinet"), "pinet-on.svg")

    def test_stopped_service_goes_back_to_ink(self):
        self.says("on")
        self.run_it()
        self.says("off")
        self.run_it()
        self.assertEqual(self.icon_of("pinet"), "pinet-off.svg")

    def test_nothing_is_rewritten_when_the_icon_is_already_right(self):
        before = (self.desktop / "pinet.desktop").stat().st_mtime_ns
        self.run_it()
        self.assertEqual((self.desktop / "pinet.desktop").stat().st_mtime_ns, before)

    def test_no_temp_file_is_left_on_the_desktop(self):
        self.says("on")
        self.run_it()
        self.assertEqual(sorted(p.name for p in self.desktop.iterdir()),
                         ["pinet.desktop", "spotify.desktop"])

    def test_the_rest_of_the_entry_survives(self):
        self.says("on")
        self.run_it()
        text = (self.desktop / "pinet.desktop").read_text()
        self.assertIn("Exec=/usr/local/bin/pinet-confirm toggle pinet", text)
        self.assertIn("Name=PINET", text)

    def test_an_unreadable_state_leaves_the_icon_alone(self):
        self.h._write_exec(self.h.bin / "pinet-confirm", "#!/bin/bash\nexit 1\n")
        self.run_it()
        self.assertEqual(self.icon_of("pinet"), "pinet-off.svg")

    # eth-share isn't a set of systemd units, so its icon follows the
    # /run/eth-share flag directly, not pinet-confirm.
    def _make_eth_share(self):
        (self.desktop / "eth-share.desktop").write_text(
            self.ENTRY.format(name="Ethernet Share", group="eth-share", icons=self.icons))
        return self.h.dir / "eth-share.flag"

    def test_eth_share_icon_is_green_while_the_flag_exists(self):
        flag = self._make_eth_share()
        flag.write_text("on\n")
        self.h.run(env={"DESKTOP_DIR": str(self.desktop), "ICON_DIR": str(self.icons),
                        "ICON_GROUPS": "eth-share", "ETH_SHARE_FLAG": str(flag)})
        self.assertEqual(self.icon_of("eth-share"), "eth-share-on.svg")

    def test_eth_share_icon_is_ink_without_the_flag(self):
        flag = self._make_eth_share()   # not created
        self.h.run(env={"DESKTOP_DIR": str(self.desktop), "ICON_DIR": str(self.icons),
                        "ICON_GROUPS": "eth-share", "ETH_SHARE_FLAG": str(flag)})
        self.assertEqual(self.icon_of("eth-share"), "eth-share-off.svg")


class NetChanged(unittest.TestCase):
    """The NetworkManager hook re-announces Spotify when the Pi's uplink
    changes -- move the Pi to another Wi-Fi and the old announcement is what a
    phone on the new network would (not) find."""

    def setUp(self):
        self.h = ShellHarness("etc/NetworkManager/dispatcher.d/90-pinet-net-changed")
        self.addCleanup(self.h.cleanup)
        self.h._write_exec(self.h.bin / "logger",
                           '#!/bin/bash\necho "logger $*" >> "$FAKE_DIR/calls.log"\n')
        self.h.set_active("raspotify.service")
        self.stamp = self.h.dir / "stamp"

    def fire(self, iface="wlan1", action="up", **env):
        return self.h.run(iface, action,
                          env={"NET_CHANGED_STAMP": str(self.stamp), **env})

    def restarts(self):
        return [c for c in self.h.calls() if c.startswith("systemctl restart raspotify")]

    def test_uplink_coming_up_re_announces(self):
        self.fire()
        self.assertEqual(len(self.restarts()), 1)

    def test_a_new_lease_on_the_same_network_also_counts(self):
        self.fire(action="dhcp4-change")
        self.assertEqual(len(self.restarts()), 1)

    def test_the_hotspot_interface_is_not_an_uplink(self):
        # wlan0 goes up and down every time PINET is toggled, and it is not
        # the Pi's way out to Spotify.
        self.fire(iface="wlan0")
        self.assertEqual(self.restarts(), [])

    def test_going_down_changes_nothing(self):
        self.fire(action="down")
        self.assertEqual(self.restarts(), [])

    def test_nothing_to_re_announce_when_the_player_is_off(self):
        self.h.set_active()
        self.fire()
        self.assertEqual(self.restarts(), [])

    def test_the_burst_of_events_one_connect_fires_restarts_once(self):
        for action in ("up", "dhcp4-change", "connectivity-change"):
            self.fire(action=action)
        self.assertEqual(len(self.restarts()), 1)

    def test_a_later_change_restarts_again(self):
        self.fire()
        self.stamp.write_text("1")          # long past the debounce window
        self.fire()
        self.assertEqual(len(self.restarts()), 2)


class PinetSplashGuard(HarnessCase):
    SCRIPT = "scripts/sbin/pinet-splash-guard"
    REWRITES = {"/usr/share/plymouth/themes": "{tmp}/themes"}

    def stub(self, name, body):
        self.h._write_exec(self.h.bin / name, "#!/bin/bash\n" + body)

    def setUp(self):
        super().setUp()
        (self.h.dir / "themes" / "pinet").mkdir(parents=True)
        self.stub("logger", 'echo "logger $*" >> "$FAKE_DIR/calls.log"\n')

    def theme(self, current, rc=0):
        self.stub("plymouth-set-default-theme",
                  f'[ $# -eq 0 ] && {{ echo {current}; exit 0; }}\n'
                  f'echo "plymouth-set-default-theme $*" >> "$FAKE_DIR/calls.log"; exit {rc}\n')

    def test_pinet_already_set_does_nothing(self):
        self.theme("pinet")
        self.assertEqual(self.h.run().returncode, 0)
        self.assertEqual(self.h.calls(), [])

    def test_reset_theme_is_restored_with_initramfs_rebuild(self):
        self.theme("pix")
        self.assertEqual(self.h.run().returncode, 0)
        self.assertIn("plymouth-set-default-theme -R pinet", self.h.calls())

    def test_failed_restore_is_logged_but_never_fails_dpkg(self):
        self.theme("pix", rc=1)
        self.assertEqual(self.h.run().returncode, 0)
        self.assertTrue(any("failed" in c for c in self.h.calls()))

    def test_missing_theme_is_a_noop(self):
        (self.h.dir / "themes" / "pinet").rmdir()
        self.theme("pix")
        self.assertEqual(self.h.run().returncode, 0)
        self.assertEqual(self.h.calls(), [])


class HdmiMonitorDevice(unittest.TestCase):
    """hdmi-monitor finds a UVC capture node by driver, not by name or number."""

    def find(self, nodes):
        tmp = Path(tempfile.mkdtemp(prefix="pinet-v4l-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        for node, (name, index, driver) in nodes.items():
            (tmp / node / "device").mkdir(parents=True)
            (tmp / "drivers" / driver).mkdir(parents=True, exist_ok=True)
            (tmp / node / "device" / "driver").symlink_to(tmp / "drivers" / driver)
            (tmp / node / "name").write_text(name + "\n")
            (tmp / node / "index").write_text(f"{index}\n")
        r = subprocess.run(["/bin/bash", str(REPO / "scripts/bin/hdmi-monitor"), "--device"],
                           env={"PATH": "/usr/bin:/bin", "HDMI_MONITOR_SYSFS": str(tmp)},
                           capture_output=True, text=True)
        return r.returncode, r.stdout.strip()

    def test_capture_node_not_metadata_or_csi(self):
        rc, dev = self.find({"video0": ("unicam-image", 0, "unicam"),
                             "video3": ("USB2 Video: USB2 Video", 1, "uvcvideo"),
                             "video4": ("USB2 Video: USB2 Video", 0, "uvcvideo")})
        self.assertEqual((rc, dev), (0, "/dev/video4"))

    def test_any_dongle_model(self):
        rc, dev = self.find({"video0": ("unicam-image", 0, "unicam"),
                             "video1": ("USB3. 0 capture: USB3. 0 captur", 0, "uvcvideo"),
                             "video2": ("USB3. 0 capture: USB3. 0 captur", 1, "uvcvideo")})
        self.assertEqual((rc, dev), (0, "/dev/video1"))

    def test_missing_dongle_fails(self):
        self.assertEqual(self.find({"video0": ("unicam-image", 0, "unicam")})[0], 1)


class HdmiMonitorSingleInstance(unittest.TestCase):
    """A second tap while the monitor is open must not start a second player
    or delete the running one's monitor-mode flag."""

    def setUp(self):
        self.h = ShellHarness("scripts/bin/hdmi-monitor",
                              rewrites={"/run/user/$(id -u)": "{tmp}"})
        self.addCleanup(self.h.cleanup)
        sysfs = self.h.dir / "v4l" / "video1"
        (sysfs / "device").mkdir(parents=True)
        (self.h.dir / "drivers" / "uvcvideo").mkdir(parents=True)
        (sysfs / "device" / "driver").symlink_to(self.h.dir / "drivers" / "uvcvideo")
        (sysfs / "index").write_text("0\n")
        stub = '#!/bin/bash\necho "{0} $*" >> "$FAKE_DIR/calls.log"\n{1}\n'
        # ffplay: "quits" (exit 0, like q/Esc) after FAKE_PLAYER_QUIT seconds,
        # else plays until killed.
        ShellHarness._write_exec(self.h.bin / "ffplay", stub.format(
            "ffplay", '[ -n "${FAKE_PLAYER_QUIT:-}" ] && { /bin/sleep "$FAKE_PLAYER_QUIT"; exit 0; }\n'
                      'exec /bin/sleep 60'))
        # ffmpeg: counts frames into its -progress file every 0.2 s. On its
        # first run it freezes after FAKE_STALL_AFTER frames (a dead USB
        # stream); FAKE_NO_FRAMES makes every run produce none (device busy).
        ShellHarness._write_exec(self.h.bin / "ffmpeg", stub.format("ffmpeg", r'''
for a; do [ "${prev:-}" = -progress ] && P=${a#file:}; prev=$a; done
n=$(( $(cat "$FAKE_DIR/ffmpeg.runs" 2>/dev/null || echo 0) + 1 )); echo $n > "$FAKE_DIR/ffmpeg.runs"
[ -n "${FAKE_NO_FRAMES:-}" ] && exit 1
exec 5> "$P"; i=0
while :; do
    if [ $n = 1 ] && [ $i -ge "${FAKE_STALL_AFTER:-1000000}" ]; then exec /bin/sleep 60; fi
    i=$((i + 1)); echo "frame=$i" >&5; echo "progress=continue" >&5; /bin/sleep 0.2
done'''))
        ShellHarness._write_exec(self.h.bin / "python3", stub.format("python3", "exec /bin/sleep 30"))
        ShellHarness._write_exec(self.h.bin / "zenity", stub.format("zenity", ""))
        # Like logger(1): logs its arguments, or stdin when there are none.
        ShellHarness._write_exec(self.h.bin / "logger", '#!/bin/bash\n[ $# -gt 2 ] || cat >/dev/null\n')
        self.env = {"HDMI_MONITOR_SYSFS": str(self.h.dir / "v4l"), "WAYLAND_DISPLAY": "w",
                    "HDMI_MONITOR_STALL": "2", "FAKE_PLAYER_QUIT": "3"}

    def start(self, **env):
        p = subprocess.Popen(["/bin/bash", str(self.h.script)],
                             env={"PATH": f"{self.h.bin}:/usr/bin:/bin", "FAKE_DIR": str(self.h.dir),
                                  **self.env, **env})
        self.addCleanup(p.kill)
        return p

    def runs(self, name):
        return sum(c.startswith(name) for c in self.h.calls())

    def test_second_launch_is_a_no_op(self):
        first = self.start()
        self.addCleanup(first.kill)
        flag = self.h.dir / "monitor-mode"
        for _ in range(50):
            if flag.exists():
                break
            time.sleep(0.05)
        r = self.h.run(env=self.env)
        self.assertEqual(r.returncode, 0)
        self.assertTrue(flag.exists())   # the running monitor still owns it
        self.assertEqual(sum(c.startswith("ffplay") for c in self.h.calls()), 1)
        # Wakes the screen on start (it may be asleep, e.g. launched remotely).
        self.assertEqual(sum(c.startswith("dsi-wake.sh") for c in self.h.calls()), 1)
        self.assertFalse(any(c.startswith("zenity") for c in self.h.calls()))
        first.wait(timeout=10)
        self.assertFalse(flag.exists())

    def test_frozen_stream_restarts(self):
        p = self.start(FAKE_STALL_AFTER="5", FAKE_PLAYER_QUIT="")
        for _ in range(100):   # 1 s of frames, a 2 s stall, then a restart
            if self.runs("ffmpeg") >= 2:
                break
            time.sleep(0.1)
        self.assertEqual((self.runs("ffmpeg"), self.runs("ffplay")), (2, 2))
        time.sleep(3)   # the new stream keeps flowing: no further restarts
        self.assertEqual(self.runs("ffmpeg"), 2)
        p.terminate()   # what the close button does
        self.assertEqual(p.wait(timeout=10), 0)
        self.assertFalse((self.h.dir / "monitor-mode").exists())
        self.assertFalse(any(c.startswith("zenity") for c in self.h.calls()))

    def test_closing_the_player_does_not_restart(self):
        self.assertEqual(self.start(FAKE_PLAYER_QUIT="1").wait(timeout=15), 0)
        self.assertEqual(self.runs("ffmpeg"), 1)

    def test_never_starting_gives_up_with_a_message(self):
        self.assertEqual(self.start(FAKE_NO_FRAMES="1", FAKE_PLAYER_QUIT="").wait(timeout=60), 1)
        self.assertEqual(self.runs("ffmpeg"), 3)
        self.assertEqual(self.runs("zenity"), 1)


class DsiSleepStaysAwake(unittest.TestCase):
    """dsi-sleep.sh (swayidle's 90 s timeout) never blanks the HDMI monitor."""

    def setUp(self):
        self.h = ShellHarness("scripts/bin/dsi-sleep.sh")
        self.addCleanup(self.h.cleanup)
        ShellHarness._write_exec(self.h.bin / "sudo", '#!/bin/bash\necho "sudo $*" >> "$FAKE_DIR/calls.log"\n')

    def blanked(self):
        r = self.h.run(env={"XDG_RUNTIME_DIR": str(self.h.dir)})
        self.assertEqual(r.returncode, 0, r.stderr)
        return any("dsi-backlight.sh off" in c for c in self.h.calls())

    def test_sleeps_when_idle(self):
        self.assertTrue(self.blanked())

    def test_stays_lit_while_monitor_open(self):
        (self.h.dir / "monitor-mode").touch()
        self.assertFalse(self.blanked())
        self.assertIn("systemctl --user try-restart dsi-idle-sleep.service", self.h.calls())
