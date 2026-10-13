#!/usr/bin/env python3
"""Generates an animated showcase GIF of the PINET cyber-deck UI for the README.
Uses Pillow to composite screenshots, format e-ink panels, render caption pills,
and generate smooth cross-fades between subsystems.

Run with:
    uv run --with pillow --with numpy python3 tools/make_showcase_gif.py
"""
import os
import glob
from PIL import Image, ImageDraw, ImageFont

W, H = 800, 480
FONT_PATH = "pinet-board/static/fonts/Roboto-Bold.ttf"
REG_FONT_PATH = "pinet-board/static/fonts/Roboto-Regular.ttf"

SCENES = [
    ("docs/images/boot-splash.png", "PINET Cyber-Deck", "Boot Splash (Debian 13 labwc Wayland)"),
    ("docs/images/desktop.png", "Touchscreen Desktop", "800x480 DSI • Single-Tap Launchers & Tray Controls"),
    ("docs/images/media-centre.png", "Media Centre Chooser", "Spotify Connect • Live IPTV • HDMI Field Monitor"),
    ("docs/images/media-centre-iptv.png", "Live IPTV Channels", "576p Indian Broadcast Streams • Pre-probed Liveness"),
    ("docs/images/media-centre-video.png", "IPTV Video Playback", "Full-Screen VLC • Auto-hiding Corner Touch Controls"),
    ("docs/images/hdmi-monitor.png", "HDMI Field Monitor", "Live Video Input via USB UVC Capture Dongle"),
    ("docs/images/kali-tools.png", "Kali Auditing Toolkit", "Native Pentest Suite • Embedded Vte Terminal Pane"),
    ("docs/images/portal-login.png", "PINET Captive Portal", "Offline Wi-Fi Message Board & File Drop (10.10.10.1)"),
    ("docs/images/ethernet-share.png", "Ethernet Share", "Wired Uplink Routing to eth0 with Pi-hole Ad Blocking"),
    ("docs/images/eink-status.png", "2.13\" Rear E-ink Display", "Always-On Telemetry (CPU, Temp, RAM, Weather, IPs)"),
    ("docs/images/eink-hotspot.png", "E-ink Hotspot Card", "Scannable Wi-Fi Join QR Code & Guest Credentials"),
    ("docs/images/lock-screen.png", "Passcode Lock Screen", "Touchscreen Numeric PIN Pad Overlay & Screen Sleep"),
]

def make_bg():
    img = Image.new("RGB", (W, H))
    draw = ImageDraw.Draw(img)
    # Dark cyberdeck gradient from #0f1114 to #1e2128
    top = (15, 17, 20)
    bot = (30, 33, 40)
    for y in range(H):
        ratio = y / H
        r = int(top[0] + (bot[0] - top[0]) * ratio)
        g = int(top[1] + (bot[1] - top[1]) * ratio)
        b = int(top[2] + (bot[2] - top[2]) * ratio)
        draw.line([(0, y), (W, y)], fill=(r, g, b))
    return img

BG = make_bg()

try:
    font_bold = ImageFont.truetype(FONT_PATH, 16)
    font_sub = ImageFont.truetype(REG_FONT_PATH, 13)
except Exception:
    font_bold = ImageFont.load_default()
    font_sub = ImageFont.load_default()

def render_scene(path, title, subtitle):
    base = BG.copy()
    src = Image.open(path).convert("RGBA")
    
    # Check if e-ink display (750x366 or non-800x480)
    if src.width != W or src.height != H:
        # Scale to fit nicely with bezel
        target_w = 640
        target_h = int(src.height * (target_w / src.width))
        resized = src.resize((target_w, target_h), Image.LANCZOS)
        x = (W - target_w) // 2
        y = (H - 50 - target_h) // 2
        # Draw frame/bezel
        bezel_draw = ImageDraw.Draw(base)
        bezel_box = [x - 6, y - 6, x + target_w + 6, y + target_h + 6]
        bezel_draw.rectangle(bezel_box, outline=(60, 65, 75), width=2, fill=(20, 22, 26))
        base.paste(resized, (x, y), resized)
    else:
        base.paste(src, (0, 0), src)
    
    # Render pill overlay at bottom
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)
    
    pill_h = 36
    pill_w = W - 32
    pill_x0 = 16
    pill_y0 = H - pill_h - 12
    pill_box = [pill_x0, pill_y0, pill_x0 + pill_w, pill_y0 + pill_h]
    
    # Semi-transparent dark pill background
    odraw.rounded_rectangle(pill_box, radius=8, fill=(12, 14, 18, 225), outline=(50, 55, 65, 200), width=1)
    
    # Terminal green accent dot
    odraw.ellipse([pill_x0 + 12, pill_y0 + 13, pill_x0 + 22, pill_y0 + 23], fill=(74, 222, 128))
    
    # Text
    odraw.text((pill_x0 + 30, pill_y0 + 9), title, font=font_bold, fill=(245, 245, 245))
    
    # Subtitle
    sub_bbox = odraw.textbbox((0, 0), subtitle, font=font_sub)
    sub_w = sub_bbox[2] - sub_bbox[0]
    odraw.text((pill_x0 + pill_w - sub_w - 14, pill_y0 + 11), subtitle, font=font_sub, fill=(170, 178, 190))
    
    final = Image.alpha_composite(base.convert("RGBA"), overlay).convert("RGB")
    return final

def blend(im1, im2, alpha):
    return Image.blend(im1, im2, alpha)

def main():
    print("Rendering scene frames...")
    scene_images = []
    for path, title, sub in SCENES:
        print(f"  Rendering {title} ({path})...")
        scene_images.append(render_scene(path, title, sub))
        
    frames = []
    durations = []
    
    # Hold frames per scene and transition frames
    HOLD_COUNT = 6    # 6 frames * 250ms = 1.5s
    FADE_COUNT = 3    # 3 frames * 70ms = 210ms
    
    for i in range(len(scene_images)):
        cur = scene_images[i]
        nxt = scene_images[(i + 1) % len(scene_images)]
        
        # Hold
        for _ in range(HOLD_COUNT):
            frames.append(cur)
            durations.append(250)
            
        # Crossfade to next scene
        for f in range(1, FADE_COUNT + 1):
            alpha = f / (FADE_COUNT + 1)
            frames.append(blend(cur, nxt, alpha))
            durations.append(70)
            
    print(f"Total frames: {len(frames)}. Optimizing palette and saving GIF...")
    
    # Save optimized GIF with adaptive palette
    out_path = "docs/images/pinet-showcase.gif"
    
    # Convert frames to palette mode using first frame palette or adaptive per frame
    palette_frames = [f.convert("P", palette=Image.ADAPTIVE, colors=128) for f in frames]
    
    palette_frames[0].save(
        out_path,
        save_all=True,
        append_images=palette_frames[1:],
        duration=durations,
        loop=0,
        optimize=True
    )
    
    size_mb = os.path.getsize(out_path) / (1024 * 1024)
    print(f"Saved {out_path} ({size_mb:.2f} MB)")

if __name__ == "__main__":
    main()
