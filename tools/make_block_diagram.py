#!/usr/bin/env python3
"""Generates a publication-grade, high-resolution hardware block diagram
for the PINET cyberdeck repository (docs/images/block-diagram.png).

Renders a dark cyberdeck schematic with:
- Color-coded functional subsystems (Power, Displays, Radios, Peripherals)
- Hardware chipsets, interfaces, bus badges, and protocols
- Clear power vs. data signal paths with arrowheads
- Clean technical typography and subtle schematic grid
"""
import math
import os
from PIL import Image, ImageDraw, ImageFont

W, H = 2200, 1200  # Wide layout with ample margin

# Theme palette
BG_TOP = (12, 14, 18)
BG_BOT = (20, 23, 30)
GRID_COLOR = (26, 30, 38)
CARD_BG = (17, 20, 27)
CARD_BORDER = (45, 52, 65)

# Accent colors
ACCENT_BLUE = (56, 189, 248)    # Core / SoC
ACCENT_AMBER = (251, 191, 36)   # Power / UPS
ACCENT_CYAN = (6, 182, 212)     # Displays
ACCENT_GREEN = (74, 222, 128)   # Networking / Radios
ACCENT_PURPLE = (168, 85, 247)  # Peripherals / Media
TEXT_WHITE = (245, 247, 250)
TEXT_MUTED = (160, 168, 182)
TEXT_DIM = (107, 114, 128)

# Fonts
FONT_BOLD_PATH = "pinet-board/static/fonts/Roboto-Bold.ttf"
FONT_REG_PATH = "pinet-board/static/fonts/Roboto-Regular.ttf"

try:
    font_title = ImageFont.truetype(FONT_BOLD_PATH, 34)
    font_subtitle = ImageFont.truetype(FONT_REG_PATH, 16)
    font_sec = ImageFont.truetype(FONT_BOLD_PATH, 18)
    font_h1 = ImageFont.truetype(FONT_BOLD_PATH, 19)
    font_h2 = ImageFont.truetype(FONT_BOLD_PATH, 14)
    font_body = ImageFont.truetype(FONT_REG_PATH, 13)
    font_badge = ImageFont.truetype(FONT_BOLD_PATH, 11)
except Exception:
    font_title = font_subtitle = font_sec = font_h1 = font_h2 = font_body = font_badge = ImageFont.load_default()

def create_background():
    img = Image.new("RGBA", (W, H))
    draw = ImageDraw.Draw(img)
    # Background gradient
    for y in range(H):
        ratio = y / H
        r = int(BG_TOP[0] + (BG_BOT[0] - BG_TOP[0]) * ratio)
        g = int(BG_TOP[1] + (BG_BOT[1] - BG_TOP[1]) * ratio)
        b = int(BG_TOP[2] + (BG_BOT[2] - BG_TOP[2]) * ratio)
        draw.line([(0, y), (W, y)], fill=(r, g, b, 255))
    
    # Technical schematic grid
    grid_size = 40
    for x in range(0, W, grid_size):
        draw.line([(x, 0), (x, H)], fill=GRID_COLOR + (130,), width=1)
    for y in range(0, H, grid_size):
        draw.line([(0, y), (W, y)], fill=GRID_COLOR + (130,), width=1)
        
    return img

def draw_pill(draw, x, y, text, color, bg=(24, 28, 38)):
    bbox = draw.textbbox((0, 0), text, font=font_badge)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    pw, ph = tw + 14, th + 8
    draw.rounded_rectangle([x, y, x + pw, y + ph], radius=4, fill=bg + (245,), outline=color + (200,), width=1)
    draw.text((x + 7, y + 3), text, font=font_badge, fill=color)
    return pw, ph

def draw_card(draw, x, y, w, h, title, subtitle, items, accent_color, badge=None):
    # Card shadow
    draw.rounded_rectangle([x + 3, y + 4, x + w + 3, y + h + 4], radius=10, fill=(8, 10, 14, 160))
    # Card surface
    draw.rounded_rectangle([x, y, x + w, y + h], radius=10, fill=CARD_BG + (252,), outline=CARD_BORDER + (255,), width=1)
    # Accent top border strip
    draw.rounded_rectangle([x, y, x + w, y + 4], radius=2, fill=accent_color + (255,))
    
    # Title
    draw.text((x + 18, y + 15), title, font=font_h1, fill=TEXT_WHITE)
    if badge:
        draw_pill(draw, x + w - 95, y + 14, badge, accent_color)
        
    draw.text((x + 18, y + 40), subtitle, font=font_body, fill=accent_color)
    
    # Divider
    draw.line([(x + 16, y + 62), (x + w - 16, y + 62)], fill=CARD_BORDER + (180,), width=1)
    
    # Items
    curr_y = y + 74
    for icon_label, val in items:
        # Dot bullet
        draw.ellipse([x + 18, curr_y + 4, x + 24, curr_y + 10], fill=accent_color)
        draw.text((x + 32, curr_y), icon_label, font=font_h2, fill=TEXT_WHITE)
        draw.text((x + 32, curr_y + 18), val, font=font_body, fill=TEXT_MUTED)
        curr_y += 44

def draw_arrow(draw, start, end, color, width=2, dashed=False, label=None, label_side="top"):
    x0, y0 = start
    x1, y1 = end
    
    if dashed:
        dist = math.hypot(x1 - x0, y1 - y0)
        dash_len = 8
        gap_len = 6
        step = dash_len + gap_len
        num_dashes = int(dist // step)
        dx = (x1 - x0) / dist
        dy = (y1 - y0) / dist
        for i in range(num_dashes):
            sx = x0 + i * step * dx
            sy = y0 + i * step * dy
            ex = sx + dash_len * dx
            ey = sy + dash_len * dy
            draw.line([(sx, sy), (ex, ey)], fill=color, width=width)
    else:
        draw.line([start, end], fill=color, width=width)
        
    # Arrow head at end
    angle = math.atan2(y1 - y0, x1 - x0)
    head_len = 9
    angle1 = angle + math.pi * 0.85
    angle2 = angle - math.pi * 0.85
    p1 = (x1 + head_len * math.cos(angle1), y1 + head_len * math.sin(angle1))
    p2 = (x1 + head_len * math.cos(angle2), y1 + head_len * math.sin(angle2))
    draw.polygon([end, p1, p2], fill=color)
    
    if label:
        mx = (x0 + x1) / 2
        my = (y0 + y1) / 2
        bbox = draw.textbbox((0, 0), label, font=font_badge)
        lw = bbox[2] - bbox[0] + 12
        lh = bbox[3] - bbox[1] + 6
        ly = my - lh - 4 if label_side == "top" else my + 4
        lx = mx - lw / 2
        draw.rounded_rectangle([lx, ly, lx + lw, ly + lh], radius=4, fill=(13, 16, 22, 240), outline=color + (180,), width=1)
        draw.text((lx + 6, ly + 2), label, font=font_badge, fill=color)

def main():
    img = create_background()
    draw = ImageDraw.Draw(img)
    
    # ---------------- HEADER ----------------
    draw.text((60, 42), "PINET CYBER-DECK", font=font_title, fill=TEXT_WHITE)
    draw.text((60, 84), "Hardware Architecture, Subsystems & Interconnect Topology", font=font_subtitle, fill=ACCENT_CYAN)
    
    # Header badges
    draw_pill(draw, W - 490, 50, "PLATFORM: RASPBERRY PI 3B (REV 1.2)", ACCENT_BLUE)
    draw_pill(draw, W - 210, 50, "DEBIAN 13 TRIXIE", ACCENT_GREEN)
    draw.line([(60, 120), (W - 60, 120)], fill=CARD_BORDER + (200,), width=1)
    
    # ---------------- CENTRAL SOC HUB ----------------
    # Layout spacing:
    # Left cards: x=60 to 650 (w=590)
    # Gap: 650 to 820 (w=170) for arrows
    # Center Hub: x=820 to 1380 (w=560)
    # Gap: 1380 to 1550 (w=170) for arrows
    # Right cards: x=1550 to 2140 (w=590)
    
    cx, cy, cw, ch = 800, 240, 540, 680
    
    # Glow around Core
    for g in range(8, 0, -2):
        draw.rounded_rectangle([cx - g, cy - g, cx + cw + g, cy + ch + g], radius=16, outline=ACCENT_BLUE + (25,))
    draw.rounded_rectangle([cx, cy, cx + cw, cy + ch], radius=14, fill=(15, 22, 36, 252), outline=ACCENT_BLUE, width=2)
    # Core banner
    draw.rounded_rectangle([cx, cy, cx + cw, cy + 50], radius=4, fill=(24, 38, 64, 255))
    draw.text((cx + 22, cy + 14), "CENTRAL PROCESSOR UNIT (SBC)", font=font_sec, fill=TEXT_WHITE)
    draw_pill(draw, cx + cw - 105, cy + 13, "BCM2837", ACCENT_BLUE)
    
    # Core specs inside
    core_items = [
        ("Application Processor (SoC)", "Broadcom BCM2837 (4x ARM Cortex-A53 @ 1.2 GHz, 64-bit ARMv8-A)"),
        ("System Memory", "1 GB LPDDR2 SDRAM (Shared dynamically with VideoCore IV GPU)"),
        ("Operating System", "Debian 13 'trixie' (64-bit) • Linux Kernel 6.12+ (AArch64)"),
        ("Compositor & Display Server", "labwc Wayland Compositor • wf-panel-pi Custom Dark Taskbar"),
        ("Power Management Daemon", "pi-power-manager (Load Shedding, Brownout Guard & Staggering)"),
        ("Local Web & Media Services", "pinet-board (Flask), raspotify Connect, hostapd, dnsmasq"),
        ("Security Auditing Subsystem", "kali-launcher (Integrated GTK3/Vte Terminal + Pentest Daemon)"),
    ]
    cur_y = cy + 68
    for label, val in core_items:
        draw.ellipse([cx + 20, cur_y + 4, cx + 26, cur_y + 10], fill=ACCENT_BLUE)
        draw.text((cx + 34, cur_y), label, font=font_h2, fill=ACCENT_CYAN)
        draw.text((cx + 34, cur_y + 20), val, font=font_body, fill=TEXT_WHITE)
        cur_y += 52
        if label != core_items[-1][0]:
            draw.line([(cx + 20, cur_y + 12), (cx + cw - 20, cur_y + 12)], fill=(28, 42, 66), width=1)
            cur_y += 24

    # ---------------- 1. POWER SUBSYSTEM (TOP LEFT) ----------------
    px, py, pw, ph = 50, 180, 580, 290
    draw_card(draw, px, py, pw, ph,
              "POWER SUBSYSTEM & UPS",
              "Uninterruptible Battery Power & Live Hardware Telemetry",
              [
                  ("Battery Pack", "2x 21700 Li-ion Cells in Parallel (8400 mAh, 3.7 V Nominal)"),
                  ("UPS HAT & Gauge", "Waveshare UPS HAT (D) • INA219 Current/Voltage Sensor (0x43)"),
                  ("Protection Daemon", "pinet-ups-guard (15s Poll, Auto-Shutdown <=3.3V / <=10%)"),
                  ("Resting Math", "Internal Resistance Compensation (IR = 0.045 Ohm, OCV Curve)"),
                  ("Power Profile", "Proactive Load Shedding (VNC, BT, AP) on Kiosk/Pentest Launch"),
              ],
              ACCENT_AMBER, badge="I2C / 5V")
    
    # Arrows from Power to Pi
    draw_arrow(draw, (px + pw, py + 80), (cx, cy + 70), ACCENT_AMBER, width=3, dashed=False, label="5.0 V / 3.0 A Power Rail", label_side="top")
    draw_arrow(draw, (px + pw, py + 190), (cx, cy + 150), ACCENT_AMBER, width=2, dashed=True, label="I2C Bus 1 (0x43) Telemetry", label_side="bottom")

    # ---------------- 2. DISPLAYS SUBSYSTEM (BOTTOM LEFT) ----------------
    dx, dy, dw, dh = 50, 520, 580, 350
    draw_card(draw, dx, dy, dw, dh,
              "DUAL DISPLAY SUBSYSTEM",
              "Front Touchscreen GUI + Always-On Rear Status Panel",
              [
                  ("Primary Touchscreen (Front)", "Official Raspberry Pi 7\" DSI Panel (800x480, 24-bit RGB)"),
                  ("Capacitive Touch Controller", "edt_ft5x06 • EVIOCGRAB Exclusive Touch Isolation on Sleep"),
                  ("Secondary Panel (Rear)", "Waveshare 2.13\" e-Paper HAT V4 (250x122, 1-bit Monochrome)"),
                  ("E-ink Carousel & Alert", "7-Screen Status Carousel • Headless SPI • Pirate Pentest Banner"),
                  ("DSI Backlight Management", "dsi-tap-wake (Double-Tap Wake) • swayidle 90s Sleep Timeout"),
                  ("Boot & Shutdown Splash", "Plymouth Animated Breathing Pulse • DOOM Splash on Shutdown"),
              ],
              ACCENT_CYAN, badge="DSI + SPI")
              
    # Arrows from Displays to Pi
    draw_arrow(draw, (dx + dw, dy + 75), (cx, cy + 280), ACCENT_CYAN, width=2, dashed=False, label="DSI Video + I2C Touch", label_side="top")
    draw_arrow(draw, (dx + dw, dy + 215), (cx, cy + 370), ACCENT_CYAN, width=2, dashed=False, label="SPI Bus 0 + GPIO Signals", label_side="bottom")

    # ---------------- 3. NETWORKING & RADIOS (TOP RIGHT) ----------------
    nx, ny, nw, nh = 1570, 180, 580, 290
    draw_card(draw, nx, ny, nw, nh,
              "NETWORKING & RADIO INTERFACES",
              "Isolated Intranet Hotspot, Station Uplink & Hardware Auditing",
              [
                  ("PINET Offline Hotspot (wlan0)", "Onboard Broadcom BCM43438 • 2.4 GHz 802.11n AP (10.10.10.1)"),
                  ("Captive Portal Redirection", "dnsmasq Wildcard DNS (/#/10.10.10.1) • Mobile Auto-Popup"),
                  ("External Wi-Fi Uplink (wlan1)", "TP-Link Archer T2U Plus (RTL8821AU) • Monitor Mode & Injection"),
                  ("Wired Ethernet Share (eth0)", "Static 10.42.0.1/24 • DHCP Leases 10.42.0.10-254 + Pi-hole DNS"),
                  ("Firewall Security", "nftables Isolation (SSH/VNC Blocked from PINET Hotspot Guests)"),
              ],
              ACCENT_GREEN, badge="SDIO / USB")

    # Arrows from Radios to Pi
    draw_arrow(draw, (cx + cw, cy + 70), (nx, ny + 70), ACCENT_GREEN, width=2, dashed=False, label="SDIO (wlan0 AP)", label_side="top")
    draw_arrow(draw, (cx + cw, cy + 150), (nx, ny + 155), ACCENT_GREEN, width=2, dashed=False, label="USB 2.0 (wlan1 Uplink)", label_side="top")
    draw_arrow(draw, (cx + cw, cy + 220), (nx, ny + 235), ACCENT_GREEN, width=2, dashed=False, label="Built-in PHY (eth0 Share)", label_side="bottom")

    # ---------------- 4. PERIPHERALS & MEDIA (BOTTOM RIGHT) ----------------
    mx, my, mw, mh = 1570, 520, 580, 350
    draw_card(draw, mx, my, mw, mh,
              "PERIPHERALS, CAPTURE & STORAGE",
              "Audio Endpoints, Hardware Camera & Video Dongles",
              [
                  ("Pi Camera Module V2", "Sony IMX219 8 MP Sensor • picamera2 640x480 MJPEG Streamer"),
                  ("HDMI Video Field Monitor", "MacroSilicon MS2109 USB Capture Dongle (UVC Video / MJPEG)"),
                  ("Removable Media Storage", "58 GB USB 3.0 Flash Drive mounted at /mnt/pinet-media"),
                  ("Wireless Audio Output", "Bluetooth A2DP Sink via PipeWire / WirePlumber (150% Boost)"),
                  ("Touch Input Enhancement", "On-Screen Virtual Keyboard (wvkbd) with Auto-Compaction"),
                  ("Media Centre Engine", "Unified Chooser for Spotify Connect, IPTV & HDMI Field Monitor"),
              ],
              ACCENT_PURPLE, badge="CSI / USB / BT")

    # Arrows from Peripherals to Pi
    draw_arrow(draw, (cx + cw, cy + 300), (mx, my + 60), ACCENT_PURPLE, width=2, dashed=False, label="15-pin CSI (Camera)", label_side="top")
    draw_arrow(draw, (cx + cw, cy + 380), (mx, my + 130), ACCENT_PURPLE, width=2, dashed=False, label="USB 2.0 (UVC Capture)", label_side="top")
    draw_arrow(draw, (cx + cw, cy + 460), (mx, my + 195), ACCENT_PURPLE, width=2, dashed=False, label="USB 2.0 (/mnt/pinet-media)", label_side="bottom")
    draw_arrow(draw, (cx + cw, cy + 540), (mx, my + 260), ACCENT_PURPLE, width=2, dashed=True, label="Bluetooth A2DP Audio", label_side="bottom")

    # ---------------- FOOTER TECHNICAL LEGEND ----------------
    legend_y = H - 100
    draw.rounded_rectangle([60, legend_y, W - 60, legend_y + 55], radius=8, fill=(16, 20, 27, 240), outline=CARD_BORDER, width=1)
    
    draw.text((80, legend_y + 18), "BUS LEGEND:", font=font_sec, fill=TEXT_WHITE)
    leg_x = 220
    legends = [
        ("Power Delivery (Solid)", ACCENT_AMBER),
        ("Hardware Telemetry / I2C (Dashed)", ACCENT_AMBER),
        ("Display & Touch Data (DSI/SPI)", ACCENT_CYAN),
        ("Wireless & Network Buses (SDIO/USB/PHY)", ACCENT_GREEN),
        ("Media & Peripheral Lines (CSI/USB/BT)", ACCENT_PURPLE),
    ]
    for label, col in legends:
        draw.rounded_rectangle([leg_x, legend_y + 20, leg_x + 14, legend_y + 34], radius=3, fill=col)
        draw.text((leg_x + 22, legend_y + 20), label, font=font_badge, fill=TEXT_MUTED)
        leg_x += draw.textbbox((0, 0), label, font=font_badge)[2] + 45
        
    out_png = "docs/images/block-diagram.png"
    img.save(out_png, "PNG", optimize=True)
    print(f"Saved publication-grade block diagram to {out_png} ({os.path.getsize(out_png) / 1024:.1f} KB)")

if __name__ == "__main__":
    main()
