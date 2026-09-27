"""pinet-battery: the voltage/percent/icon maths and the INA219 register decode."""
import importlib.machinery
import importlib.util
import unittest

from _support import repo_path

_loader = importlib.machinery.SourceFileLoader("pinet_battery", str(repo_path("scripts", "bin", "pinet-battery")))
_spec = importlib.util.spec_from_loader("pinet_battery", _loader)
batt = importlib.util.module_from_spec(_spec)
_loader.exec_module(batt)


class FakeBus:
    """read_word_data returns little-endian words, as smbus does."""
    def __init__(self, regs):
        self.regs = regs

    def read_word_data(self, addr, reg):
        v = self.regs[reg]
        return ((v & 0xFF) << 8) | (v >> 8)


class Battery(unittest.TestCase):
    def test_one_cell_range(self):
        self.assertEqual(batt.percent(3.0), 0)
        self.assertEqual(batt.percent(3.6), 50)
        self.assertEqual(batt.percent(4.2), 100)
        self.assertEqual(batt.percent(4.35), 100)
        self.assertEqual(batt.percent(2.8), 0)

    def test_two_cells_in_series(self):
        self.assertEqual(batt.percent(7.2), 50)
        self.assertEqual(batt.percent(8.4), 100)

    def test_every_icon_it_can_ask_for_ships(self):
        for pct in range(101):
            for state in ("charging", "battery", "full"):
                name = batt.icon_name(pct, state)
                self.assertTrue(repo_path("desktop", "icons", name + ".svg").exists(), name)

    def test_icon_levels(self):
        self.assertEqual(batt.icon_name(10, "battery"), "pinet-battery-0")
        self.assertEqual(batt.icon_name(40, "charging"), "pinet-battery-50-charging")
        self.assertEqual(batt.icon_name(95, "battery"), "pinet-battery-100")
        self.assertEqual(batt.icon_name(100, "full"), "pinet-battery-100-charging")

    def test_power_state(self):
        self.assertEqual(batt.power_state(2.2), "charging")
        self.assertEqual(batt.power_state(-0.9), "battery")
        self.assertEqual(batt.power_state(0.005), "full")

    def test_register_decode(self):
        # 4.000 V -> 1000 << 3; 150 mA through 0.01 ohm = 1.5 mV = 150 LSB.
        # HAT (D) wiring: the shunt reads negative while the cells charge.
        volts, amps = batt.read(FakeBus({0x02: 1000 << 3, 0x01: 0x10000 - 150}), 0x43)
        self.assertAlmostEqual(volts, 4.0)
        self.assertAlmostEqual(amps, 0.150)
        _, amps = batt.read(FakeBus({0x02: 1000 << 3, 0x01: 200}), 0x43)
        self.assertAlmostEqual(amps, -0.200)


if __name__ == "__main__":
    unittest.main()
