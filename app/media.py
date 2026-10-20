"""Image / slideshow / video players. Each exposes an explicit, pollable
"give me a frame if there's a new one" interface (not a plain generator) -
that's deliberate: a plain generator that yields once (a static image) or
ends (a non-looping video) used to be mistaken by the worker for "done,
go back to the dashboard", which made images vanish immediately after being
shown. These players instead hold their state until the GUI explicitly stops
or replaces them, and support pause/seek/next/prev.
"""

import os
import time

import cv2
from PIL import Image, ImageDraw, ImageFont

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp"}

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_TEXT_FONT_PATH = os.path.join(_REPO_ROOT, "res", "fonts", "roboto", "Roboto-Bold.ttf")


def _letterbox(pil_image: Image.Image, width: int, height: int) -> Image.Image:
    """Resize to fit within width x height preserving aspect ratio, pad the rest black."""
    img = pil_image.convert("RGB")
    img.thumbnail((width, height), Image.LANCZOS)
    canvas = Image.new("RGB", (width, height), (0, 0, 0))
    x = (width - img.width) // 2
    y = (height - img.height) // 2
    canvas.paste(img, (x, y))
    return canvas


class ImagePlayer:
    """A single static image. Stays on screen until replaced/stopped - the
    worker only needs to push it once."""

    kind = "image"

    def __init__(self, path):
        self.path = path
        self._pushed = False

    def poll(self, width, height):
        """Returns a frame only the first time it's called (nothing changes
        after that, so there's nothing new to push) - until refresh() is
        called, e.g. when the orientation changes and the image needs to be
        re-letterboxed to the new dimensions."""
        if self._pushed:
            return None
        self._pushed = True
        return _letterbox(Image.open(self.path), width, height)

    def refresh(self):
        self._pushed = False

    def release(self):
        pass


class SlideshowPlayer:
    """Cycles through every image in a folder. Supports pause/next/previous;
    only returns a frame from poll() when the shown image actually changed."""

    kind = "slideshow"

    def __init__(self, folder, interval_s=3.0):
        self.paths = sorted(
            os.path.join(folder, f)
            for f in os.listdir(folder)
            if os.path.splitext(f)[1].lower() in IMAGE_EXTENSIONS
        )
        self.interval_s = interval_s
        self.index = 0
        self.paused = False
        self._last_advance = time.time()
        self._last_shown_index = -1

    def refresh(self):
        self._last_shown_index = -1

    @property
    def total(self):
        return len(self.paths)

    def next(self):
        if self.paths:
            self.index = (self.index + 1) % len(self.paths)
            self._last_advance = time.time()

    def previous(self):
        if self.paths:
            self.index = (self.index - 1) % len(self.paths)
            self._last_advance = time.time()

    def toggle_pause(self):
        self.paused = not self.paused
        self._last_advance = time.time()

    def poll(self, width, height):
        if not self.paths:
            return None
        if not self.paused and time.time() - self._last_advance >= self.interval_s:
            self.next()
        if self.index == self._last_shown_index:
            return None
        self._last_shown_index = self.index
        return _letterbox(Image.open(self.paths[self.index]), width, height)

    def release(self):
        pass


class VideoPlayer:
    """Decodes a video file on demand. Supports pause and seek (by fraction
    0.0-1.0). The serial link's bandwidth, not decode speed, is the real
    frame-rate limiter - the worker measures and reports actual achieved fps
    rather than assuming the source video's fps."""

    kind = "video"

    def __init__(self, path, loop=True):
        self.cap = cv2.VideoCapture(path)
        if not self.cap.isOpened():
            raise ValueError(f"Could not open video: {path}")
        self.loop = loop
        self.paused = False
        self.ended = False
        self.total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0

    @property
    def position_fraction(self) -> float:
        if not self.total_frames:
            return 0.0
        return min(self.cap.get(cv2.CAP_PROP_POS_FRAMES) / self.total_frames, 1.0)

    def seek_fraction(self, fraction: float):
        fraction = max(0.0, min(1.0, fraction))
        target = int(fraction * max(self.total_frames - 1, 0))
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, target)
        self.ended = False

    def toggle_pause(self):
        self.paused = not self.paused

    def refresh(self):
        pass  # next poll() naturally re-letterboxes to the current width/height

    def poll(self, width, height):
        """Returns the next decoded frame, or None if paused / nothing new
        (a non-looping video that reached its end stays on its last frame)."""
        if self.paused or self.ended:
            return None
        ok, frame = self.cap.read()
        if not ok:
            if self.loop:
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ok, frame = self.cap.read()
                if not ok:
                    self.ended = True
                    return None
            else:
                self.ended = True
                return None
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        return _letterbox(Image.fromarray(rgb), width, height)

    def release(self):
        self.cap.release()


def _build_text_image(text, font, color):
    """Renders text to an image sized exactly to its own pixel footprint, so
    the caller can tell whether it fits the panel or needs to scroll."""
    probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    bbox = probe.textbbox((0, 0), text, font=font)
    w, h = max(bbox[2] - bbox[0], 1), max(bbox[3] - bbox[1], 1)
    img = Image.new("RGB", (w, h), (0, 0, 0))
    ImageDraw.Draw(img).text((-bbox[0], -bbox[1]), text, font=font, fill=color)
    return img, w, h


class TextPlayer:
    """Displays typed text: centered and static if it fits the panel width,
    or scrolling horizontally (marquee-style, looping with a blank gap) if
    it doesn't. Font size and scroll speed can be changed live without
    reloading the text."""

    kind = "text"

    def __init__(self, text, font_size=20, scroll_px_per_sec=40,
                 color=(255, 255, 255), bg=(10, 10, 15)):
        self.text = text or " "
        self.font_size = font_size
        self.scroll_speed = max(scroll_px_per_sec, 0)
        self.color = color
        self.bg = bg
        self._text_img = None
        self._text_w = 0
        self._text_h = 0
        self._start_time = time.time()
        self._static_pushed = False
        self._built_font_size = None

    def set_font_size(self, font_size):
        self.font_size = font_size
        self._built_font_size = None  # forces a rebuild on the next poll

    def set_scroll_speed(self, px_per_sec):
        self.scroll_speed = max(px_per_sec, 0)
        self._start_time = time.time()  # restart the scroll cleanly at the new speed

    def refresh(self):
        self._built_font_size = None  # e.g. orientation changed - rebuild for the new canvas

    def _ensure_built(self):
        if self._built_font_size == self.font_size:
            return
        font = ImageFont.truetype(_TEXT_FONT_PATH, self.font_size)
        self._text_img, self._text_w, self._text_h = _build_text_image(self.text, font, self.color)
        self._built_font_size = self.font_size
        self._start_time = time.time()
        self._static_pushed = False

    def poll(self, width, height):
        self._ensure_built()
        y = max((height - self._text_h) // 2, 0)

        if self._text_w <= width:
            if self._static_pushed:
                return None
            self._static_pushed = True
            canvas = Image.new("RGB", (width, height), self.bg)
            canvas.paste(self._text_img, ((width - self._text_w) // 2, y))
            return canvas

        if self.scroll_speed == 0:
            if self._static_pushed:
                return None
            self._static_pushed = True
            canvas = Image.new("RGB", (width, height), self.bg)
            canvas.paste(self._text_img, (0, y))  # frozen at the start, clipped
            return canvas

        gap = width  # blank gap before the text repeats
        loop_width = self._text_w + gap
        elapsed = time.time() - self._start_time
        offset = int((elapsed * self.scroll_speed) % loop_width)

        canvas = Image.new("RGB", (width, height), self.bg)
        canvas.paste(self._text_img, (-offset, y))
        canvas.paste(self._text_img, (loop_width - offset, y))  # covers the wraparound seam
        return canvas

    def release(self):
        pass
