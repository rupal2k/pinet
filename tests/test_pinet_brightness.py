"""pinet-brightness: level logic (the GTK tray in tray() is not imported here --
importing the module must not need gi)."""
import importlib.machinery
import importlib.util
import tempfile
import unittest
from pathlib import Path

from _support import repo_path

_loader = importlib.machinery.SourceFileLoader(
    "pinet_brightness", str(repo_path("scripts/bin/pinet-brightness")))
_spec = importlib.util.spec_from_loader("pinet_brightness", _loader)
pb = importlib.util.module_from_spec(_spec)
_loader.exec_module(pb)


class Levels(unittest.TestCase):
    def test_clamp_never_fully_dark(self):
        self.assertEqual([pb.clamp(v) for v in (0, 5, 26, 128, 255, 900)], [26, 26, 26, 128, 255, 255])
        self.assertEqual(pb.percent(pb.MIN_LEVEL), 10)

    def test_scroll_steps_and_stops_at_the_ends(self):
        self.assertEqual(pb.scrolled(100, 120), 116)
        self.assertEqual(pb.scrolled(100, -1), 84)
        self.assertEqual(pb.scrolled(250, 120), 255)
        self.assertEqual(pb.scrolled(30, -120), 26)
        self.assertEqual(pb.scrolled(100, 0), 100)

    def test_levels_read_live_then_saved(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            conf, bl = d / "dsi-screen", d / "brightness"
            conf.write_text("# c\nBRIGHTNESS=90\n")
            bl.write_text("200\n")
            self.assertEqual(pb.current_level(str(bl), str(conf)), 200)
            bl.write_text("0\n")                      # asleep -> the saved level
            self.assertEqual(pb.current_level(str(bl), str(conf)), 90)
            conf.write_text("BRIGHTNESS=junk\n")
            self.assertEqual(pb.saved_level(str(conf)), 255)
            self.assertEqual(pb.saved_level(str(d / "missing")), 255)

    def test_importing_does_not_pull_in_gtk(self):
        import sys
        self.assertNotIn("gi.repository.Gtk", sys.modules)


if __name__ == "__main__":
    unittest.main()
