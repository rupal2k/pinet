#!/usr/bin/env bash
# Installs everything needed to run the e-ink dashboard on a Raspberry Pi.
# Run this ON THE PI (not on a dev machine), from inside pi-eink-dashboard/:
#   chmod +x scripts/install.sh && ./scripts/install.sh
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WAVESHARE_DIR="$HOME/e-Paper"

echo "==> Enabling SPI interface"
sudo raspi-config nonint do_spi 0

echo "==> Installing system packages"
sudo apt update
sudo apt install -y \
  python3-pip python3-pil python3-numpy python3-venv \
  git fonts-roboto wireless-tools libopenjp2-7

echo "==> Cloning/updating Waveshare e-Paper driver library"
if [ -d "$WAVESHARE_DIR" ]; then
  git -C "$WAVESHARE_DIR" pull
else
  git clone --depth 1 https://github.com/waveshareteam/e-Paper.git "$WAVESHARE_DIR"
fi

echo "==> Installing waveshare_epd Python package"
PIP_BREAK="--break-system-packages"
python3 -m pip install $PIP_BREAK "$WAVESHARE_DIR/RaspberryPi_JetsonNano/python" || \
  python3 -m pip install "$WAVESHARE_DIR/RaspberryPi_JetsonNano/python"

echo "==> Installing Python dependencies for the dashboard"
python3 -m pip install $PIP_BREAK pillow psutil requests || \
  python3 -m pip install pillow psutil requests

echo "==> Installing systemd service"
sudo sed \
  -e "s#/home/pi/pi-eink-dashboard#${PROJECT_DIR}#g" \
  -e "s#User=pi#User=${USER}#g" \
  "$PROJECT_DIR/systemd/pi-eink-dashboard.service" \
  | sudo tee /etc/systemd/system/pi-eink-dashboard.service > /dev/null

echo "==> Installing shutdown-splash service (shows the DOOM logo, dark
mode, on the panel during shutdown/reboot -- ordered to run only after
pi-eink-dashboard.service has released the panel)"
sudo sed \
  -e "s#/home/pi/pi-eink-dashboard#${PROJECT_DIR}#g" \
  -e "s#User=pi#User=${USER}#g" \
  "$PROJECT_DIR/systemd/pi-eink-shutdown-splash.service" \
  | sudo tee /etc/systemd/system/pi-eink-shutdown-splash.service > /dev/null

echo "==> Installing journald persistent-storage drop-in (overrides Raspberry
Pi OS's 40-rpi-volatile-storage.conf, which forces Storage=volatile -- without
this, journals live in /run and are wiped on every reboot; the SystemMaxUse cap
bounds SD-card wear)"
sudo install -d /etc/systemd/journald.conf.d
sudo install -m 0644 \
  "$PROJECT_DIR/systemd/journald.conf.d/99-persistent-storage.conf" \
  /etc/systemd/journald.conf.d/99-persistent-storage.conf
sudo systemctl restart systemd-journald
sudo journalctl --flush || true

sudo systemctl daemon-reload
sudo systemctl enable --now pi-eink-dashboard.service
sudo systemctl enable --now pi-eink-shutdown-splash.service

echo "==> Done. Check status with:"
echo "    sudo systemctl status pi-eink-dashboard"
echo "    journalctl -u pi-eink-dashboard -f"
