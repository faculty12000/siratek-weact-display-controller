"""Generates an original 80x160 retro-platformer-style test image: sky, clouds,
a question block, a coin, and brick ground - a more colorful/varied test of
bitmap rendering than a plain gradient. Original pixel art, not reproducing
any copyrighted character/sprite designs."""

from PIL import Image, ImageDraw

W, H = 80, 160
SKY = (92, 148, 252)
img = Image.new("RGB", (W, H), SKY)
draw = ImageDraw.Draw(img)


def pixel_block(x, y, size, color, shade=None):
    draw.rectangle([x, y, x + size - 1, y + size - 1], fill=color)
    if shade:
        draw.line([(x, y + size - 1), (x + size - 1, y + size - 1)], fill=shade)
        draw.line([(x + size - 1, y), (x + size - 1, y + size - 1)], fill=shade)


# Clouds (simple pixel-cloud clusters)
def cloud(x, y):
    for dx, dy, s in [(0, 4, 8), (6, 0, 10), (14, 4, 8), (4, 8, 16)]:
        draw.ellipse([x + dx, y + dy, x + dx + s, y + dy + s], fill=(255, 255, 255))


cloud(4, 14)
cloud(40, 30)

# Question block
qb = 20
qb_x, qb_y = 30, 60
pixel_block(qb_x, qb_y, qb, (252, 188, 48), shade=(160, 110, 20))
draw.rectangle([qb_x + 6, qb_y + 3, qb_x + 13, qb_y + 16], outline=(80, 50, 10), width=2)

# Coin (floating above)
cx, cy, cr = 55, 55, 7
draw.ellipse([cx - cr, cy - cr, cx + cr, cy + cr], fill=(255, 221, 51), outline=(150, 110, 0))

# Ground: two rows of brick blocks across the bottom
brick = 16
ground_y = H - brick * 2
for row in range(2):
    for col in range(W // brick + 1):
        shade = (120, 60, 20) if (row + col) % 2 == 0 else (150, 80, 30)
        pixel_block(col * brick, ground_y + row * brick, brick, (200, 100, 40), shade=shade)

img.save("test_platformer.png")
print("wrote test_platformer.png (80x160)")
