"""pinet-updates pure logic: reading versions and deciding what a row says.

The commands themselves (git, curl, apt, pinet-update) are covered by the
on-Pi run; what decides whether a module can be selected is pure and tested
here, against output captured from the Pi.
"""
import unittest

from _support import load_defs

UP = load_defs(
    "scripts/bin/pinet-updates",
    ["tool_version", "version_from_release_url", "version_from_json", "sha_from_git",
     "pihole_versions", "apt_policy", "parse_preview", "age_text", "strip_ansi", "short",
     "row_state", "versions_text", "versioned", "system_row", "root_readonly"],
    globals_={"re": __import__("re"), "json": __import__("json")},
)
SHA_A = "fc7135b" + "0" * 33
SHA_B = "15ed838" + "1" * 33
PIHOLE = ("Core version is v6.4.3 (Latest: v6.6)\n"
          "Web version is v6.6 (Latest: v6.6.1)\n"
          "FTL version is v6.7.1 (Latest: v6.9)\n")
POLICY = ("raspotify:\n  Installed: 0.48.3~librespot.v0.8.0-939dc5e\n"
          "  Candidate: 0.48.3~librespot.v0.8.0-939dc5e\n  Version table:\n")

class Versions(unittest.TestCase):
    def test_tool_version(self):
        self.assertEqual(UP.tool_version("spotifast 0.17.1\n", "spotifast"), "0.17.1")
        self.assertEqual(UP.tool_version("rad 1.10.3 (7e1cb406bb93)\n", "rad"), "1.10.3")
        self.assertEqual(UP.tool_version("", "rad"), "")                       # not installed
        self.assertEqual(UP.tool_version("bash: rad: not found", "rad"), "")

    def test_latest_release_from_redirect(self):
        url = "https://github.com/crmne/spotifast/releases/tag/v0.17.1"
        self.assertEqual(UP.version_from_release_url(url), "0.17.1")
        self.assertEqual(UP.version_from_release_url(""), "")                  # offline
        # no release yet: /releases/latest lands on /releases
        self.assertEqual(UP.version_from_release_url("https://github.com/x/y/releases"), "")
        self.assertEqual(UP.version_from_release_url("https://evil/releases/tag/v1;rm -rf"), "")

    def test_latest_radicle_from_json(self):
        self.assertEqual(UP.version_from_json('{"name":"rad","version":"1.10.3","commit":"7e1c"}'), "1.10.3")
        self.assertEqual(UP.version_from_json(""), "")                         # offline
        self.assertEqual(UP.version_from_json("<html>503</html>"), "")
        self.assertEqual(UP.version_from_json('{"version": "1.0; rm"}'), "")
        self.assertEqual(UP.version_from_json("[1, 2]"), "")

    def test_commit_ids(self):
        self.assertEqual(UP.sha_from_git(SHA_A + "\n"), SHA_A)                  # rev-parse
        self.assertEqual(UP.sha_from_git(SHA_A + "\trefs/heads/main\n"), SHA_A)  # ls-remote
        self.assertEqual(UP.sha_from_git("fatal: not a git repository"), "")
        self.assertEqual(UP.sha_from_git(""), "")

    def test_pihole(self):
        self.assertEqual(UP.pihole_versions(PIHOLE), ("6.4.3 / 6.6 / 6.7.1", "6.6 / 6.6.1 / 6.9"))
        self.assertEqual(UP.pihole_versions(""), ("", ""))                     # not installed
        # Pi-hole could not reach GitHub: it prints N/A for the latest
        offline = PIHOLE.replace("Latest: v6.6)", "Latest: N/A)")
        self.assertEqual(UP.pihole_versions(offline), ("6.4.3 / 6.6 / 6.7.1", ""))

    def test_apt_policy(self):
        v = "0.48.3~librespot.v0.8.0-939dc5e"
        self.assertEqual(UP.apt_policy(POLICY), (v, v))
        self.assertEqual(UP.apt_policy("raspotify:\n  Installed: (none)\n  Candidate: 1.2\n"), ("", "1.2"))
        self.assertEqual(UP.apt_policy(""), ("", ""))

    def test_short(self):
        self.assertEqual(UP.short(SHA_A), "fc7135b")
        self.assertEqual(UP.short("0.17.1"), "0.17.1")
        self.assertEqual(UP.short("0.48.3~librespot.v0.8.0-939dc5e"), "0.48.3")


class Rows(unittest.TestCase):
    def test_a_module_is_only_selectable_when_there_is_something_newer(self):
        self.assertEqual(UP.row_state("0.14.2", "0.17.1"), ("Update available", True))
        self.assertEqual(UP.row_state("0.17.1", "0.17.1"), ("Up to date", False))
        # offline: never offer an update we can't name
        self.assertFalse(UP.row_state("0.14.2", "")[1])
        self.assertFalse(UP.row_state("", "")[1])

    def test_only_spotifast_installs_from_nothing(self):
        self.assertTrue(UP.row_state("", "0.17.1")[1])
        # Radicle, Pi-hole, raspotify: not there means not wanted on this Pi
        self.assertEqual(UP.row_state("", "1.10.3", installable=False), ("Not installed", False))
        self.assertEqual(UP.row_state("", "", installable=False), ("Not installed", False))

    def test_versions_text(self):
        self.assertEqual(UP.versions_text("0.14.2", "0.17.1"), "0.14.2  →  0.17.1")
        self.assertEqual(UP.versions_text(SHA_B, SHA_A), "15ed838  →  fc7135b")
        self.assertEqual(UP.versions_text("0.17.1", "0.17.1"), "0.17.1")
        self.assertEqual(UP.versions_text("0.17.1", ""), "0.17.1")
        self.assertEqual(UP.versions_text("", ""), "—")
        # two builds of one version: the short form would read "0.48.3 -> 0.48.3"
        self.assertEqual(UP.versions_text("0.48.3~librespot.v0.8.0-939dc5e", "0.48.3~librespot.v0.9.0-abc1234"),
                         "0.48.3~librespot.v0.8.0-939dc5e  →  0.48.3~librespot.v0.9.0-abc1234")
        self.assertEqual(UP.versioned(*UP.pihole_versions(PIHOLE), False),
                         ("6.4.3 / 6.6 / 6.7.1  →  6.6 / 6.6.1 / 6.9", "Update available", True))


class SystemPackages(unittest.TestCase):
    def test_guarded_and_held_packages_are_never_offered(self):
        # nothing but kernel / firmware / desktop pending: nothing to select
        self.assertEqual(UP.parse_preview("ready=0 guarded=14 held=43\n"), (0, 57))
        self.assertEqual(UP.system_row("ready=0 guarded=14 held=43", 18 * 86400),
                         ("—", "Up to date (lists from 18 days ago, 57 left alone)", False))

    def test_ordinary_upgrades_are_counted(self):
        self.assertEqual(UP.system_row("ready=86 guarded=14 held=43", 3600),
                         ("86 packages", "Update available (lists from today, 57 left alone)", True))
        self.assertEqual(UP.system_row("ready=1 guarded=0 held=0", None),
                         ("1 package", "Update available (lists from an unknown day)", True))

    def test_a_preview_that_cannot_be_read_offers_nothing(self):
        self.assertIsNone(UP.parse_preview(""))                     # the helper is missing
        self.assertEqual(UP.system_row("", 0), ("—", "Can't check", False))
        self.assertEqual(UP.system_row("E: could not read lists", 0)[2], False)

    def test_age(self):
        self.assertEqual(UP.age_text(0), "today")
        self.assertEqual(UP.age_text(86400 * 1.5), "yesterday")
        self.assertEqual(UP.age_text(86400 * 18.2), "18 days ago")
        self.assertEqual(UP.age_text(None), "an unknown day")


class Output(unittest.TestCase):
    def test_terminal_colours_are_removed(self):
        self.assertEqual(UP.strip_ansi("\x1b[32m✓\x1b[0m Radicle \x1b[2m1.10.3\x1b[0m was installed"),
                         "✓ Radicle 1.10.3 was installed")
        self.assertEqual(UP.strip_ansi("plain [done] text"), "plain [done] text")


class SdCard(unittest.TestCase):
    def test_read_only_root_blocks_updates(self):
        rw = "/dev/mmcblk0p2 / ext4 rw,noatime 0 0\n/dev/mapper/pinet-media /mnt/pinet-media ext4 rw 0 0\n"
        ro = "/dev/mmcblk0p2 / ext4 ro,noatime 0 0\n"
        self.assertFalse(UP.root_readonly(rw))
        self.assertTrue(UP.root_readonly(ro))
        # a read-only mount elsewhere, or "ro" inside another option, is not /
        self.assertFalse(UP.root_readonly("/dev/x / ext4 rw,errors=remount-ro 0 0\n/dev/y /boot vfat ro 0 0\n"))
        self.assertFalse(UP.root_readonly(""))


if __name__ == "__main__":
    unittest.main()
