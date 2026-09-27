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
    def test_one_cell_follows_the_lithium_curve(self):
        self.assertEqual(batt.percent(2.9), 0)
        self.assertEqual(batt.percent(3.0), 0)
        self.assertEqual(batt.percent(3.74), 50)
        self.assertEqual(batt.percent(3.77), 55)     # halfway between two points
        self.assertEqual(batt.percent(4.2), 100)
        self.assertEqual(batt.percent(4.35), 100)

    def test_the_curve_only_goes_up(self):
        readings = [batt.percent(3.0 + i / 100) for i in range(121)]
        self.assertEqual(readings, sorted(readings))

    def test_two_cells_in_series(self):
        self.assertEqual(batt.percent(7.48), 50)
        self.assertEqual(batt.percent(8.4), 100)

    def test_same_charge_reads_the_same_on_and_off_the_charger(self):
        # Real readings seconds apart as the charger was pulled (13:38) and
        # plugged back in (13:41): uncompensated they read 64% vs 53%.
        for on, off in (((3.764, 2.19), (3.640, -0.51)), ((3.752, 2.133), (3.640, -0.519))):
            p_on = batt.percent(batt.rest_volts(*on))
            p_off = batt.percent(batt.rest_volts(*off))
            self.assertLessEqual(abs(p_on - p_off), 1, (p_on, p_off))

    def test_remaining_mah_is_the_share_of_two_4200_cells(self):
        self.assertEqual(batt.CAPACITY_MAH, 8400)
        self.assertEqual(batt.remaining_mah(58), 4870)
        self.assertEqual(batt.remaining_mah(100), 8400)
        self.assertEqual(batt.remaining_mah(0), 0)

    def test_every_icon_it_can_ask_for_ships(self):
        for pct in range(101):
            for state in ("charging", "battery", "full"):
                name = batt.icon_name(pct, state)
                self.assertTrue(repo_path("desktop", "icons", name + ".svg").exists(), name)

    def test_icon_levels(self):
        self.assertEqual(batt.icon_name(4, "battery"), "pinet-battery-0")
        self.assertEqual(batt.icon_name(44, "charging"), "pinet-battery-40-charging")
        self.assertEqual(batt.icon_name(97, "battery"), "pinet-battery-100")
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
