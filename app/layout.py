"""Turns a list of selected metric keys into the actual PIL frame sent to the
display, and tells the GUI how many rows fit at a given font size so it can
grey out further checkboxes instead of silently clipping text.

One metric per line ("Label: value") to keep the panel dense - this is what
determines how many parameters can actually be selected. Width/height are
passed in (not hardcoded) so the same code works in portrait (80x160) or
landscape (160x80).
"""

import os

from PIL import Image, ImageDraw, ImageFont

# Portrait-orientation defaults - the worker passes its current
# width/height explicitly, these are just fallbacks for standalone use.
WIDTH, HEIGHT = 80, 160
TOP_MARGIN = 2
LINE_PADDING = 2
BG_COLOR = (15, 15, 25)
TEXT_COLOR = (230, 230, 230)
LABEL_COLOR = (120, 200, 255)

# Absolute path so this works regardless of the process's current directory.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_FONT_PATH = os.path.join(_REPO_ROOT, "res", "fonts", "roboto", "Roboto-Regular.ttf")
_FONT_CACHE = {}


def _font(size):
    if size not in _FONT_CACHE:
        _FONT_CACHE[size] = ImageFont.truetype(_FONT_PATH, size)
    return _FONT_CACHE[size]


def line_height(font_size: int) -> int:
    return font_size + LINE_PADDING


def max_rows_for_font(font_size: int, height: int = HEIGHT) -> int:
    """How many "Label: value" lines fit vertically at this font size and
    panel height (height differs between portrait and landscape)."""
    return max((height - TOP_MARGIN) // line_height(font_size), 0)


def render_dashboard(rows, font_size: int = 12, width: int = WIDTH, height: int = HEIGHT) -> Image.Image:
    """rows: ordered list of (label, value) string pairs. Anything beyond
    what fits at this font size/height is silently dropped here too, as a
    backstop - the GUI is responsible for not letting the user select more
    than max_rows_for_font(font_size, height) in the first place."""
    img = Image.new("RGB", (width, height), BG_COLOR)
    draw = ImageDraw.Draw(img)
    font = _font(font_size)
    lh = line_height(font_size)

    y = TOP_MARGIN
    for label, value in rows:
        if y + lh > height:
            break
        draw.text((3, y), f"{label}:", font=font, fill=LABEL_COLOR)
        text_w = draw.textlength(f"{label}: ", font=font)
        draw.text((3 + text_w, y), value, font=font, fill=TEXT_COLOR)
        y += lh
    return img
