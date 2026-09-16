#!/usr/bin/env python3
"""Show the DOOM logo (forced dark mode) on the e-ink panel during system
shutdown/reboot, then leave it displayed -- e-ink holds its last image with
no power, so this is what's on the panel while the Pi is off. Invoked from
pi-eink-shutdown-splash.service's ExecStop, which is ordered (via that
unit's own Before=pi-eink-dashboard.service) to run only after the live
dashboard service has already released the panel -- two processes must
never touch the same SPI/GPIO panel at once.

Deliberately does NOT call epd.Clear() afterward, unlike the live
dashboard's own shutdown path -- the whole point here is for the DOOM logo
to remain visible while powered off, not to blank the panel.
"""
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import dashboard  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("eink-shutdown-splash")


def main():
    from waveshare_epd import epd2in13_V4

    cfg = dashboard.load_config()
    flip_180 = cfg.getboolean("flip_180", fallback=False)

    epd = epd2in13_V4.EPD()
    voltage, under_voltage, throttled = dashboard.get_power_status()
    disk_free_gb, disk_used_gb, disk_total_gb = dashboard.get_disk_usage()

    image = dashboard.render_image_screen(
        epd, dashboard.DOOM_LOGO_PATH, dark_mode=True,
        voltage=voltage, under_voltage=under_voltage, throttled=throttled,
        disk_free_gb=disk_free_gb, disk_used_gb=disk_used_gb, disk_total_gb=disk_total_gb,
    )
    if flip_180:
        image = image.rotate(180)

    epd.init()
    epd.display(epd.getbuffer(image))
    epd.sleep()
    logger.info("DOOM logo (dark mode) shown for shutdown")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # Never let a display problem block/delay the actual shutdown.
        logger.exception("Failed to show shutdown splash")
