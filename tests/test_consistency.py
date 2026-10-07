"""Repo consistency: every installed path the repo points at is shipped by it.

Install mapping used (from README / install scripts):
  /usr/local/bin/X            -> scripts/bin/X
  /usr/local/sbin/X           -> scripts/sbin/X
  /opt/pinet-board/X          -> pinet-board/X
  /home/pi/pi-eink-dashboard/ -> eink-dashboard/
  ~/.local/share/icons/X      -> desktop/icons/X
"""
import configparser
import re
import unittest

from _support import REPO, repo_path

INSTALL_MAP = {
    "/usr/local/bin/": "scripts/bin/",
    "/usr/local/sbin/": "scripts/sbin/",
    "/opt/pinet-board/": "pinet-board/",
    "/home/pi/pi-eink-dashboard/": "eink-dashboard/",
    "/home/rupal/.local/share/icons/": "desktop/icons/",
}
# Freedesktop icon-theme names that any desktop provides.
THEME_ICONS = {"camera-photo", "image-x-generic", "utilities-terminal", "system-lock-screen"}
# Units provided by Debian / Raspberry Pi OS packages, not by this repo.
DISTRO_UNITS = {
    "bluetooth.service", "dbus-org.bluez.service", "hostapd.service", "dnsmasq.service",
    "wayvnc.service", "rpi-connect-wayvnc.service",
    "lightdm.service", "raspotify.service",
}
SOURCE_DIRS = ("scripts", "desktop", "systemd", "etc", "pinet-board", "eink-dashboard/scripts",
               "eink-dashboard/systemd", "eink-dashboard/src")


def repo_file_for(installed):
    for prefix, rel in INSTALL_MAP.items():
        if installed.startswith(prefix):
            return repo_path(rel + installed[len(prefix):])
    return None


def desktop_entries():
    out = {}
    for p in sorted(repo_path("desktop").glob("*.desktop")):
        cp = configparser.ConfigParser(interpolation=None, strict=False)
        cp.optionxform = str
        cp.read(p)
        out[p.name] = cp["Desktop Entry"]
    return out


def source_files():
    for d in SOURCE_DIRS:
        for p in sorted(repo_path(d).rglob("*")):
            if p.is_file() and p.suffix not in {".ttf", ".png", ".crt", ".svg"}:
                yield p


def shipped_units():
    return {p.name for d in ("systemd", "eink-dashboard/systemd") for p in repo_path(d).rglob("*")
            if p.suffix in (".service", ".timer")}


def referenced_units():
    refs = {}
    pat = re.compile(r"[A-Za-z0-9@_.-]+\.(?:service|timer)\b")
    for p in source_files():
        for m in pat.findall(p.read_text(errors="replace")):
            refs.setdefault(m, set()).add(str(p.relative_to(REPO)))
    return refs


class Consistency(unittest.TestCase):
    maxDiff = None

    def test_camera_controls_open_the_folder_the_server_writes_to(self):
        # The FILES button is only useful if it lands where captures go, and
        # the two scripts each keep their own copy of that path.
        server = repo_path("scripts/bin/dsi-cam-server.py").read_text()
        controls = repo_path("scripts/bin/dsi-cam-controls.py").read_text()
        pat = re.compile(r'^MEDIA_DIR = "([^"]+)"', re.M)
        self.assertEqual(pat.findall(server), pat.findall(controls))
        self.assertTrue(pat.findall(server), "MEDIA_DIR not found in cam server")

    def test_desktop_exec_targets_ship(self):
        missing = []
        for name, e in desktop_entries().items():
            for tok in e["Exec"].split():
                f = repo_file_for(tok)
                if f is not None and not f.is_file():
                    missing.append(f"{name}: {tok}")
        self.assertEqual(missing, [])

    def test_desktop_icon_paths_ship(self):
        missing = []
        for name, e in desktop_entries().items():
            icon = e.get("Icon", "")
            if icon.startswith("/"):
                f = repo_file_for(icon)
                if f is None or not f.is_file():
                    missing.append(f"{name}: {icon}")
        self.assertEqual(missing, [])

    # QA-12: pinet-board.desktop uses Icon=pinet-portal, which is neither a theme icon
    # nor shipped in desktop/icons.
    def test_named_custom_icons_ship(self):
        missing = []
        for name, e in desktop_entries().items():
            icon = e.get("Icon", "")
            if icon and not icon.startswith("/") and icon not in THEME_ICONS:
                if not list(repo_path("desktop", "icons").glob(icon + ".*")):
                    missing.append(f"{name}: Icon={icon}")
        self.assertEqual(missing, [])

    def test_systemd_exec_paths_ship(self):
        missing = []
        pat = re.compile(r"^Exec\w*=-?(.*)$", re.M)
        for p in [*repo_path("systemd").rglob("*"), *repo_path("eink-dashboard", "systemd").rglob("*")]:
            if not p.is_file():
                continue
            for cmd in pat.findall(p.read_text()):
                for tok in cmd.split():
                    f = repo_file_for(tok)
                    if f is not None and not f.is_file():
                        missing.append(f"{p.name}: {tok}")
        self.assertEqual(missing, [])

    def test_usr_local_references_ship(self):
        pat = re.compile(r"/usr/local/s?bin/[A-Za-z0-9_.-]+")
        missing = set()
        count = 0
        for p in source_files():
            for ref in pat.findall(p.read_text(errors="replace")):
                count += 1
                if not repo_file_for(ref).is_file():
                    missing.add(f"{p.relative_to(REPO)}: {ref}")
        self.assertGreater(count, 40)
        self.assertEqual(sorted(missing), [])

    # QA-15: custom units that scripts start/stop/enable are not shipped in systemd/.
    @unittest.expectedFailure
    def test_custom_units_referenced_by_scripts_are_shipped(self):
        shipped = shipped_units()
        missing = {u: sorted(files) for u, files in referenced_units().items()
                   if u not in shipped and u not in DISTRO_UNITS}
        self.assertEqual(missing, {})

    # QA-15: the pi-power-manager daemon (docs/systemd service.md names
    # pi-power-manager.service) has no unit file in the repo.
    @unittest.expectedFailure
    def test_pi_power_manager_has_a_unit(self):
        self.assertIn("pi-power-manager.service", shipped_units())

    # QA-15: config the scripts depend on is not shipped under etc/, and README lists a
    # `cam` script in scripts/bin that does not exist.
    @unittest.expectedFailure
    def test_referenced_etc_files_and_readme_scripts_ship(self):
        missing = []
        if "stunnel@pinet-board.service" in referenced_units() and \
                not repo_path("etc", "stunnel", "pinet-board.conf").is_file():
            missing.append("etc/stunnel/pinet-board.conf (for stunnel@pinet-board.service)")
        if "80dsi-install-guard" in repo_path("scripts", "sbin", "dsi-install-guard").read_text() and \
                not repo_path("etc", "apt", "apt.conf.d", "80dsi-install-guard").is_file():
            missing.append("etc/apt/apt.conf.d/80dsi-install-guard (hook config for dsi-install-guard)")
        if re.search(r"bin/.*\(dsi-\*, cam\)", repo_path("README.md").read_text()) and \
                not repo_path("scripts", "bin", "cam").exists():
            missing.append("scripts/bin/cam (listed in README)")
        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
