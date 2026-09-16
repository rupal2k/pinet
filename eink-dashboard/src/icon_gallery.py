"""Render every icon in a labeled grid for visual QA -- no e-ink hardware needed."""
from PIL import Image, ImageDraw, ImageFont, ImageOps

import icons

FONT = ImageFont.truetype("/usr/share/fonts/truetype/roboto/unhinted/RobotoTTF/Roboto-Regular.ttf", 11)

ITEMS = [
    ("calendar", lambda d, x, y: icons.calendar(d, x, y, size=14)),
    ("clock", lambda d, x, y: icons.clock(d, x + 14, y + 14, r=11)),
    ("cpu_chip", lambda d, x, y: icons.cpu_chip(d, x, y, size=20)),
    ("ram_stick", lambda d, x, y: icons.ram_stick(d, x, y, w=22, h=14)),
    ("wifi", lambda d, x, y: icons.wifi(d, x + 14, y + 14, size=13)),
    ("antenna", lambda d, x, y: icons.antenna(d, x + 14, y + 16, size=14)),
    ("wired", lambda d, x, y: icons.wired(d, x, y, size=18)),
    ("offline", lambda d, x, y: icons.offline(d, x + 14, y + 14, size=11)),
    ("exclamation", lambda d, x, y: icons.exclamation(d, x + 14, y + 20, size=11)),
    ("sun", lambda d, x, y: icons.sun(d, x + 14, y + 14, r=8)),
    ("moon", lambda d, x, y: icons.moon(d, x + 14, y + 14, r=8)),
    ("cloud", lambda d, x, y: icons.cloud(d, x + 16, y + 16, w=24, h=16)),
    ("rain", lambda d, x, y: icons.rain(d, x + 16, y + 12)),
    ("snow", lambda d, x, y: icons.snow(d, x + 16, y + 12)),
    ("fog", lambda d, x, y: icons.fog(d, x + 16, y + 14, w=26)),
    ("thunder", lambda d, x, y: icons.thunder(d, x + 16, y + 10)),
]

COLS = 4
CELL_W, CELL_H = 100, 80
ROWS = (len(ITEMS) + COLS - 1) // COLS
W, H = CELL_W * COLS, CELL_H * ROWS


def render():
    img = Image.new("1", (W, H), 255)
    draw = ImageDraw.Draw(img)
    for i, (name, fn) in enumerate(ITEMS):
        col, row = i % COLS, i // COLS
        cx, cy = col * CELL_W, row * CELL_H
        draw.rectangle((cx, cy, cx + CELL_W - 1, cy + CELL_H - 1), outline=0)
        fn(draw, cx + 10, cy + 8)
        draw.text((cx + 4, cy + CELL_H - 16), name, font=FONT, fill=0)
    return img.resize((W * 3, H * 3))


light = render()
light.save("icon_gallery.png")
print("saved icon_gallery.png")

dark = ImageOps.invert(light.convert("L")).convert("1")
dark.save("icon_gallery_dark.png")
print("saved icon_gallery_dark.png")
