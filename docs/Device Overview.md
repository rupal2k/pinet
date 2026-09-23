---
tags: [project, raspberry-pi, device, overview, active]
---

# PINET Pi — Device Overview

**What it is:** a single Raspberry Pi 3B turned into a self-contained, multi-purpose
appliance. It started as an e-ink status dashboard and has grown into five
coexisting subsystems on one board — a status panel, a private offline
network + portal, a touchscreen photo frame / kiosk, a Wi-Fi security-testing
toolbox, and a Bluetooth music endpoint — all coordinated so they share the
Pi's tight power budget without stepping on each other.

Think of it as a pocket "home server + info appliance": it shows you status at a
glance, hosts its own guest network and message board with no internet needed,
doubles as a photo frame and camera, can audit your own Wi-Fi, and streams
Spotify to a Bluetooth speaker.

## Hardware

| Fact | Value |
|---|---|
| Board | Raspberry Pi 3 Model B Rev 1.2 · Debian 13 "trixie" (64-bit) |
| Host / user | `raspberrypi` / `rupal` (passwordless sudo) |
| e-ink panel | Waveshare 2.13" e-Paper HAT (V4), 250×122, 1-bit — over SPI/GPIO |
| Touchscreen | Official Raspberry Pi 7" DSI, 800×480, capacitive touch |
| Wi-Fi (station) | `wlan1` = TP-Link Archer T2U Plus (RTL8821AU) — home Wi-Fi / internet uplink; the only monitor-mode-capable radio |
| Wi-Fi (AP) | `wlan0` = onboard Broadcom — dedicated to the `PINET` hotspot (2.4GHz, no monitor mode) |
| Storage | 16GB SD (OS) + 58GB USB drive mounted `/mnt/pinet-media` (PINET uploads, slideshow photos, camera captures) |
| Audio out | Bluetooth speaker ("Dubstep Pop 600") via PipeWire |
| Reachable at | `192.168.29.125` (wlan1, DHCP) / `192.168.29.166` (Ethernet) / `10.10.10.1` (PINET) — treat IPs as DHCP |

## What it can do — the five subsystems

### 1. e-Ink status dashboard  ([[Overview]], [[dashboard.py]])
Always-on 2.13" panel cycling a carousel: date/time, CPU/RAM/temp, weather,
network status, a Wi-Fi QR join screen, a logo/health screen (voltage + disk),
and a PINET hotspot join screen. Runs headless as `pi-eink-dashboard.service`;
e-paper holds its image with no power, and a shutdown splash leaves a logo on
the panel when it powers off. Shows a **pirate "PENTEST" screen** while Wi-Fi
pentest mode is active.

### 2. PINET — private offline network + portal  ([[pinet-board]], [[pinet-captive-portal]])
A self-hosted **intranet-only Wi-Fi hotspot** (SSID `PINET`, `10.10.10.1`, no
internet) running hostapd + dnsmasq on `wlan0`. Phones that join get an
automatic captive-portal pop-up (confirmed on Samsung/Android) into
**`pinet-board`** — an anonymous message board + up to ~1GB file sharing
(tabbed UI, in-browser file viewing, guest/admin roles), stored on the USB
drive. Purely local: guests can reach the Pi but nothing beyond it, and a
firewall blocks SSH/VNC from PINET clients. **As of 2026-09-16 PINET is
on-demand** — it does not auto-start at boot; bring it up/down with the
**Start PINET / Stop PINET** desktop shortcuts.

### 3. DSI touchscreen — photo frame + kiosks  ([[dsi photo frame]])
The 7" screen is a **digital photo frame** (fit-to-screen slideshow over a
blurred background) that sleeps and wakes on a double-tap. On-demand desktop
shortcuts launch **kiosks**: the **Ezykam** smart-camera web app, a **live Pi
camera** view with on-screen **Photo/Video capture** (saved to
`/mnt/pinet-media/camera`, upright), and the **PINET portal**. A
**pi-power-manager** sheds heavy services (VNC, Bluetooth, PINET, slideshow)
whenever a kiosk is open so the load never browns out the board. Dark PINET
theme, hand-drawn icon set, 12-hour clock, boot splash.

### 4. Kali / Wi-Fi security toolbox  ([[Device Overview]], desktop `kali-tools-guide.txt`)
Native security tools (nmap, arp-scan, masscan, aircrack-ng suite, wifite,
reaver, bully, mdk4, hcxdumptool/tools, macchanger, tcpdump) for **authorized**
network and Wi-Fi auditing. The **Kali Tools** desktop shortcut opens a terminal
with everything on PATH. A **pentest power mode** (`wifi-pentest-start/stop`)
flips `wlan1` into monitor mode, stops PINET, sheds power, and flags the e-ink
pirate screen — reversing cleanly. (Only test networks you own / are authorized
to test.)

### 5. raspotify — Spotify → Bluetooth  ([[Device Overview]])
A **Spotify Connect** endpoint ("raspotify (raspberrypi)"): select it in the
Spotify app and it plays through the Pi to the paired **Bluetooth speaker** via
PipeWire. Configured for the BT output (pulseaudio backend, sandbox opened for
the session socket, linear volume, sink boosted to 150%).

## How you operate it

- **Desktop (touchscreen or VNC):** shortcuts for Camera, Ezykam, PINET Portal,
  Photo Frame, Start/Stop PINET, Start/Stop Spotify, Graphs, and Kali Tools.
  Slideshow runs when idle.
- **At a glance:** the e-ink panel — no interaction needed.
- **Remotely:** SSH/SFTP over wlan1 or Ethernet (blocked from PINET guests).
- **On the go:** it's portable; on a phone hotspot the home IPs change (DHCP).

## Key things to know

- **Power is the main constraint.** The 5V supply is marginal — sustained heavy
  load (Chromium-class browsers, big installs, or a loose plug) can brown the
  board out and reset it. The desktop uses the lightweight `cog` browser for
  kiosks, and pi-power-manager sheds load during kiosks/pentest. The real cure
  is a solid 5V/3A supply + short thick cable. See [[power and undervoltage]].
- **PINET is offline by design** (no internet bridge) and now **off by default**.
- **wlan1 is dual-purpose** — internet uplink *and* the only pentest radio;
  entering pentest mode takes the Pi offline until you stop it.
- Everything auto-starts on boot **except** PINET; the e-ink, desktop, photo
  frame, and raspotify come up on their own.

## Detailed notes
[[Overview]] · [[dashboard.py]] · [[icons.py]] · [[config.ini]] ·
[[systemd service]] · [[dsi photo frame]] · [[pinet-board]] ·
[[pinet-captive-portal]] · [[power and undervoltage]] · [[fixes session log]]
