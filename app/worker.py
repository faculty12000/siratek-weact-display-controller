"""Owns the single serial connection to the display. One dedicated thread
renders whatever the current state is (dashboard / media / alert overlay) and
pushes each frame to the panel - this is the only thread that calls
lcd.DisplayPILImage, so there's no need for the upstream project's
update_queue/multi-writer-thread machinery.

The GUI thread only ever pushes commands into `command_queue` and reads the
latest rendered frame from `preview_queue` for its live mirror - it never
touches the serial connection directly.
"""

import queue
import threading
import time

from library.lcd.lcd_comm import Orientation
from library.lcd.lcd_comm_weact_b import LcdCommWeActB

from app import layout, media
from app.sensors import METRICS, SensorReader

DASHBOARD_INTERVAL = 1.0  # seconds between dashboard re-renders

ORIENTATIONS = {
    "portrait": Orientation.PORTRAIT,
    "landscape": Orientation.LANDSCAPE,
    "reverse_portrait": Orientation.REVERSE_PORTRAIT,
    "reverse_landscape": Orientation.REVERSE_LANDSCAPE,
}
# Rotation cycle order (0, 90, 180, 270 degrees) - "Rotate" steps through all
# four so whichever direction matches how the device is physically mounted
# can be found, rather than guessing which of "landscape"/"reverse landscape"
# is correct for a given setup.
ORIENTATION_SEQUENCE = ["portrait", "landscape", "reverse_portrait", "reverse_landscape"]


class DisplayWorker(threading.Thread):
    def __init__(self, com_port: str):
        super().__init__(daemon=True)
        self.com_port = com_port
        self.command_queue: queue.Queue = queue.Queue()
        self.preview_queue: queue.Queue = queue.Queue(maxsize=1)
        self.status = {
            "connected": False, "error": None, "fps": 0.0, "mode": "dashboard",
            "media_kind": None,  # None | "image" | "slideshow" | "video"
            "width": 80, "height": 160, "orientation": "portrait",
            "video_position": 0.0, "video_paused": False,
            "slideshow_index": 0, "slideshow_total": 0, "slideshow_paused": False,
        }
        self._stop = threading.Event()

        self.metric_keys = ["cpu_percent", "ram_percent", "net_down", "net_up", "datetime"]
        self.font_size = 12
        self.sensor_reader = SensorReader(enable_external=False)
        self.mode = "dashboard"
        self.width, self.height = 80, 160
        self.media_player = None  # ImagePlayer | SlideshowPlayer | VideoPlayer | None
        self.alert_image = None
        self.alert_expire = 0.0
        self.lcd = None

    # -- public API, called from the GUI thread -------------------------------
    def send(self, *command):
        self.command_queue.put(command)

    def stop(self):
        self._stop.set()

    def latest_preview(self):
        """Non-blocking: returns the most recent frame, or None."""
        frame = None
        try:
            while True:
                frame = self.preview_queue.get_nowait()
        except queue.Empty:
            pass
        return frame

    # -- thread body ------------------------------------------------------------
    def run(self):
        try:
            self.lcd = LcdCommWeActB(com_port=self.com_port, display_width=80, display_height=160)
            self.lcd.Reset()
            self.lcd.InitializeComm()
            self.lcd.SetOrientation(orientation=Orientation.PORTRAIT)
            self.lcd.SetBrightness(level=40)
            self.status["connected"] = True
        except Exception as e:
            self.status["error"] = str(e)
            return

        last_dashboard_render = 0.0
        while not self._stop.is_set():
            self._drain_commands()

            now = time.time()
            frame = None

            try:
                if self.alert_image is not None and now < self.alert_expire:
                    frame = self.alert_image
                else:
                    if self.alert_image is not None:
                        self.alert_image = None  # alert just expired, fall through to normal view

                    if self.mode == "media" and self.media_player is not None:
                        frame = self.media_player.poll(self.width, self.height)
                        self._update_media_status()
                    elif self.mode == "dashboard":
                        if now - last_dashboard_render >= DASHBOARD_INTERVAL:
                            frame = self._render_dashboard()
                            last_dashboard_render = now
            except Exception as e:
                # Same reasoning as _drain_commands: a single bad frame (e.g.
                # a corrupt video frame) must not kill this thread - drop the
                # media that caused it and fall back to the dashboard rather
                # than leaving the display frozen with no way back.
                self.status["error"] = f"render failed, reverted to dashboard: {e}"
                self._set_media(None)
                self.mode = "dashboard"
                self.status["mode"] = "dashboard"

            if frame is not None:
                self._push_frame(frame)
            else:
                time.sleep(0.05)

        if self.media_player:
            self.media_player.release()
        try:
            self.lcd.closeSerial()
        except Exception:
            pass

    # -- internals ----------------------------------------------------------------
    def _drain_commands(self):
        while True:
            try:
                cmd = self.command_queue.get_nowait()
            except queue.Empty:
                return
            try:
                self._apply(cmd)
            except Exception as e:
                # A single bad command (e.g. an unreadable video file) must
                # never kill this thread - that would freeze the display on
                # whatever was last shown with no way back, since nothing
                # would be left to process a later "stop" command either.
                self.status["error"] = f"{cmd[0]} failed: {e}"

    def _apply(self, cmd):
        name, *args = cmd
        if name == "set_metrics":
            self.metric_keys = args[0]
        elif name == "set_font_size":
            self.font_size = args[0]
        elif name == "set_external":
            self.sensor_reader.enable_external = args[0]
        elif name == "set_disk_path":
            self.sensor_reader.disk_path = args[0]
        elif name == "set_brightness":
            try:
                self.lcd.SetBrightness(level=args[0])
            except Exception:
                pass
        elif name == "set_orientation":
            self._set_orientation(args[0])
        elif name == "rotate":
            current_index = ORIENTATION_SEQUENCE.index(self.status["orientation"])
            next_name = ORIENTATION_SEQUENCE[(current_index + 1) % len(ORIENTATION_SEQUENCE)]
            self._set_orientation(next_name)
        elif name == "play_image":
            self._set_media(media.ImagePlayer(args[0]))
        elif name == "play_slideshow":
            interval = args[1] if len(args) > 1 else 3.0
            self._set_media(media.SlideshowPlayer(args[0], interval_s=interval))
        elif name == "play_video":
            loop = args[1] if len(args) > 1 else True
            self._set_media(media.VideoPlayer(args[0], loop=loop))
        elif name == "play_text":
            text, font_size, scroll_speed, color, bg = args
            self._set_media(media.TextPlayer(text, font_size=font_size, scroll_px_per_sec=scroll_speed,
                                              color=tuple(color), bg=tuple(bg)))
        elif name == "set_text_font_size":
            if self.media_player and self.media_player.kind == "text":
                self.media_player.set_font_size(args[0])
        elif name == "set_text_scroll_speed":
            if self.media_player and self.media_player.kind == "text":
                self.media_player.set_scroll_speed(args[0])
        elif name == "stop_media":
            self._set_media(None)
            self.mode = "dashboard"
            self.status["mode"] = "dashboard"
        elif name == "video_play_pause":
            if self.media_player and self.media_player.kind == "video":
                self.media_player.toggle_pause()
        elif name == "video_seek":
            if self.media_player and self.media_player.kind == "video":
                self.media_player.seek_fraction(args[0])
        elif name == "slideshow_next":
            if self.media_player and self.media_player.kind == "slideshow":
                self.media_player.next()
        elif name == "slideshow_prev":
            if self.media_player and self.media_player.kind == "slideshow":
                self.media_player.previous()
        elif name == "slideshow_pause":
            if self.media_player and self.media_player.kind == "slideshow":
                self.media_player.toggle_pause()
        elif name == "alert":
            text, duration, color = args
            from app import alerts
            self.alert_image = alerts.render_alert(text, width=self.width, height=self.height, bg=tuple(color))
            self.alert_expire = time.time() + duration

    def _set_orientation(self, name: str):
        orientation = ORIENTATIONS.get(name, Orientation.PORTRAIT)
        self.lcd.SetOrientation(orientation=orientation)
        self.width, self.height = self.lcd.get_width(), self.lcd.get_height()
        self.status["width"], self.status["height"] = self.width, self.height
        self.status["orientation"] = name
        if self.media_player is not None:
            self.media_player.refresh()  # re-letterbox whatever's on screen to the new dimensions

    def _set_media(self, player):
        if self.media_player:
            self.media_player.release()
        self.media_player = player
        self.status["media_kind"] = player.kind if player else None
        if player is not None:
            self.mode = "media"
            self.status["mode"] = "media"
            self.status["fps"] = 0.0

    def _update_media_status(self):
        p = self.media_player
        if p is None:
            return
        if p.kind == "video":
            self.status["video_position"] = p.position_fraction
            self.status["video_paused"] = p.paused
        elif p.kind == "slideshow":
            self.status["slideshow_index"] = p.index
            self.status["slideshow_total"] = p.total
            self.status["slideshow_paused"] = p.paused

    def _render_dashboard(self):
        rows = []
        max_rows = layout.max_rows_for_font(self.font_size, height=self.height)
        for key in self.metric_keys[:max_rows]:
            label = METRICS.get(key, (key, False, False, ""))[0]
            value = self.sensor_reader.read(key)
            rows.append((label, value))
        return layout.render_dashboard(rows, font_size=self.font_size, width=self.width, height=self.height)

    def _push_frame(self, frame):
        try:
            self.lcd.DisplayPILImage(frame)
        except Exception as e:
            self.status["error"] = str(e)
        try:
            self.preview_queue.put_nowait(frame)
        except queue.Full:
            pass
