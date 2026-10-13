#!/usr/bin/env python3
"""Generates a high-legibility, publication-grade hardware block diagram
for the PINET cyberdeck repository (docs/images/block-diagram.png).

Designed specifically for README scaling on GitHub:
- Sized at 1600x1050 with large, crisp typography (16-44px) so text is
  comfortably readable at standard 800px-wide web view.
- Color-coded functional subsystems (Power, Displays, Radios, Peripherals)
- Hardware chipsets, interfaces, bus badges, and protocols
- Clear power vs. data signal paths with high-contrast arrowheads
"""
import math
import os
from PIL import Image, ImageDraw, ImageFont

W, H = 1600, 1050

# Theme palette
BG_TOP = (12, 14, 18)
BG_BOT = (20, 23, 30)
GRID_COLOR = (28, 32, 42)
CARD_BG = (17, 20, 28)
CARD_BORDER = (48, 56, 70)

# Accent colors
ACCENT_BLUE = (56, 189, 248)    # Core / SoC
ACCENT_AMBER = (251, 191, 36)   # Power / UPS
ACCENT_CYAN = (6, 182, 212)     # Displays
ACCENT_GREEN = (74, 222, 128)   # Networking / Radios
ACCENT_PURPLE = (168, 85, 247)  # Peripherals / Media
TEXT_WHITE = (250, 250, 252)
TEXT_MUTED = (165, 175, 192)
TEXT_DIM = (115, 125, 140)

# Fonts
FONT_BOLD_PATH = "pinet-board/static/fonts/Roboto-Bold.ttf"
FONT_REG_PATH = "pinet-board/static/fonts/Roboto-Regular.ttf"

try:
    font_title = ImageFont.truetype(FONT_BOLD_PATH, 34)
    font_subtitle = ImageFont.truetype(FONT_REG_PATH, 17)
    font_sec = ImageFont.truetype(FONT_BOLD_PATH, 20)
    font_h1 = ImageFont.truetype(FONT_BOLD_PATH, 20)
    font_h2 = ImageFont.truetype(FONT_BOLD_PATH, 16)
    font_body = ImageFont.truetype(FONT_REG_PATH, 15)
    font_badge = ImageFont.truetype(FONT_BOLD_PATH, 13)
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
    pw, ph = tw + 16, th + 10
    draw.rounded_rectangle([x, y, x + pw, y + ph], radius=5, fill=bg + (250,), outline=color + (220,), width=1)
    draw.text((x + 8, y + 4), text, font=font_badge, fill=color)
    return pw, ph

def draw_card(draw, x, y, w, h, title, subtitle, items, accent_color, badge=None):
    # Card shadow
    draw.rounded_rectangle([x + 3, y + 4, x + w + 3, y + h + 4], radius=10, fill=(8, 10, 14, 180))
    # Card surface
    draw.rounded_rectangle([x, y, x + w, y + h], radius=10, fill=CARD_BG + (252,), outline=CARD_BORDER + (255,), width=1)
    # Accent top border strip
    draw.rounded_rectangle([x, y, x + w, y + 4], radius=2, fill=accent_color + (255,))
    
    # Title
    draw.text((x + 18, y + 16), title, font=font_h1, fill=TEXT_WHITE)
    if badge:
        draw_pill(draw, x + w - 105, y + 14, badge, accent_color)
        
    draw.text((x + 18, y + 43), subtitle, font=font_body, fill=accent_color)
    
    # Divider
    draw.line([(x + 16, y + 68), (x + w - 16, y + 68)], fill=CARD_BORDER + (200,), width=1)
    
    # Items
    curr_y = y + 80
    for icon_label, val in items:
        # Dot bullet
        draw.ellipse([x + 18, curr_y + 4, x + 25, curr_y + 11], fill=accent_color)
        draw.text((x + 34, curr_y), icon_label, font=font_h2, fill=TEXT_WHITE)
        draw.text((x + 34, curr_y + 21), val, font=font_body, fill=TEXT_MUTED)
        curr_y += 48

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
    head_len = 11
    angle1 = angle + math.pi * 0.85
    angle2 = angle - math.pi * 0.85
    p1 = (x1 + head_len * math.cos(angle1), y1 + head_len * math.sin(angle1))
    p2 = (x1 + head_len * math.cos(angle2), y1 + head_len * math.sin(angle2))
    draw.polygon([end, p1, p2], fill=color)
    
    if label:
        mx = (x0 + x1) / 2
        my = (y0 + y1) / 2
        bbox = draw.textbbox((0, 0), label, font=font_badge)
        lw = bbox[2] - bbox[0] + 16
        lh = bbox[3] - bbox[1] + 8
        ly = my - lh - 5 if label_side == "top" else my + 5
        lx = mx - lw / 2
        draw.rounded_rectangle([lx, ly, lx + lw, ly + lh], radius=4, fill=(13, 16, 22, 245), outline=color + (200,), width=1)
        draw.text((lx + 8, ly + 3), label, font=font_badge, fill=color)

def main():
    img = create_background()
    draw = ImageDraw.Draw(img)
    
    # ---------------- HEADER ----------------
    draw.text((45, 34), "PINET CYBER-DECK", font=font_title, fill=TEXT_WHITE)
    draw.text((45, 76), "Hardware Architecture, Subsystems & Interconnect Topology", font=font_subtitle, fill=ACCENT_CYAN)
    
    # Header badges
    draw_pill(draw, W - 490, 42, "PLATFORM: RASPBERRY PI 3B (REV 1.2)", ACCENT_BLUE)
    draw_pill(draw, W - 200, 42, "DEBIAN 13 TRIXIE", ACCENT_GREEN)
    draw.line([(45, 110), (W - 45, 110)], fill=CARD_BORDER + (200,), width=1)
    
    # ---------------- CENTRAL SOC HUB ----------------
    # Layout spacing:
    # Canvas W=1600
    # Left cards: x=45, w=440
    # Left gap: x=485 to 585 (w=100)
    # Center Hub: x=585, w=430
    # Right gap: x=1015 to 1115 (w=100)
    # Right cards: x=1115, w=440
    
    cx, cy, cw, ch = 585, 150, 430, 770
    
    # Glow around Core
    for g in range(8, 0, -2):
        draw.rounded_rectangle([cx - g, cy - g, cx + cw + g, cy + ch + g], radius=16, outline=ACCENT_BLUE + (25,))
    draw.rounded_rectangle([cx, cy, cx + cw, cy + ch], radius=14, fill=(15, 22, 36, 252), outline=ACCENT_BLUE, width=2)
    
    # Core banner
    draw.rounded_rectangle([cx, cy, cx + cw, cy + 54], radius=4, fill=(24, 38, 64, 255))
    draw.text((cx + 18, cy + 16), "CENTRAL PROCESSOR UNIT", font=font_sec, fill=TEXT_WHITE)
    draw_pill(draw, cx + cw - 105, cy + 14, "BCM2837", ACCENT_BLUE)
    
    # Core specs inside
    core_items = [
        ("Application Processor (SoC)", "Broadcom BCM2837 (4x Cortex-A53 @ 1.2 GHz)"),
        ("System Memory", "1 GB LPDDR2 SDRAM (Shared with GPU)"),
        ("Operating Environment", "Debian 13 'trixie' (64-bit) • Kernel 6.12+"),
        ("Display Server & Desktop", "labwc Wayland Compositor • wf-panel-pi"),
        ("Power Management Daemon", "pi-power-manager (Load Shedding Guard)"),
        ("Local Web & Media Services", "pinet-board (Flask), raspotify, hostapd"),
        ("Security Auditing Subsystem", "kali-launcher (Vte Terminal + Pentest)"),
    ]
    cur_y = cy + 74
    for label, val in core_items:
        draw.ellipse([cx + 18, cur_y + 4, cx + 25, cur_y + 11], fill=ACCENT_BLUE)
        draw.text((cx + 34, cur_y), label, font=font_h2, fill=ACCENT_CYAN)
        draw.text((cx + 34, cur_y + 22), val, font=font_body, fill=TEXT_WHITE)
        cur_y += 58
        if label != core_items[-1][0]:
            draw.line([(cx + 18, cur_y + 12), (cx + cw - 18, cur_y + 12)], fill=(28, 42, 66), width=1)
            cur_y += 28

    # ---------------- 1. POWER SUBSYSTEM (TOP LEFT) ----------------
    px, py, pw, ph = 45, 150, 440, 360
    draw_card(draw, px, py, pw, ph,
              "POWER SUBSYSTEM & UPS",
              "Battery Autonomy & Hardware Telemetry",
              [
                  ("Battery Pack", "2x 21700 Li-ion Cells (8400 mAh, 3.7 V)"),
                  ("UPS HAT & Gauge", "Waveshare UPS HAT (D) • INA219 (0x43)"),
                  ("Protection Daemon", "pinet-ups-guard (Shutdown <=3.3V / <=10%)"),
                  ("Voltage Compensation", "IR Resistance Math (0.045 Ohm, OCV Curve)"),
                  ("Load Shedding", "Sheds VNC/BT/AP on Kiosk & Pentest Run"),
              ],
              ACCENT_AMBER, badge="I2C / 5V")
    
    # Arrows from Power to Pi
    draw_arrow(draw, (px + pw, py + 90), (cx, cy + 90), ACCENT_AMBER, width=3, dashed=False, label="5.0 V / 3 A Rail", label_side="top")
    draw_arrow(draw, (px + pw, py + 220), (cx, cy + 200), ACCENT_AMBER, width=2, dashed=True, label="I2C (0x43)", label_side="bottom")

    # ---------------- 2. DISPLAYS SUBSYSTEM (BOTTOM LEFT) ----------------
    dx, dy, dw, dh = 45, 545, 440, 375
    draw_card(draw, dx, dy, dw, dh,
              "DUAL DISPLAY SUBSYSTEM",
              "Front Touchscreen + Rear Status Panel",
              [
                  ("Primary Touchscreen (Front)", "Official Pi 7\" DSI Panel (800x480 RGB)"),
                  ("Capacitive Touch", "edt_ft5x06 • EVIOCGRAB Touch Isolation"),
                  ("Secondary Panel (Rear)", "Waveshare 2.13\" e-Paper (250x122 SPI)"),
                  ("E-ink Carousel & Alert", "7-Screen Status Carousel • Pentest Screen"),
                  ("Backlight Management", "dsi-tap-wake (Double Tap) • swayidle 90s"),
                  ("Boot & Halt Splash", "Plymouth Breathing Pulse • DOOM Splash"),
              ],
              ACCENT_CYAN, badge="DSI + SPI")
              
    # Arrows from Displays to Pi
    draw_arrow(draw, (dx + dw, dy + 90), (cx, cy + 340), ACCENT_CYAN, width=2, dashed=False, label="DSI Video + I2C", label_side="top")
    draw_arrow(draw, (dx + dw, dy + 230), (cx, cy + 460), ACCENT_CYAN, width=2, dashed=False, label="SPI Bus 0 + GPIO", label_side="bottom")

    # ---------------- 3. NETWORKING & RADIOS (TOP RIGHT) ----------------
    nx, ny, nw, nh = 1115, 150, 440, 360
    draw_card(draw, nx, ny, nw, nh,
              "NETWORKING & RADIOS",
              "Hotspot, Uplink & Hardware Auditing",
              [
                  ("PINET Hotspot (wlan0)", "Broadcom BCM43438 • AP (10.10.10.1)"),
                  ("Captive Portal DNS", "dnsmasq Wildcard (/#/10.10.10.1) Redirect"),
                  ("Wi-Fi Uplink (wlan1)", "TP-Link Archer T2U • Monitor Mode & Inj."),
                  ("Wired Share (eth0)", "Static 10.42.0.1/24 + Pi-hole Ad Blocking"),
                  ("Firewall Security", "nftables Isolation (SSH/VNC Blocked)"),
              ],
              ACCENT_GREEN, badge="SDIO / USB")

    # Arrows from Radios to Pi
    draw_arrow(draw, (cx + cw, cy + 90), (nx, ny + 90), ACCENT_GREEN, width=2, dashed=False, label="SDIO (wlan0)", label_side="top")
    draw_arrow(draw, (cx + cw, cy + 180), (nx, ny + 180), ACCENT_GREEN, width=2, dashed=False, label="USB (wlan1)", label_side="top")
    draw_arrow(draw, (cx + cw, cy + 260), (nx, ny + 265), ACCENT_GREEN, width=2, dashed=False, label="PHY (eth0)", label_side="bottom")

    # ---------------- 4. PERIPHERALS & MEDIA (BOTTOM RIGHT) ----------------
    mx, my, mw, mh = 1115, 545, 440, 375
    draw_card(draw, mx, my, mw, mh,
              "PERIPHERALS & MEDIA",
              "Audio Endpoints, Camera & Capture",
              [
                  ("Pi Camera Module V2", "Sony IMX219 8 MP Sensor • MJPEG Server"),
                  ("HDMI Video Field Monitor", "MacroSilicon MS2109 USB Capture (UVC)"),
                  ("Mass Media Storage", "58 GB USB 3.0 Drive at /mnt/pinet-media"),
                  ("Wireless Audio Out", "Bluetooth A2DP via PipeWire (150% Boost)"),
                  ("Touch Virtual Keyboard", "wvkbd On-Demand with Auto-Compaction"),
                  ("Media Centre Engine", "Spotify Connect, IPTV & HDMI Monitor"),
              ],
              ACCENT_PURPLE, badge="CSI / USB / BT")

    # Arrows from Peripherals to Pi
    draw_arrow(draw, (cx + cw, cy + 360), (mx, my + 80), ACCENT_PURPLE, width=2, dashed=False, label="15-pin CSI (Camera)", label_side="top")
    draw_arrow(draw, (cx + cw, cy + 450), (mx, my + 160), ACCENT_PURPLE, width=2, dashed=False, label="USB (UVC Capture)", label_side="top")
    draw_arrow(draw, (cx + cw, cy + 540), (mx, my + 230), ACCENT_PURPLE, width=2, dashed=False, label="USB (/mnt/media)", label_side="bottom")
    draw_arrow(draw, (cx + cw, cy + 630), (mx, my + 300), ACCENT_PURPLE, width=2, dashed=True, label="Bluetooth Audio", label_side="bottom")

    # ---------------- FOOTER TECHNICAL LEGEND ----------------
    legend_y = H - 90
    draw.rounded_rectangle([45, legend_y, W - 45, legend_y + 55], radius=8, fill=(16, 20, 28, 245), outline=CARD_BORDER, width=1)
    
    draw.text((65, legend_y + 17), "BUS LEGEND:", font=font_sec, fill=TEXT_WHITE)
    leg_x = 205
    legends = [
        ("Power Delivery (Solid)", ACCENT_AMBER),
        ("Hardware Telemetry / I2C (Dashed)", ACCENT_AMBER),
        ("Display & Touch Data (DSI/SPI)", ACCENT_CYAN),
        ("Wireless & Network Buses (SDIO/USB/PHY)", ACCENT_GREEN),
        ("Media & Peripheral Lines (CSI/USB/BT)", ACCENT_PURPLE),
    ]
    for label, col in legends:
        draw.rounded_rectangle([leg_x, legend_y + 19, leg_x + 14, legend_y + 33], radius=3, fill=col)
        draw.text((leg_x + 22, legend_y + 18), label, font=font_badge, fill=TEXT_MUTED)
        leg_x += draw.textbbox((0, 0), label, font=font_badge)[2] + 35
        
    out_png = "docs/images/block-diagram.png"
    img.save(out_png, "PNG", optimize=True)
    print(f"Saved publication-grade block diagram to {out_png} ({os.path.getsize(out_png) / 1024:.1f} KB)")

if __name__ == "__main__":
    main()
