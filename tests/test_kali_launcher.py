"""kali-launcher: the tool registry and argv building (the pure core; the GTK
UI in run_gui is not imported here -- importing the module must not need gi)."""
import importlib.machinery
import importlib.util
import unittest

from _support import repo_path

_loader = importlib.machinery.SourceFileLoader(
    "kali_launcher", str(repo_path("scripts", "bin", "kali-launcher")))
_spec = importlib.util.spec_from_loader("kali_launcher", _loader)
kl = importlib.util.module_from_spec(_spec)
_loader.exec_module(kl)


def tool(key):
    return next(t for t in kl.build_tools(cidr="10.0.0.0/24") if t["key"] == key)


class Registry(unittest.TestCase):
    def test_importing_does_not_pull_in_gtk(self):
        # The module is loaded above with no display / no gi; if run_gui's
        # imports leaked to module scope this file would already have failed.
        import sys
        self.assertNotIn("gi", sys.modules)

    def test_every_tool_is_in_a_known_group(self):
        for t in kl.build_tools():
            self.assertIn(t["group"], kl.GROUP_ORDER, t["key"])

    def test_keys_are_unique(self):
        keys = [t["key"] for t in kl.build_tools()]
        self.assertEqual(len(keys), len(set(keys)))

    def test_defaults_flow_into_the_scan_target(self):
        # build_tools takes the detected CIDR so scan defaults are local.
        self.assertEqual(tool("nmap")["fields"][1][3], "10.0.0.0/24")


class Argv(unittest.TestCase):
    def test_plain_tool_has_no_pkexec(self):
        argv = kl.build_argv(tool("nmap"), {"flags": "-sn", "target": "10.0.0.0/24"},
                             binpath="/usr/bin/nmap")
        self.assertEqual(argv, ["/usr/bin/nmap", "-sn", "10.0.0.0/24"])

    def test_flags_split_into_separate_args(self):
        argv = kl.build_argv(tool("nmap"), {"flags": "-sV -p-", "target": "h"},
                             binpath="nmap")
        self.assertEqual(argv, ["nmap", "-sV", "-p-", "h"])

    def test_root_tool_is_sudo_wrapped(self):
        argv = kl.build_argv(tool("tcpdump"),
                             {"iface": "wlan1", "count": "20", "filter": ""},
                             binpath="/usr/bin/tcpdump")
        self.assertEqual(argv[:2], ["sudo", "/usr/bin/tcpdump"])
        self.assertIn("-c", argv)
        self.assertEqual(argv[argv.index("-c") + 1], "20")

    def test_empty_optional_field_is_omitted(self):
        # netdiscover -r is only added when a range is given.
        with_range = kl.build_argv(tool("netdiscover"),
                                   {"iface": "wlan1", "range": "10.0.0.0/24"}, binpath="nd")
        without = kl.build_argv(tool("netdiscover"),
                                {"iface": "wlan1", "range": "  "}, binpath="nd")
        self.assertIn("-r", with_range)
        self.assertNotIn("-r", without)

    def test_tcpdump_bpf_filter_is_split(self):
        argv = kl.build_argv(tool("tcpdump"),
                             {"iface": "wlan1", "count": "5", "filter": "port 53"},
                             binpath="tcpdump")
        self.assertEqual(argv[-2:], ["port", "53"])

    def test_all_argv_builders_are_callable_with_blank_fields(self):
        # No tool's argv lambda should raise on empty strings (the preview
        # builds a command live as the user types).
        for t in kl.build_tools():
            vals = {name: "" for name, *_ in t["fields"]}
            kl.build_argv(t, vals, binpath=t["bin"])  # must not raise


class MonitorState(unittest.TestCase):
    def test_flag_file_short_circuits(self):
        import os
        real = os.path.exists
        os.path.exists = lambda p: True if p == kl.PENTEST_FLAG else real(p)
        try:
            self.assertTrue(kl.monitor_active())
        finally:
            os.path.exists = real


if __name__ == "__main__":
    unittest.main()
