"""Generates a colorful 80x160 test image to prove out image rendering
(gradient + shapes + text baked into the bitmap), not just the library's
live-drawn text/progress-bar primitives."""

from PIL import Image, ImageDraw, ImageFont

W, H = 80, 160
img = Image.new("RGB", (W, H))
draw = ImageDraw.Draw(img)

# Vertical gradient background (purple -> teal)
for y in range(H):
    t = y / (H - 1)
    r = int(80 + (20 - 80) * t)
    g = int(20 + (180 - 20) * t)
    b = int(120 + (160 - 120) * t)
    draw.line([(0, y), (W, y)], fill=(r, g, b))

# A few shapes to show solid-color rendering
draw.ellipse([10, 10, 70, 70], fill=(255, 200, 0), outline=(255, 255, 255), width=2)
draw.rectangle([15, 85, 65, 110], fill=(255, 60, 60), outline=(255, 255, 255), width=2)

font = ImageFont.truetype("res/fonts/roboto/Roboto-Bold.ttf", 13)
draw.text((8, 125), "IMAGE", font=font, fill=(255, 255, 255))
draw.text((8, 140), "TEST", font=font, fill=(255, 255, 255))

img.save("test_image.png")
print("wrote test_image.png (80x160)")
