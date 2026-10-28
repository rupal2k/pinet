"""pinet-panel-tab: the panel-config rewrite that shows/hides the taskbar."""
import unittest

from _support import load_defs

TAB = load_defs("scripts/bin/pinet-panel-tab", ["with_autohide"])

CONF = "[panel]\nautohide=true\nautohide_duration=300\nposition=bottom\n"


class WithAutohide(unittest.TestCase):
    def test_flips_existing_value_and_keeps_the_rest(self):
        out = TAB.with_autohide(CONF, False)
        self.assertEqual(out, CONF.replace("autohide=true", "autohide=false"))
        self.assertIn("autohide_duration=300", out)   # not mistaken for autohide=

    def test_round_trip_is_identity(self):
        self.assertEqual(TAB.with_autohide(TAB.with_autohide(CONF, False), True), CONF)

    def test_adds_under_panel_when_missing(self):
        out = TAB.with_autohide("[panel]\nposition=bottom\n", True)
        self.assertEqual(out, "[panel]\nautohide=true\nposition=bottom\n")

    def test_adds_panel_section_when_file_is_empty(self):
        self.assertEqual(TAB.with_autohide("", False), "[panel]\nautohide=false\n")


if __name__ == "__main__":
    unittest.main()
