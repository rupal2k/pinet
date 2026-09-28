"""eth-share pure logic: lease counting, status parsing and the start guard.

The command wrappers (nmcli calls) aren't unit-tested here -- they're covered
by the on-Pi smoke run -- but the safety gate that decides whether sharing may
start, and the parsing the GUI depends on, are pure and tested here.
"""
import unittest

from _support import load_defs

ETH = load_defs(
    "scripts/sbin/eth-share",
    ["parse_kv", "count_leases", "start_block_reason", "MIN_BATTERY_PCT"],
    globals_={"os": __import__("os")},
)
GUI = load_defs(
    "scripts/bin/eth-share-gui",
    ["parse_status", "status_lines"],
)


class ParseKV(unittest.TestCase):
    def test_reads_key_values_ignores_junk(self):
        kv = ETH.parse_kv("state=battery\npercent=42\n\ngarbage line\n=noeq\n")
        self.assertEqual(kv, {"state": "battery", "percent": "42"})

    def test_reads_pinet_battery_single_line(self):
        # pinet-battery --once emits one space-separated line, not one per key.
        kv = ETH.parse_kv(
            "addr=0x43 volts=4.084 amps=-0.486 percent=85 state=battery icon=pinet-battery-80\n")
        self.assertEqual(kv["percent"], "85")
        self.assertEqual(kv["state"], "battery")


class CountLeases(unittest.TestCase):
    def test_counts_only_real_lease_rows(self):
        text = (
            "1690000000 aa:bb:cc:dd:ee:01 10.42.0.23 phone 01:aa:bb:cc:dd:ee:01\n"
            "1690000100 aa:bb:cc:dd:ee:02 10.42.0.24 laptop *\n"
            "\n"
            "duid 00:01:00:01:2a:2b\n"          # ipv6 header line, not a lease
        )
        self.assertEqual(ETH.count_leases(text), 2)

    def test_empty_file_is_zero(self):
        self.assertEqual(ETH.count_leases(""), 0)


class StartGuard(unittest.TestCase):
    def ok_battery(self):
        return {"state": "battery", "percent": 90}

    def test_allows_when_all_clear(self):
        self.assertIsNone(ETH.start_block_reason(
            pentest=False, uplink_ok=True, ups_low=False, battery=self.ok_battery()))

    def test_blocks_in_pentest_mode(self):
        r = ETH.start_block_reason(True, True, False, self.ok_battery())
        self.assertIn("Pentest Mode", r)

    def test_blocks_without_uplink(self):
        r = ETH.start_block_reason(False, False, False, self.ok_battery())
        self.assertIn("uplink", r.lower())

    def test_blocks_when_ups_low(self):
        r = ETH.start_block_reason(False, True, True, self.ok_battery())
        self.assertIn("critically low", r)

    def test_blocks_low_battery_on_battery_power(self):
        r = ETH.start_block_reason(
            False, True, False, {"state": "battery", "percent": ETH.MIN_BATTERY_PCT - 1})
        self.assertIn("%", r)

    def test_allows_low_battery_while_charging(self):
        # On the charger, a low percent is fine -- it's rising, and the draw is
        # covered by mains, not the cells.
        self.assertIsNone(ETH.start_block_reason(
            False, True, False, {"state": "charging", "percent": 5}))

    def test_allows_when_no_battery_reader(self):
        self.assertIsNone(ETH.start_block_reason(False, True, False, None))

    def test_at_threshold_is_allowed(self):
        # Strictly below MIN blocks; exactly MIN is allowed.
        self.assertIsNone(ETH.start_block_reason(
            False, True, False, {"state": "battery", "percent": ETH.MIN_BATTERY_PCT}))


class GuiStatusLines(unittest.TestCase):
    def parse(self, **kw):
        text = "\n".join(f"{k}={v}" for k, v in kw.items())
        return GUI.parse_status(text)

    def test_on_with_devices(self):
        st = self.parse(state="on", uplink_ok="1", uplink_ssid="JioFiber",
                        uplink_signal="72", eth_carrier="1", clients="3")
        on, uplink, eth, clients = GUI.status_lines(st)
        self.assertTrue(on)
        self.assertIn("JioFiber", uplink)
        self.assertIn("72%", uplink)
        self.assertIn("cable connected", eth)
        self.assertEqual(clients, "3 devices connected")

    def test_singular_device(self):
        st = self.parse(state="on", clients="1", eth_carrier="1", uplink_ok="1", uplink_ssid="X")
        _, _, _, clients = GUI.status_lines(st)
        self.assertEqual(clients, "1 device connected")

    def test_off_no_uplink(self):
        st = self.parse(state="off", uplink_ok="0", eth_carrier="0", clients="")
        on, uplink, eth, clients = GUI.status_lines(st)
        self.assertFalse(on)
        self.assertEqual(uplink, "no Wi-Fi uplink")
        self.assertEqual(eth, "no cable")
        self.assertEqual(clients, "sharing off")


if __name__ == "__main__":
    unittest.main()
