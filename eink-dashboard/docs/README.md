# Raspberry Pi e-Ink Status Dashboard

Shows on a Waveshare 2.13" e-Paper HAT (V4):
- Date and time
- CPU usage, RAM usage, CPU temperature
- Weather (via Open-Meteo, no API key needed)
- Network status: local IP address, and Wi-Fi SSID / Wired / Offline

Files:
```
pi-eink-dashboard/
  src/dashboard.py               the dashboard script (runs continuously)
  config/config.ini              latitude/longitude + refresh interval
  scripts/install.sh             one-shot setup script (run on the Pi)
  systemd/pi-eink-dashboard.service   background service definition
```

## 0. Confirm your exact HAT model

This script targets the **2.13inch e-Paper HAT (V4)**. Waveshare's Python
driver is per-model, so before wiring anything, check the label on the
ribbon cable or the product page/box for the exact model string
(e.g. `2.13inch e-Paper HAT`, `2.13inch e-Paper HAT (D)`, `2.7inch`,
`2.9inch V2`). If yours isn't the V4 2.13", after cloning the driver repo
(step 3 below) look in
`~/e-Paper/RaspberryPi_JetsonNano/python/lib/waveshare_epd/` for the
matching file (e.g. `epd2in7.py`), then in `src/dashboard.py` change:

```python
from waveshare_epd import epd2in13_V4
...
epd = epd2in13_V4.EPD()
```

to the matching module/class name. Nothing else in the script needs to change.

## 1. Get your Pi on the network (and find it to SSH in)

If the Pi isn't already set up on your Wi-Fi/Ethernet:

**Easiest — during imaging:** use Raspberry Pi Imager (raspberrypi.com/software).
Click the gear icon before writing the SD card to pre-configure hostname,
enable SSH, and set your Wi-Fi SSID/password. Boot the Pi and it will join
your network automatically.

**Already imaged, headless, via Ethernet:** plug the Pi into your router with
an Ethernet cable and power it on — no Wi-Fi config needed.

**Already imaged, need Wi-Fi from the command line** (after logging in via
keyboard/monitor or Ethernet+SSH):
```bash
sudo raspi-config
# System Options -> Wireless LAN -> enter SSID and password
```
or non-interactively:
```bash
sudo nmcli device wifi connect "YOUR_SSID" password "YOUR_WIFI_PASSWORD"
```

**Find the Pi's IP address to SSH into it**, run one of these from the
Pi itself (keyboard/monitor) or from another machine on the same network:
```bash
hostname -I                     # run on the Pi
ping raspberrypi.local          # run from another machine (mDNS)
```
Then from your dev machine:
```bash
ssh pi@<the-ip-address>
# or, if mDNS resolves:
ssh pi@raspberrypi.local
```
Make sure SSH is enabled: `sudo raspi-config` -> Interface Options -> SSH,
or `sudo systemctl enable --now ssh`.

Once the dashboard is running, this same IP/SSID is exactly what shows up
in the "IP:" and "WiFi:"/"Wired" lines on the e-ink screen itself, so you
can glance at the panel later to find the Pi's address without SSHing in.

## 2. Copy this project onto the Pi

From your dev machine:
```bash
scp -r pi-eink-dashboard pi@<pi-ip-address>:~/
```
(or `git clone` it if you push it to a repo you control).

## 3. Wire the HAT and run the installer

Power off the Pi, seat the HAT firmly on the 40-pin GPIO header, power back on.

SSH into the Pi, then:
```bash
cd ~/pi-eink-dashboard
chmod +x scripts/install.sh
./scripts/install.sh
```
This enables SPI, installs system packages, clones Waveshare's driver repo,
installs the `waveshare_epd` Python package plus `pillow`/`psutil`/`requests`,
and installs+starts the systemd service.

The installer assumes your project lives at `~/pi-eink-dashboard` and your
Pi login user owns it — it patches the systemd unit's paths/user automatically.

## 4. Configure location (optional but recommended)

Edit `config/config.ini`:
```ini
[dashboard]
latitude = 51.5074
longitude = -0.1278
refresh_minutes = 10
```
Leave latitude/longitude blank to auto-detect via your public IP
(`ip-api.com`, no key required, but less precise and one extra outbound
call per refresh). Restart the service after editing:
```bash
sudo systemctl restart pi-eink-dashboard
```

## 5. Verify it's working

```bash
sudo systemctl status pi-eink-dashboard   # should show "active (running)"
journalctl -u pi-eink-dashboard -f        # live logs; Ctrl+C to stop watching
```
The panel should update within a few seconds of the service starting, then
redraw every `refresh_minutes`.

## Troubleshooting

- **Blank/no display**: confirm SPI is enabled (`ls /dev/spidev*` should list
  a device) and the HAT is fully seated on the header.
- **`ModuleNotFoundError: waveshare_epd`**: the pip install in step 3 failed —
  re-run `python3 -m pip install --break-system-packages ~/e-Paper/RaspberryPi_JetsonNano/python`.
- **Permission errors on GPIO/SPI**: make sure the systemd service's `User=`
  is a user in the `gpio` and `spi` groups (the default `pi` user is by
  default); `sudo usermod -aG gpio,spi $USER` and re-login/reboot if not.
- **"IP: -- not connected --" on screen**: the Pi has no network route —
  check Wi-Fi/Ethernet per step 1; the dashboard itself doesn't configure
  networking, it only reports current status.
- **Ghosting/faint previous image**: normal for e-ink after many partial
  updates; this script does a full re-init + refresh every cycle, so
  ghosting should be minimal. If it builds up anyway, run once manually:
  `python3 -c "from waveshare_epd import epd2in13_V4 as e; d=e.EPD(); d.init(); d.Clear(0xFF)"`.
