<div align="center">

# 📟 PINET

### Dual-Screen Raspberry Pi 3B Cyber-Deck

**An all-in-one battery-powered appliance: offline hotspot & captive message board, 2.13" e-ink rear telemetry panel, 7" touchscreen photo frame & kiosks, Wi-Fi auditing station, and wireless media centre.**

<br />

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg?style=flat-square)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Raspberry%20Pi%203B-c51a4a.svg?style=flat-square)](https://www.raspberrypi.com/)
[![OS](https://img.shields.io/badge/OS-Debian%2013%20trixie%20(64--bit)-a80030.svg?style=flat-square)](https://www.debian.org/)
[![Python](https://img.shields.io/badge/Python-3.11+-3776ab.svg?style=flat-square)](https://www.python.org/)
[![Tests](https://img.shields.io/badge/Tests-301%20passing-brightgreen.svg?style=flat-square)](tests/)
[![Displays](https://img.shields.io/badge/Displays-7%22%20DSI%20%2B%202.13%22%20e--Paper-blueviolet.svg?style=flat-square)](#-hardware-specifications)
[![Compositor](https://img.shields.io/badge/Compositor-labwc%20(Wayland)-informational.svg?style=flat-square)](#-subsystems)
[![Power](https://img.shields.io/badge/Battery-8400%20mAh%20(2%C3%9721700)-f59e0b.svg?style=flat-square)](#-power-management-and-battery-guard)

<br />

[Hardware Architecture](#-hardware-architecture) • [Feature Highlights](#-feature-highlights) • [Subsystems](#-subsystems) • [Getting Started](#-getting-started) • [CLI Tools](#-command-line-utilities) • [Screenshots](#-screenshots)

<br />

| [▶️ **Watch Demo on YouTube**](https://youtu.be/Q5zrIVO-YQM) | [📖 **Read Build Guide on Hackster.io**](https://www.hackster.io/rupal2k/pinet-dual-screen-pi-cyber-deck-7a8dd3) |
|:---:|:---:|

<br />

<img src="docs/images/pinet-showcase.gif" alt="PINET Interface Walkthrough" width="100%" style="border-radius: 10px; border: 1px solid #30363d;" />

</div>

<br />

PINET started as an e-ink status display and grew into five coexisting subsystems
sharing a single Raspberry Pi 3B. They run under a tight 5 V power budget: an
on-board power manager sheds background services whenever heavy touchscreen kiosks
run, and no service starts at boot unless it must.

This repository contains the complete source code, system configurations, desktop
definitions, unit tests and documentation for the device. For the detailed
architectural write-up, see [`docs/Device Overview.md`](docs/Device%20Overview.md).

---

## ⚡ Feature Highlights

| | Subsystem | Description |
|:---:|---|---|
| 📟 | **Dual Displays** | Front 7" DSI capacitive touch panel (800×480) for Wayland desktop & kiosks; rear 2.13" e-Paper panel (250×122) for continuous system health and hotspot join QR. |
| 📡 | **Air-Gapped Hotspot** | Self-hosted wireless AP on `wlan0` (`10.10.10.1`) with dnsmasq captive portal redirecting phones to `pinet-board` (message board + 1 GB file drop on USB). |
| ⚡ | **Battery & UPS Protection** | Dual 21700 cells (8400 mAh) on Waveshare UPS HAT (D) with INA219 I²C monitoring, calibrated OCV math, and a proactive load-shedding daemon preventing brownouts. |
| 📻 | **Unified Media Centre** | Touch launcher for Spotify Connect (PipeWire to Bluetooth with 150% boost), live 576p Indian IPTV streams, and low-latency USB UVC HDMI field monitoring. |
| 🎯 | **Wi-Fi Auditing Suite** | Native pentest tools (`nmap`, `aircrack-ng`, `wifite`, `reaver`, `bully`) in `kali-launcher` with an embedded Vte terminal pane and dedicated monitor-mode power profile. |
| 🔌 | **Ethernet Share & Pi-hole** | Bridges `wlan1` internet uplink out through `eth0` (`10.42.0.1/24`) with dnsmasq DHCP leases and toggleable Pi-hole ad blocking. |

---

## 🛠️ Hardware Architecture

### Schematic & Interconnect Topology

![PINET Hardware Architecture](docs/images/block-diagram.png)

### Component Bill of Materials

| Component | Part / Specification | Interface | Role |
|---|---|---|---|
| **Single-Board Computer** | Raspberry Pi 3 Model B Rev 1.2 | — | Broadcom BCM2837, 4× Cortex-A53 @ 1.2 GHz, 1 GB LPDDR2 |
| **Operating System** | Debian 13 "trixie" (64-bit) | SD Card | Kernel 6.12+, systemd, labwc Wayland compositor |
| **Touchscreen** | Official Raspberry Pi 7" Touchscreen | DSI + I²C | 800×480 capacitive touch (`edt_ft5x06`), primary UI |
| **Status Display** | Waveshare 2.13" e-Paper HAT (V4) | SPI (bus 0) | 250×122 1-bit monochrome rear status panel |
| **Power Management** | Waveshare UPS HAT (D) | I²C (`0x43`) | Dual 21700 cells (8400 mAh), INA219 voltage/current sensor |
| **Hotspot Radio** | On-board Broadcom BCM43438 | SDIO (`wlan0`) | Dedicated 2.4 GHz 802.11n AP for `PINET` (`10.10.10.1`) |
| **Uplink / Auditing Radio** | TP-Link Archer T2U Plus (RTL8821AU) | USB (`wlan1`) | 2.4/5 GHz home uplink; monitor mode and packet injection |
| **Mass Storage** | 58 GB USB 3.0 flash drive | USB | Mounted at `/mnt/pinet-media` (uploads, camera, slideshow) |
| **Camera** | Raspberry Pi Camera Module V2 (IMX219) | 15-pin CSI | 8 MP sensor for live viewer and still/video capture |
| **Video Capture** | USB UVC HDMI Capture Dongle (MS2109) | USB | Full-screen HDMI field monitor input |
| **Audio Output** | Bluetooth A2DP Sink (Speaker/Headphones) | Bluetooth | PipeWire / WirePlumber audio endpoint |

---

## 🧩 Subsystems

### E-ink Status Dashboard

<details open>
<summary><b>Click to expand architecture & operational details</b></summary>
<br />

An always-on 2.13" panel on the rear of the deck provides continuous system
telemetry without waking the touchscreen. Driven over SPI by
`pi-eink-dashboard.service`. Because e-paper holds an image with zero current,
the panel draws power only while refreshing.

- **Rotating Carousel**: Cycles through seven information cards:
  1. *Clock and Date*: 12-hour local time and calendar date.
  2. *System Health*: CPU utilization percentage, RAM consumption, and SoC temperature.
  3. *Live Weather*: Current conditions and forecast via web API.
  4. *Network Status*: IP addresses for `eth0`, `wlan0` (hotspot), and `wlan1` (station).
  5. *Wi-Fi Join QR*: Scannable QR code encoding the local home Wi-Fi credentials.
  6. *PINET Hotspot Card*: SSID, guest board password, and connected client count.
  7. *Hardware Voltage*: INA219 bus voltage and disk space indicators.
- **Auditing Alert**: Switches to a pirate "PENTEST" banner when Wi-Fi auditing starts.
- **Clean Shutdown Splash**: Displays a persistent DOOM logo during system halt or reboot.

</details>

### PINET Hotspot and Message Board

<details>
<summary><b>Click to expand architecture & operational details</b></summary>
<br />

A self-contained, internet-free wireless network hosted on the internal Broadcom
radio (`wlan0`, `10.10.10.1`). When client devices connect, a dnsmasq wildcard DNS
responder (`address=/#/10.10.10.1`) triggers the mobile captive portal prompt,
opening the `pinet-board` web application.

- **Anonymous Message Board**: SQLite-backed bulletin board for local discussions.
- **File Sharing (up to 1 GB)**: Upload and download files directly from mobile
  browsers. Large files stream directly to `/mnt/pinet-media/` with dedicated `TMPDIR`
  handling to protect the Pi's 463 MB RAM-backed `/tmp` from exhaustion.
- **In-Browser Preview**: Inline viewing for images, PDFs, text, and videos (`/view/<id>`),
  with forced download and `X-Content-Type-Options: nosniff` headers on executable or
  scriptable file types (`.html`, `.svg`, `.js`).
- **Two-Tier Authentication**: Single password prompt differentiates between Guest
  (view, post, upload, download; password shown on e-ink) and Admin (file deletion;
  managed via `set_password.py`).
- **Network Isolation**: Strict nftables rules prevent hotspot clients from accessing
  SSH (port 22) or VNC (port 5900). Started and stopped on demand.

</details>

### Touchscreen Photo Frame and Kiosks

<details>
<summary><b>Click to expand architecture & operational details</b></summary>
<br />

An official Raspberry Pi 7" capacitive touchscreen (800×480) driven by `labwc`
(Wayland) and `wf-panel-pi` under a custom PINET dark theme.

- **Photo Frame Slideshow**: Runs fullscreen via `pqiv` when the device is idle.
  Images from `/mnt/pinet-media/slideshow/` are normalized to 800×480 and displayed
  fit-to-screen over blurred letterboxing rather than cropped.
- **Touch Sleep and Double-Tap Wake**: After 90 seconds of inactivity, `swayidle`
  blanks the DSI output and backlight. While asleep, `dsi-tap-wake.py` grabs the
  touchscreen evdev node exclusively (`EVIOCGRAB`) so stray contact cannot trigger
  desktop icons. A rapid double-tap re-lights the display and re-arms the sleep timer.
- **Passcode Lock Screen**: Taskbar lock icon launches `dsi-lock.py`, presenting an
  on-screen numeric keypad before restoring desktop access.
- **On-Screen Keyboard**: Integrated `wvkbd` launcher in the taskbar. Auto-compresses
  window geometry when active so input fields remain visible.
- **Lightweight Kiosks**: On-demand shortcuts launch the Pi Camera (`dsi-cam-server.py`
  providing 640×480 MJPEG at 10 fps with upright photo/video capture), the Ezykam
  smart-camera viewer, and the PINET Portal. Kiosks run in `cog` (WPE WebKit) or
  PyQt6 to prevent the high memory overhead of full desktop browsers.

</details>

### Media Centre

<details>
<summary><b>Click to expand architecture & operational details</b></summary>
<br />

A unified touch interface (`media-centre`) providing three dedicated entertainment
modes behind one desktop launcher:

- **Spotify Connect**: Runs `raspotify` as a background receiver. Sound routes to
  connected Bluetooth speakers via PipeWire. If no speaker is currently connected,
  it attempts reconnection with paired devices (prioritizing the last-used speaker).
  Forces speaker volume to 150% so the source phone's volume slider controls the
  full audible range.
- **IPTV Player**: Plays live Indian broadcast streams in English, Bengali, and
  Hindi from `iptv-org`. Automatically filters playlists to 576p streams (avoiding
  Pi 3B hardware decoding bottlenecks) and pre-probes stream endpoints when the list
  opens. VLC plays full-screen while a media flag suppresses screen blanking.
  Corner touch controls (Back, Play/Pause, Close) auto-hide after 4 seconds.
- **HDMI Field Monitor**: Connects to a USB UVC HDMI capture card (tested with
  MacroSilicon MS2109) to convert the touchscreen into an external HDMI field monitor
  for laptops or cameras. Streams video through low-latency `ffmpeg` and `ffplay`
  pipelines with automatic recovery if the USB bus resets.

</details>

### Wi-Fi Auditing Toolkit

<details>
<summary><b>Click to expand architecture & operational details</b></summary>
<br />

A specialized launcher (`kali-launcher`) for wireless and network assessments on
authorized hardware:

- **Touch-Friendly Tool Grid**: Quick-access cards for `nmap`, `aircrack-ng`, `wifite`,
  `reaver`, `bully`, `mdk4`, `hcxdumptool`, `hcxtools`, `macchanger`, and `tcpdump`.
- **Embedded Terminal**: An integrated GTK3/Vte terminal pane hosts interactive
  ncurses sessions (e.g. `wifite`, `airodump-ng`) directly within the window. Cards
  automatically collapse when the on-screen keyboard opens.
- **Pentest Power Mode**: `wifi-pentest-start` switches the external USB Wi-Fi
  dongle (`wlan1`) into monitor mode, stops the PINET hotspot, sheds non-essential
  power consumers, and updates the e-ink screen with the pirate skull indicator.
  `wifi-pentest-stop` cleanly restores station mode.

</details>

### Ethernet Share

<details>
<summary><b>Click to expand architecture & operational details</b></summary>
<br />

Routes uplink connectivity from the Wi-Fi interface (`wlan1`) out through the
built-in Ethernet jack (`eth0`):

- **DHCP and Routing**: Assigns static `10.42.0.1/24` to `eth0`, hands out DHCP leases
  from `10.42.0.10` to `10.42.0.254` via dnsmasq, and configures nftables NAT masquerade.
- **Ad-Blocking**: Includes an optional local Pi-hole DNS interception toggle.
- **Touch and CLI Controls**: Managed either via command line (`eth-share`) or an
  on-screen touchscreen window (`eth-share-gui`).

</details>

### Power Management and Battery Guard

<details>
<summary><b>Click to expand architecture & operational details</b></summary>
<br />

Because the Raspberry Pi 3B shares a single 5 V rail across its SoC, dual displays,
CSI camera, and USB peripherals, unmanaged power draws can trigger under-voltage
throttling (`0x50005`) or USB bus resets. PINET implements multi-layered power controls:

- **Battery Telemetry (`pinet-battery`)**: Interrogates the INA219 sensor on the
  Waveshare UPS HAT (D) over I²C (`0x43`). Calculates resting voltage by compensating
  for internal pack resistance ($IR = 0.045\,\Omega$), interpolates battery percentage
  against an empirically measured Open Circuit Voltage curve (3.35 V to 4.20 V), and
  renders a battery status icon in the taskbar.
- **Automatic Shutdown Guard (`pinet-ups-guard`)**: Monitors battery levels every 15
  seconds. When the pack drops to critical levels ($\le 3.3\,\text{V}$ under load or
  $\le 10\%$), the daemon executes an orderly shutdown to protect the SD card from
  sudden power loss.
- **Proactive Load Shedding (`pi-power-manager`)**: Whenever high-demand workloads
  (kiosks or pentest mode) launch, this daemon automatically stops background consumers
  (VNC, Bluetooth, PINET hotspot, photo frame slideshow). When the workload exits,
  services are restored in staggered 2-second intervals, verifying voltage stability
  at each step.
- **I/O Flush Protection (`dsi-install-guard`)**: Blanking the DSI display and tuning
  kernel dirty memory thresholds (`/etc/sysctl.d/90-sd-writeback.conf`) during `apt`
  operations avoids SD controller stalls.

</details>

---

## 📸 Screenshots

All captures taken directly from the 800×480 touchscreen interface.

| | |
|---|---|
| ![Desktop](docs/images/desktop.png)<br>**Desktop.** Single-tap launchers with battery, lock, and virtual keyboard in the taskbar. | ![Media Centre](docs/images/media-centre.png)<br>**Media Centre.** Mode selector. The Spotify indicator turns green while active. |
| ![IPTV channel list](docs/images/media-centre-iptv.png)<br>**IPTV channel list.** Filtered by language and category, pre-probed for liveness. | ![IPTV video controls](docs/images/media-centre-video.png)<br>**IPTV playback.** Full-screen video with corner controls visible. |
| ![HDMI Monitor](docs/images/hdmi-monitor.png)<br>**HDMI monitor.** Displaying a laptop display feed via USB UVC capture dongle. | ![Start Spotify dialog](docs/images/spotify-confirm.png)<br>**Spotify Connect.** Confirmation dialog before starting raspotify. |
| ![Start PINET dialog](docs/images/pinet-confirm.png)<br>**Service confirmation.** Safety prompt prior to toggling system daemons. | ![Portal login](docs/images/portal-login.png)<br>**PINET portal.** Captive message board and file drop sign-in screen. |
| ![Kali Tools](docs/images/kali-tools.png)<br>**Wi-Fi auditing launcher.** Touch-friendly tool cards with embedded Vte terminal. | ![Ethernet Share](docs/images/ethernet-share.png)<br>**Ethernet Share.** Wired interface sharing with optional Pi-hole filtering. |
| ![Lock screen](docs/images/lock-screen.png)<br>**Passcode lock screen.** Numeric PIN pad overlay protecting the touch session. | ![Brightness slider](docs/images/brightness-slider.png)<br>**Brightness slider.** Anchored taskbar slider with a 10% safety floor. |
| ![E-ink status](docs/images/eink-status.png)<br>**E-ink status panel.** Rear-facing system metrics and telemetry display. | ![E-ink hotspot card](docs/images/eink-hotspot.png)<br>**E-ink join card.** Displays current SSID, guest key, and join count. |
| ![Graph viewer](docs/images/graph-viewer.png)<br>**Code graph viewer.** On-device browser for inspecting repository structure. | ![PINET boot splash](docs/images/boot-splash.png)<br>**Boot splash.** Dark gradient boot and shutdown splash screen. |

---

## 🚀 Getting Started

### Prerequisites

- A Raspberry Pi 3B with Debian 13 "trixie" (or Raspberry Pi OS 64-bit).
- Hardware assembled per the [Hackster.io build guide](https://www.hackster.io/rupal2k/pinet-dual-screen-pi-cyber-deck-7a8dd3).
- Passwordless `sudo` configured for the primary user.
- I²C and SPI enabled in `/boot/firmware/config.txt`.

### 1. E-ink Dashboard Installation

The e-ink status dashboard includes an automated setup script that enables the
hardware interfaces, fetches the Waveshare driver, installs Python dependencies,
and sets up systemd services:

```bash
git clone https://github.com/rupal2k/pinet.git
cd pinet/eink-dashboard
chmod +x scripts/install.sh
./scripts/install.sh
```

Verify service status:

```bash
sudo systemctl status pi-eink-dashboard.service
journalctl -u pi-eink-dashboard.service -f
```

### 2. Deploying System Files

Install the remaining system scripts, services, and configurations to their
expected filesystem locations:

```bash
# Core user-facing scripts and background daemons
sudo install -m 755 scripts/bin/* /usr/local/bin/
sudo install -m 755 scripts/sbin/* /usr/local/sbin/

# Systemd services and drop-ins
sudo cp -r systemd/* /etc/systemd/system/
sudo systemctl daemon-reload

# Network and hardware configuration files
sudo cp -r etc/* /etc/

# Captive portal web application
sudo mkdir -p /opt/pinet-board
sudo cp -r pinet-board/* /opt/pinet-board/
sudo chown -R pinet-board:pinet-board /opt/pinet-board

# Desktop shortcuts and icons
mkdir -p ~/.config ~/.local/share/icons ~/Desktop
cp -r config/* ~/.config/
cp -r desktop/icons/* ~/.local/share/icons/
cp desktop/*.desktop ~/Desktop/
chmod +x ~/Desktop/*.desktop
```

### 3. Media Storage Setup

Attach an external USB flash drive formatted as ext4, create the required
directory structure, and configure `/etc/fstab`:

```bash
sudo mkdir -p /mnt/pinet-media/{uploads,camera,slideshow}
sudo chown -R rupal:rupal /mnt/pinet-media/slideshow /mnt/pinet-media/camera
sudo chown -R pinet-board:pinet-board /mnt/pinet-media/uploads
```

### 4. Passwords and Credentials

Set authentication keys and passwords. No default credentials exist in the
repository:

```bash
# Set PINET portal admin and guest passwords
sudo python3 /opt/pinet-board/set_password.py
sudo python3 /opt/pinet-board/set_guest_password.py

# Set DSI touchscreen passcode (numeric PIN)
echo -n "1234" | sudo tee /etc/dsi-lock/passcode > /dev/null
sudo chmod 600 /etc/dsi-lock/passcode
```

### 5. Plymouth Boot Splash

Install the custom boot animation theme:

```bash
sudo install -D -m 644 -t /usr/share/plymouth/themes/pinet plymouth/pinet/*
sudo plymouth-set-default-theme -R pinet
```

---

## 💻 Usage and Operation

### Touchscreen Desktop

| Action | Interaction | Behavior |
|---|---|---|
| **Launch Service** | Single tap on icon | Opens confirmation prompt prior to starting or stopping daemon. |
| **Media Centre** | Tap **Media Centre** icon | Select Spotify, IPTV, or HDMI Monitor. Spotify card indicates live status. |
| **Watch IPTV** | Tap **IPTV** | Opens channel selector. Tapping video corner displays playback controls. |
| **HDMI Capture** | Tap **HDMI Monitor** | Connect HDMI cable, then tap to open low-latency fullscreen preview. |
| **Lock Screen** | Tap lock icon in taskbar | Engages `dsi-lock.py` overlay. Requires PIN to dismiss. |
| **Virtual Keyboard** | Tap keyboard icon in taskbar | Spawns `wvkbd`. Dismiss by tapping the floating edge tab. |
| **Screen Brightness** | Tap or scroll brightness icon | Adjusts backlight between 10% floor and 100%. Auto-saves to config. |
| **Display Sleep / Wake** | Idle 90s / Double-tap screen | Automatically sleeps. Double-tap wakes display and re-arms sleep timer. |

### Command-Line Utilities

PINET provides standalone CLI commands for manual control and automation:

| Command | Arguments | Purpose |
|---|---|---|
| `pinet-battery` | `--once` | Prints live voltage, current (mA), resting percentage, and power state. |
| `pinet-battery` | `--log <file>` | Appends CSV telemetry per minute to calibrate battery discharge curves. |
| `pinet-brightness` | `--once` | Outputs current and saved DSI backlight brightness levels. |
| `pinet-start` | — | Starts `pinet-ap-network`, `hostapd`, `dnsmasq`, and `pinet-board`. |
| `pinet-stop` | — | Stops hotspot services and tears down the AP network. |
| `wifi-pentest-start` | — | Puts `wlan1` into monitor mode, sheds power consumers, alerts e-ink. |
| `wifi-pentest-stop` | — | Restores `wlan1` to managed Wi-Fi station mode and normal power profile. |
| `eth-share` | `[on\|off\|status]` | Enables or disables Ethernet routing and optional Pi-hole filtering. |
| `pi-diagnostic` | `[all\|eink\|network\|dsi]` | Runs automated functional tests against live hardware interfaces. |
| `hdmi-monitor` | `[--device]` | Finds connected UVC capture device or launches full-screen viewer. |

### Service Management and Diagnostic Logs

Monitor system behavior with standard journald commands:

```bash
# Monitor Media Centre and VLC stream playback
journalctl --user -t media-centre -f

# Monitor HDMI video capture pipeline and USB recovery events
journalctl -t hdmi-monitor -f

# Inspect Spotify Connect receiver daemon
journalctl -u raspotify.service -f

# Check hardware under-voltage status (0x0 means healthy, 0x50005 indicates throttling)
vcgencmd get_throttled
```

---

## 🔒 Security and Secrets

- **No Secrets in Source**: Passwords, TLS keys, Flask secret tokens, and lock-screen
  PINs are never committed to git. They reside solely on the physical device in
  mode-restricted files (`/etc/pinet-board/`, `/etc/dsi-lock/passcode`).
- **Open Hotspot with Isolated Access**: The PINET Wi-Fi hotspot is intentionally
  open for easy guest access. However, web application operations require authentication,
  and the host firewall strictly drops inbound SSH (port 22) and VNC (port 5900)
  packets arriving over `wlan0`.
- **Upload Hardening**: User uploads are stripped of path traversals, prepended
  with random tokens, and stored outside web roots. Scriptable MIME types are forced
  to download with `nosniff` headers to block stored XSS attacks.
- **Legal Compliance**: Wi-Fi auditing utilities (`kali-launcher`) are intended solely
  for authorized security assessments on networks you own or have explicit written
  permission to test.

To report security issues, refer to [SECURITY.md](SECURITY.md).

---

## ⚠️ Known Limitations

- **5 V Power Sensitivity**: Heavy concurrent operations (compiling packages, large
  file transfers, or software video decoding) can cause input rail voltage sags.
  Under-voltage can trigger temporary USB bus resets. A stable 5 V / 3 A supply
  and heavy-gauge wiring are recommended.
- **Single Radio Contention**: The external adapter (`wlan1`) handles both normal
  internet connectivity and monitor-mode frame injection. Entering pentest mode
  temporarily disconnects the Pi from its uplink network.
- **Software Video Decoding**: The Raspberry Pi 3B lacks hardware acceleration for
  USB MJPEG decoding. 720p at 30 fps requires approximately 1.2 CPU cores.
- **Bluetooth Dropouts**: The on-board Broadcom Bluetooth controller can drop audio
  frames under sustained Wi-Fi throughput. Using an external USB Bluetooth dongle
  resolves radio interference.

---

## 📁 Repository Layout

```
.
├── config/              # User configuration (~/.config): labwc, GTK themes, taskbar
├── desktop/             # Desktop shortcuts, menu entries, and custom PINET SVG icons
├── docs/                # Architecture guides, hardware notes, and screenshot assets
├── eink-dashboard/      # E-ink status dashboard (SPI driver, carousel src, systemd units)
├── etc/                 # System configuration: hostapd, dnsmasq, nftables, NetworkManager
├── pinet-board/         # Captive portal Flask application (message board and file drop)
├── plymouth/            # PINET custom boot splash theme
├── scripts/
│   ├── bin/             # /usr/local/bin: Touchscreen apps, media centre, kali launcher
│   └── sbin/            # /usr/local/sbin: Power manager, ups guard, pentest scripts
├── systemd/             # Systemd service units, timers, and drop-in configurations
├── tests/               # Standalone unit test suite (301 tests, Python standard library)
└── tools/               # Developer utilities: icon generators, code-graph refreshers
```

---

## 🧪 Testing

The repository includes a comprehensive unit test suite written strictly with the
Python standard library. Tests run on any Linux or macOS environment without
requiring Raspberry Pi hardware or display servers:

```bash
python3 -B -m unittest discover -s tests
```

- **Filesystem Consistency**: Verifies that every installed path referenced by desktop
  files, systemd units, or shell scripts matches an existing file in the repository.
- **Headless Execution**: GUI modules lazily import GTK and Vte, allowing argument
  parsing, playlist caching, and configuration parsers to be tested in CI environments.
- **Power and Battery Math**: Validates battery percentage interpolation, resting
  voltage formulas, and load-shedding sequencing.

---

## 🤝 Contributing

Contributions and bug reports are welcome. Please read [CONTRIBUTING.md](CONTRIBUTING.md)
and adhere to the [Code of Conduct](CODE_OF_CONDUCT.md). Ensure all unit tests pass
prior to submitting pull requests.

---

## 📄 License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.

---

## 🙏 Acknowledgements

- [iptv-org/iptv](https://github.com/iptv-org/iptv) for public channel playlists.
- [raspotify](https://github.com/dtcooper/raspotify) and [librespot](https://github.com/librespot-org/librespot) for Spotify Connect audio streaming.
- [VLC media player](https://www.videolan.org/) for stream decoding.
- [Waveshare](https://www.waveshare.com/) for e-Paper hardware and driver libraries.
