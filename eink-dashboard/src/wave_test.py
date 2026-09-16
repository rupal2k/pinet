"""Standalone test of the great_wave watermark motif at header scale."""
from PIL import Image, ImageDraw

import icons

W, H = 250, 26
img = Image.new("1", (W, H), 255)
draw = ImageDraw.Draw(img)
draw.rectangle((0, 0, W - 1, H - 1), outline=0)
icons.seigaiha(draw, 2, 1, 170, H - 2, rings=2, rows=1)

img = img.resize((W * 4, H * 4))
img.save("wave_test.png")
print("saved wave_test.png")
