"""Render the dashboard to PNGs using REAL live data, no e-ink hardware needed.

The Wi-Fi QR preview intentionally uses a FAKE placeholder password (never the
real one) purely to verify the QR screen's layout -- the real password is only
ever read and embedded by the live systemd service, never by this script when
run for preview/testing purposes with fake_qr=True.
"""
import dashboard


class FakeEPD:
    width = 122
    height = 250


def main():
    epd = FakeEPD()
    cfg = dashboard.load_config()
    lat, lon, location_name = dashboard.get_location(cfg)
    cpu, ram_pct, ram_used_gb, cpu_temp = dashboard.get_system_stats()
    weather = dashboard.get_weather(lat, lon)
    net = dashboard.get_network_status()
    print("location:", lat, lon, location_name)
    print("cpu/ram/temp:", cpu, ram_pct, ram_used_gb, cpu_temp)
    print("weather:", weather)
    print("net:", net)

    for mode_name, dark in (("light", False), ("dark", True)):
        img = dashboard.render(
            epd, cpu, ram_pct, ram_used_gb, cpu_temp, weather, net,
            location_name, dark,
        )
        img = img.resize((750, 366))
        img.save(f"preview_{mode_name}.png")
        print(f"saved preview_{mode_name}.png")

    # QR layout preview with a FAKE placeholder ssid/password -- never the real one.
    # Includes a worst-case 32-char SSID (WPA's max length) to verify no truncation.
    test_cases = [
        ("short", "TestNetwork"),
        ("longest_possible_ssid_32chars32", "longest_possible_ssid_32chars32"),
    ]
    for label, ssid in test_cases:
        for mode_name, dark in (("light", False), ("dark", True)):
            qr_img = dashboard.render_qr_screen(epd, ssid, "fake-placeholder-pw", net, dark)
            qr_img = qr_img.resize((750, 366))
            fname = f"preview_qr_{label}_{mode_name}.png"
            qr_img.save(fname)
            print(f"saved {fname} (fake credentials, layout check only)")

    # Hotspot/QR carousel screen -- mock status incl. PINET media storage.
    # board_password uses a same-length placeholder, never the real value.
    mock_hotspot = {
        "active": True, "ssid": "PINET", "ip": "10.10.10.1", "client_count": 3,
        "password": "fake-placeholder-pw", "board_password": "guest-pass-13",
        "storage_free_gb": 53.4, "storage_total_gb": 57.0,
    }
    for mode_name, dark in (("light", False), ("dark", True)):
        h_img = dashboard.render_hotspot_screen(epd, mock_hotspot, dark)
        h_img = h_img.resize((750, 366))
        fname = f"preview_hotspot_{mode_name}.png"
        h_img.save(fname)
        print(f"saved {fname} (fake board password, layout check only)")

    # Real-world no-wifi-credentials-found preview (uses live net status)
    real_ssid, real_password = dashboard.get_wifi_credentials()
    print("actual current wifi ssid found:", real_ssid, "| password retrieved:", bool(real_password))


if __name__ == "__main__":
    main()
