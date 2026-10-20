"""Alert overlay rendering, plus an optional localhost-only HTTP trigger so
other local scripts/automations can push an alert without a GUI click.

The HTTP server is bound to 127.0.0.1 only - it is never reachable from the
network, only from this same machine.
"""

import json
import os
import textwrap
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 80, 160
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ALERT_FONT_PATH = os.path.join(_REPO_ROOT, "res", "fonts", "roboto", "Roboto-Bold.ttf")


def render_alert(text: str, width: int = WIDTH, height: int = HEIGHT, color=(255, 255, 255),
                  bg=(180, 20, 20), font_size=14) -> Image.Image:
    img = Image.new("RGB", (width, height), bg)
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype(_ALERT_FONT_PATH, font_size)

    # Wrap to fit the panel width (rough char-width estimate for this font/size)
    chars_per_line = max(width // (font_size // 2 + 1), 4)
    wrapped = textwrap.fill(text, width=chars_per_line)

    bbox = draw.multiline_textbbox((0, 0), wrapped, font=font, spacing=4)
    text_h = bbox[3] - bbox[1]
    y = max((height - text_h) // 2, 4)
    draw.multiline_text((4, y), wrapped, font=font, fill=color, spacing=4, align="center")
    return img


class _AlertHTTPHandler(BaseHTTPRequestHandler):
    alert_callback = None  # set by start_local_alert_server; signature: (text, duration, color)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else b"{}"
        try:
            data = json.loads(body)
            text = str(data.get("text", ""))[:200]
            duration = float(data.get("duration", 5))
            color = tuple(data.get("color", (255, 0, 0)))
            if self.alert_callback and text:
                self.alert_callback(text, duration, color)
            self.send_response(200)
        except Exception:
            self.send_response(400)
        self.end_headers()

    def log_message(self, *args):
        pass  # keep stdout quiet


def start_local_alert_server(on_alert, port=8765) -> HTTPServer:
    """on_alert(text, duration, color) is called for every valid POST.
    Returns the running HTTPServer (call .shutdown() to stop it)."""
    _AlertHTTPHandler.alert_callback = on_alert
    server = HTTPServer(("127.0.0.1", port), _AlertHTTPHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server
