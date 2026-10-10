import importlib.machinery
import importlib.util
import unittest

from _support import repo_path

_path = str(repo_path("scripts/bin/media-centre"))
_loader = importlib.machinery.SourceFileLoader("media_centre", _path)
_spec = importlib.util.spec_from_loader("media_centre", _loader)
mc = importlib.util.module_from_spec(_spec)
_loader.exec_module(mc)

SAMPLE = """#EXTM3U
#EXTINF:-1 tvg-id="A.in" tvg-logo="https://x/a.png" group-title="News;General",Alpha News, Live (720p)
https://a.example/live.m3u8
#EXTINF:-1 tvg-id="B.us" group-title="Music",Beta Hits
#EXTVLCOPT:http-referrer=https://b.example/
#EXTVLCOPT:http-user-agent=Mozilla/5.0
#EXTVLCOPT:sout=#file{dst=/home/rupal/.bashrc}
https://b.example/play.m3u8
#EXTINF:-1 tvg-id="",No Group
http://c.example/s.ts
#EXTINF:-1 group-title="Kids",Dangling entry with no url
"""


class ParseTest(unittest.TestCase):
    def setUp(self):
        self.ch = mc.parse_m3u(SAMPLE)

    def test_entries_and_names(self):
        self.assertEqual([c["name"] for c in self.ch],
                         ["Alpha News, Live (720p)", "Beta Hits", "No Group"])

    def test_groups_split_and_default(self):
        self.assertEqual(self.ch[0]["groups"], ["News", "General"])
        self.assertEqual(self.ch[2]["groups"], ["Undefined"])

    def test_vlc_options_become_input_options(self):
        argv = mc.vlc_argv(self.ch[1])
        self.assertEqual(argv[-3:], ["https://b.example/play.m3u8",
                                     ":http-referrer=https://b.example/",
                                     ":http-user-agent=Mozilla/5.0"])

    def test_categories_and_filter(self):
        self.assertEqual(mc.categories(self.ch), [mc.ALL, "General", "Music", "News", "Undefined"])
        self.assertTrue(mc.matches(self.ch[0], "News", "alpha"))
        self.assertFalse(mc.matches(self.ch[0], "Music", ""))
        self.assertTrue(mc.matches(self.ch[1], mc.ALL, "HITS"))
        self.assertFalse(mc.matches(self.ch[1], None, "news"))


WPCTL = """Audio
 ├─ Sinks:
 │  *   96. Boom                                [vol: 0.47]
 │
 └─ Streams:
       103. VLC media player (LibVLC 3.0.23)
            104. output_FL       > Boom:playback_FL	[active]

Video
 └─ Streams:
        77. VLC media player (LibVLC 3.0.23)
"""


class SpeakerTest(unittest.TestCase):
    def test_paired_macs(self):
        out = "Device 54:15:89:66:FF:41 Boom\nDevice AA:79:EE:D1:A3:28 Stone 352 Pro\n"
        self.assertEqual(mc.paired_macs(out), ["54:15:89:66:FF:41", "AA:79:EE:D1:A3:28"])

    def test_last_used_speaker_is_tried_first(self):
        self.assertEqual(mc.speaker_order(["A", "B", "C"], "C"), ["C", "A", "B"])
        self.assertEqual(mc.speaker_order(["A", "B"], "gone"), ["A", "B"])


SINKS = """Audio
 ├─ Sinks:
 │      70. Built-in Audio Stereo               [vol: 0.88]
 │  *   99. Muffs A3                            [vol: 1.50]
 │
 ├─ Sources:
 │  *   96. Muffs A3                            [vol: 1.00]
"""


class FollowSpeakerTest(unittest.TestCase):
    def test_speaker_sinks_skip_the_pi_and_sources(self):
        self.assertEqual(mc.speaker_sinks(SINKS), {"99": "Muffs A3"})

    def test_a_newly_connected_speaker_is_picked(self):
        self.assertEqual(mc.new_speaker({"99": "Muffs A3"},
                                        {"99": "Muffs A3", "120": "Boom"}), "Boom")
        self.assertIsNone(mc.new_speaker({"99": "Muffs A3"}, {"99": "Muffs A3"}))
        self.assertIsNone(mc.new_speaker({"99": "Muffs A3"}, {}))   # it left


class PickTest(unittest.TestCase):
    def test_only_576p_non_hd_in_both_lists(self):
        mk = lambda n, u: {"name": n, "url": u, "groups": ["News"], "opts": []}
        country = [mk("A (576p)", "a"), mk("B (720p)", "b"), mk("C HD (576p)", "c"),
                   mk("D (576p)", "d"), mk("E (576p) [Geo-blocked]", "e")]
        picked = mc.pick_channels(country, {"English": {"a", "b", "c", "e"}, "Hindi": {"a", "d"}})
        self.assertEqual([(c["name"], c["langs"]) for c in picked],
                         [("A (576p)", ["English", "Hindi"]), ("D (576p)", ["Hindi"])])

    def test_language_filter(self):
        ch = {"name": "Zee Bangla", "groups": ["General"], "langs": ["Bengali"]}
        self.assertTrue(mc.matches(ch, mc.ALL, "", "Bengali"))
        self.assertTrue(mc.matches(ch, mc.ALL, "", mc.ALL_LANGS))
        self.assertFalse(mc.matches(ch, mc.ALL, "", "Hindi"))


class ControlTest(unittest.TestCase):
    def test_vlc_has_an_rc_socket(self):
        argv = mc.vlc_argv({"url": "u", "opts": []}, sock="/run/x.sock")
        self.assertIn("--rc-unix", argv)
        self.assertEqual(argv[argv.index("--rc-unix") + 1], "/run/x.sock")
        self.assertEqual(argv[-1], "u")
        self.assertIn(f"--network-caching={mc.NETWORK_CACHING_MS}", argv)

    def test_only_audio_streams_are_unmuted(self):
        self.assertEqual(mc.vlc_stream_ids(WPCTL), ["103"])


if __name__ == "__main__":
    unittest.main()
