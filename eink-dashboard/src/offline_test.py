"""Render the no-network fallback states without disconnecting real hardware."""
import dashboard


class FakeEPD:
    width = 122
    height = 250


def main():
    epd = FakeEPD()

    # Weather box when there's genuinely no network connectivity
    net_offline = {"ip": None, "is_wifi": False}
    img = dashboard.render(epd, 12, 40, 0.3, 45.0, None, net_offline, "Guwahati", False)
    img = img.resize((750, 366))
    img.save("preview_no_network.png")
    print("saved preview_no_network.png")

    # QR screen when there's no Wi-Fi connection at all
    qr_img = dashboard.render_qr_screen(epd, None, None, net_offline, False)
    qr_img = qr_img.resize((750, 366))
    qr_img.save("preview_qr_no_wifi.png")
    print("saved preview_qr_no_wifi.png")

    # QR screen fallback when connected via Ethernet instead of Wi-Fi
    net_wired = {"ip": "192.168.29.166", "is_wifi": False}
    qr_img = dashboard.render_qr_screen(epd, None, None, net_wired, False)
    qr_img = qr_img.resize((750, 366))
    qr_img.save("preview_qr_wired.png")
    print("saved preview_qr_wired.png")


if __name__ == "__main__":
    main()
