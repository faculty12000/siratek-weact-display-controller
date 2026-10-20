"""Tkinter GUI: Dashboard (parameter checkboxes + live preview), Media
(image/slideshow/video), Alerts tabs, plus a status bar. The GUI thread never
touches the serial connection - it only sends commands to a DisplayWorker and
mirrors whatever frame the worker most recently rendered.
"""

import tkinter as tk
from tkinter import colorchooser, filedialog, messagebox, ttk
from typing import Optional

import sv_ttk
from PIL import Image, ImageTk

from app import alerts, driver_check, layout
from app.sensors import METRICS
from app.worker import DisplayWorker

PREVIEW_SCALE = 3
FONT_SIZE_OPTIONS = {"Small (more rows)": 10, "Medium": 12, "Large": 16}


class WeActApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title('Siratek Technologies WeAct 0.96" Display Controller')
        self.root.resizable(False, False)
        sv_ttk.use_dark_theme()

        self.worker: Optional[DisplayWorker] = None
        self.metric_vars = {}
        self.metric_checkbuttons = {}
        self.alert_color = (200, 30, 30)
        self.alert_server = None
        self.current_height = 160  # tracks orientation (160=portrait, 80=landscape) for slot capping
        self.orientation_name = "portrait"
        self._seeking = False  # True while the user is dragging the video seek slider

        self._build_layout()
        self._connect()
        self.root.after(100, self._tick)

    # -- connection -------------------------------------------------------------
    def _connect(self):
        port = driver_check.find_device_port()
        if port is None:
            self.status_var.set("Device not found.")
            message, url = driver_check.driver_guidance()
            if url is not None:
                if messagebox.askyesno("Display not found", "No WeAct display was detected.\n\n" + message):
                    driver_check.open_driver_download_page(url)
            else:
                messagebox.showinfo("Display not found", "No WeAct display was detected.\n\n" + message)
            return
        self.worker = DisplayWorker(port)
        self.worker.start()
        self.worker.send("set_metrics", self._selected_metric_keys())
        self.status_var.set(f"Connecting on {port} ...")

    # -- layout -------------------------------------------------------------------
    def _build_layout(self):
        container = ttk.Frame(self.root, padding=10)
        container.grid(row=0, column=0, sticky="nsew")

        # Live preview (left)
        preview_frame = ttk.LabelFrame(container, text="Live preview", padding=8)
        preview_frame.grid(row=0, column=0, rowspan=2, padx=(0, 10), sticky="n")
        self.preview_label = ttk.Label(preview_frame)
        self.preview_label.pack()

        orientation_frame = ttk.Frame(preview_frame)
        orientation_frame.pack(pady=(8, 0), fill="x")
        ttk.Button(orientation_frame, text="⟳ Rotate", command=self._on_rotate).pack(side="left")
        self.orientation_label_var = tk.StringVar(value="Portrait")
        ttk.Label(orientation_frame, textvariable=self.orientation_label_var).pack(side="left", padx=(8, 0))

        # Tabs (right)
        notebook = ttk.Notebook(container)
        notebook.grid(row=0, column=1, sticky="nsew")
        self._build_dashboard_tab(notebook)
        self._build_media_tab(notebook)
        self._build_text_tab(notebook)
        self._build_alerts_tab(notebook)

        # Status bar
        self.status_var = tk.StringVar(value="Starting...")
        status_bar = ttk.Label(self.root, textvariable=self.status_var, anchor="w", padding=(10, 4))
        status_bar.grid(row=1, column=0, sticky="ew")

    def _build_dashboard_tab(self, notebook):
        tab = ttk.Frame(notebook, padding=10)
        notebook.add(tab, text="Dashboard")

        ttk.Label(tab, text="Font size:").grid(row=0, column=0, sticky="w")
        self.font_choice = tk.StringVar(value="Medium")
        font_menu = ttk.Combobox(tab, textvariable=self.font_choice, values=list(FONT_SIZE_OPTIONS), state="readonly", width=18)
        font_menu.grid(row=0, column=1, sticky="w", pady=4)
        font_menu.bind("<<ComboboxSelected>>", lambda e: self._on_font_changed())

        self.slots_var = tk.StringVar()
        ttk.Label(tab, textvariable=self.slots_var).grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 6))

        checks_frame = ttk.Frame(tab)
        checks_frame.grid(row=2, column=0, columnspan=2, sticky="w")
        for i, (key, (label, external, admin_note, unit)) in enumerate(METRICS.items()):
            var = tk.BooleanVar(value=key in {"cpu_percent", "ram_percent", "net_down", "net_up", "datetime"})
            self.metric_vars[key] = var
            text = label + (" *ext*" if external else "")
            cb = ttk.Checkbutton(checks_frame, text=text, variable=var, command=self._on_metrics_changed)
            cb.grid(row=i // 2, column=i % 2, sticky="w", padx=4, pady=2)
            self.metric_checkbuttons[key] = cb

        ttk.Label(tab, text="* ext * = makes an outbound network call", foreground="#999").grid(
            row=3, column=0, columnspan=2, sticky="w", pady=(6, 0)
        )

        self.external_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            tab, text="Enable external lookups (Public IP / Location)", variable=self.external_var,
            command=self._on_external_toggled,
        ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(10, 0))

        ttk.Label(tab, text="Brightness:").grid(row=5, column=0, sticky="w", pady=(10, 0))
        self.brightness_var = tk.IntVar(value=40)
        brightness_scale = ttk.Scale(tab, from_=0, to=100, variable=self.brightness_var, command=self._on_brightness_changed)
        brightness_scale.grid(row=5, column=1, sticky="we", pady=(10, 0))

        self._refresh_slot_count()

    def _build_media_tab(self, notebook):
        tab = ttk.Frame(notebook, padding=10)
        notebook.add(tab, text="Image / Video")

        ttk.Button(tab, text="Show an image...", command=self._pick_image).pack(fill="x", pady=4)
        ttk.Button(tab, text="Slideshow from a folder...", command=self._pick_slideshow).pack(fill="x", pady=4)
        ttk.Button(tab, text="Play a video...", command=self._pick_video).pack(fill="x", pady=4)
        self.loop_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(tab, text="Loop video", variable=self.loop_var).pack(anchor="w", pady=4)
        ttk.Button(tab, text="Stop - back to Dashboard", command=self._stop_media).pack(fill="x", pady=(10, 4))

        playback = ttk.LabelFrame(tab, text="Playback controls", padding=8)
        playback.pack(fill="x", pady=(10, 4))

        buttons = ttk.Frame(playback)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="⏮ Prev", command=self._slideshow_prev).pack(side="left", expand=True, fill="x")
        ttk.Button(buttons, text="⏯ Play/Pause", command=self._toggle_play_pause).pack(side="left", expand=True, fill="x")
        ttk.Button(buttons, text="Next ⏭", command=self._slideshow_next).pack(side="left", expand=True, fill="x")
        ttk.Label(
            playback, text="Prev/Next control a slideshow; Play/Pause works for both a slideshow and a video.",
            foreground="#999", wraplength=260,
        ).pack(anchor="w", pady=(4, 0))

        ttk.Label(playback, text="Video position:").pack(anchor="w", pady=(8, 0))
        self.seek_var = tk.DoubleVar(value=0.0)
        self.seek_scale = ttk.Scale(playback, from_=0, to=100, variable=self.seek_var, orient="horizontal")
        self.seek_scale.pack(fill="x")
        self.seek_scale.bind("<ButtonPress-1>", lambda e: setattr(self, "_seeking", True))
        self.seek_scale.bind("<ButtonRelease-1>", self._on_seek_release)

        self.fps_var = tk.StringVar(value="")
        ttk.Label(tab, textvariable=self.fps_var, foreground="#999").pack(anchor="w", pady=(10, 0))

    def _build_text_tab(self, notebook):
        tab = ttk.Frame(notebook, padding=10)
        notebook.add(tab, text="Text")

        ttk.Label(tab, text="Text to display:").pack(anchor="w")
        self.text_input = tk.Text(tab, height=4, width=30, wrap="word")
        self.text_input.pack(fill="x", pady=(2, 8))

        ttk.Label(tab, text="Font size:").pack(anchor="w")
        self.text_font_size_var = tk.IntVar(value=20)
        text_font_scale = ttk.Scale(
            tab, from_=8, to=48, variable=self.text_font_size_var, orient="horizontal",
        )
        text_font_scale.pack(fill="x")
        text_font_scale.bind("<ButtonRelease-1>", self._on_text_font_size_changed)

        ttk.Label(tab, text="Scroll speed (px/s) - 0 = don't scroll:").pack(anchor="w", pady=(8, 0))
        self.text_scroll_var = tk.IntVar(value=40)
        ttk.Scale(
            tab, from_=0, to=150, variable=self.text_scroll_var, orient="horizontal",
            command=self._on_text_scroll_speed_changed,
        ).pack(fill="x")
        ttk.Label(
            tab, text="Only applies when the text is wider than the screen - size and speed can be "
                      "tweaked live while the text is showing.",
            foreground="#999", wraplength=260,
        ).pack(anchor="w", pady=(2, 8))

        self.text_color = (255, 255, 255)
        self.text_bg_color = (10, 10, 15)
        color_row = ttk.Frame(tab)
        color_row.pack(fill="x", pady=(4, 0))
        self.text_color_preview = tk.Canvas(color_row, width=18, height=18, bg="#%02x%02x%02x" % self.text_color, highlightthickness=1)
        self.text_color_preview.pack(side="left")
        ttk.Button(color_row, text="Text color...", command=self._pick_text_color).pack(side="left", padx=(4, 10))
        self.text_bg_preview = tk.Canvas(color_row, width=18, height=18, bg="#%02x%02x%02x" % self.text_bg_color, highlightthickness=1)
        self.text_bg_preview.pack(side="left")
        ttk.Button(color_row, text="Background...", command=self._pick_text_bg_color).pack(side="left", padx=(4, 0))

        ttk.Button(tab, text="Display Text", command=self._show_text).pack(fill="x", pady=(10, 4))
        ttk.Button(tab, text="Stop - back to Dashboard", command=self._stop_media).pack(fill="x", pady=4)

    def _build_alerts_tab(self, notebook):
        tab = ttk.Frame(notebook, padding=10)
        notebook.add(tab, text="Alerts")

        ttk.Label(tab, text="Message:").grid(row=0, column=0, sticky="w")
        self.alert_text = tk.StringVar()
        ttk.Entry(tab, textvariable=self.alert_text, width=30).grid(row=0, column=1, pady=4)

        ttk.Label(tab, text="Duration (s):").grid(row=1, column=0, sticky="w")
        self.alert_duration = tk.IntVar(value=5)
        ttk.Spinbox(tab, from_=1, to=60, textvariable=self.alert_duration, width=6).grid(row=1, column=1, sticky="w", pady=4)

        self.color_preview = tk.Canvas(tab, width=20, height=20, bg="#%02x%02x%02x" % self.alert_color, highlightthickness=1)
        self.color_preview.grid(row=2, column=0, sticky="w")
        ttk.Button(tab, text="Pick color...", command=self._pick_alert_color).grid(row=2, column=1, sticky="w", pady=4)

        ttk.Button(tab, text="Send Alert", command=self._send_alert).grid(row=3, column=0, columnspan=2, sticky="we", pady=(10, 4))

        self.alert_server_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            tab, text="Enable local alert trigger (127.0.0.1:8765 only)", variable=self.alert_server_var,
            command=self._toggle_alert_server,
        ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(10, 0))
        ttk.Label(
            tab,
            text='curl -X POST http://127.0.0.1:8765 -d \'{"text":"hi","duration":5,"color":[200,30,30]}\'',
            foreground="#999", wraplength=320,
        ).grid(row=5, column=0, columnspan=2, sticky="w")

    # -- event handlers -----------------------------------------------------------
    def _selected_metric_keys(self):
        return [k for k, v in self.metric_vars.items() if v.get()]

    def _on_metrics_changed(self):
        self._refresh_slot_count()
        if self.worker:
            self.worker.send("set_metrics", self._selected_metric_keys())

    ORIENTATION_LABELS = {
        "portrait": "Portrait", "landscape": "Landscape",
        "reverse_portrait": "Portrait (upside-down)", "reverse_landscape": "Landscape (flipped)",
    }
    ORIENTATION_CYCLE = ["portrait", "landscape", "reverse_portrait", "reverse_landscape"]

    def _on_rotate(self):
        if self.worker:
            self.worker.send("rotate")
        # Mirror the worker's own rotation order so the label/cap update
        # immediately rather than waiting a tick for worker.status to catch up.
        idx = self.ORIENTATION_CYCLE.index(self.orientation_name)
        self.orientation_name = self.ORIENTATION_CYCLE[(idx + 1) % len(self.ORIENTATION_CYCLE)]
        self.orientation_label_var.set(self.ORIENTATION_LABELS[self.orientation_name])
        self.current_height = 80 if "landscape" in self.orientation_name else 160
        self._refresh_slot_count()

    def _refresh_slot_count(self):
        font_size = FONT_SIZE_OPTIONS[self.font_choice.get()]
        max_rows = layout.max_rows_for_font(font_size, height=self.current_height)
        selected = self._selected_metric_keys()
        self.slots_var.set(f"{len(selected)}/{max_rows} slots used at this font size")

        # At the cap: grey out every unticked box so the user can't select
        # more than will actually fit. Ticked boxes stay enabled so they can
        # still be unticked to free up a slot.
        at_cap = len(selected) >= max_rows
        for key, var in self.metric_vars.items():
            cb = self.metric_checkbuttons[key]
            if var.get():
                cb.state(["!disabled"])
            else:
                cb.state(["disabled"] if at_cap else ["!disabled"])

    def _on_font_changed(self):
        font_size = FONT_SIZE_OPTIONS[self.font_choice.get()]
        self._refresh_slot_count()
        if self.worker:
            self.worker.send("set_font_size", font_size)

    def _on_external_toggled(self):
        if self.worker:
            self.worker.send("set_external", self.external_var.get())

    def _on_brightness_changed(self, _value):
        if self.worker:
            self.worker.send("set_brightness", int(self.brightness_var.get()))

    def _pick_image(self):
        path = filedialog.askopenfilename(filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp *.gif *.webp")])
        if path and self.worker:
            self.worker.send("play_image", path)

    def _pick_slideshow(self):
        folder = filedialog.askdirectory()
        if folder and self.worker:
            self.worker.send("play_slideshow", folder, 3.0)

    def _pick_video(self):
        path = filedialog.askopenfilename(filetypes=[("Videos", "*.mp4 *.avi *.mov *.mkv *.webm")])
        if path and self.worker:
            self.worker.send("play_video", path, self.loop_var.get())

    def _stop_media(self):
        if self.worker:
            self.worker.send("stop_media")
        self.fps_var.set("")

    def _toggle_play_pause(self):
        if not self.worker:
            return
        # Harmless to send both - the worker only acts on the one matching
        # whatever media kind is actually loaded.
        self.worker.send("video_play_pause")
        self.worker.send("slideshow_pause")

    def _slideshow_next(self):
        if self.worker:
            self.worker.send("slideshow_next")

    def _slideshow_prev(self):
        if self.worker:
            self.worker.send("slideshow_prev")

    def _on_seek_release(self, _event):
        if self.worker:
            self.worker.send("video_seek", self.seek_var.get() / 100.0)
        self._seeking = False

    def _show_text(self):
        if not self.worker:
            return
        text = self.text_input.get("1.0", "end").strip()
        if not text:
            return
        self.worker.send(
            "play_text", text, int(self.text_font_size_var.get()), int(self.text_scroll_var.get()),
            self.text_color, self.text_bg_color,
        )

    def _on_text_font_size_changed(self, _event):
        if self.worker:
            self.worker.send("set_text_font_size", int(self.text_font_size_var.get()))

    def _on_text_scroll_speed_changed(self, _value):
        if self.worker:
            self.worker.send("set_text_scroll_speed", int(self.text_scroll_var.get()))

    def _pick_text_color(self):
        result = colorchooser.askcolor(color="#%02x%02x%02x" % self.text_color)
        if result[0]:
            self.text_color = tuple(int(c) for c in result[0])
            self.text_color_preview.configure(bg="#%02x%02x%02x" % self.text_color)

    def _pick_text_bg_color(self):
        result = colorchooser.askcolor(color="#%02x%02x%02x" % self.text_bg_color)
        if result[0]:
            self.text_bg_color = tuple(int(c) for c in result[0])
            self.text_bg_preview.configure(bg="#%02x%02x%02x" % self.text_bg_color)

    def _pick_alert_color(self):
        result = colorchooser.askcolor(color="#%02x%02x%02x" % self.alert_color)
        if result[0]:
            self.alert_color = tuple(int(c) for c in result[0])
            self.color_preview.configure(bg="#%02x%02x%02x" % self.alert_color)

    def _send_alert(self):
        if not self.worker:
            return
        text = self.alert_text.get().strip()
        if not text:
            return
        self.worker.send("alert", text, int(self.alert_duration.get()), self.alert_color)

    def _toggle_alert_server(self):
        if self.alert_server_var.get():
            def on_alert(text, duration, color):
                if self.worker:
                    self.worker.send("alert", text, duration, color)
            self.alert_server = alerts.start_local_alert_server(on_alert)
        elif self.alert_server:
            self.alert_server.shutdown()
            self.alert_server = None

    # -- periodic refresh --------------------------------------------------------
    def _tick(self):
        if self.worker:
            frame = self.worker.latest_preview()
            if frame is not None:
                scaled = frame.resize(
                    (frame.width * PREVIEW_SCALE, frame.height * PREVIEW_SCALE),
                    resample=Image.NEAREST,  # keep the pixel-accurate look, no smoothing
                )
                self._preview_image = ImageTk.PhotoImage(scaled)  # keep a reference
                self.preview_label.configure(image=self._preview_image)

            status = self.worker.status
            if status.get("error"):
                self.status_var.set(f"Error: {status['error']}")
            elif status.get("connected"):
                fps = status.get("fps", 0.0)
                fps_text = f" | {fps:.1f} fps" if status.get("mode") == "media" and fps else ""
                self.status_var.set(f"Connected on {self.worker.com_port} | mode: {status.get('mode')}{fps_text}")

                fps_label_parts = []
                kind = status.get("media_kind")
                if kind == "video" and fps:
                    fps_label_parts.append(f"Achieved: {fps:.1f} fps (serial bandwidth, not decode, is the limit)")
                if kind == "slideshow":
                    paused = " (paused)" if status.get("slideshow_paused") else ""
                    fps_label_parts.append(f"Slide {status['slideshow_index'] + 1}/{status['slideshow_total']}{paused}")
                if kind == "video":
                    paused_text = "paused" if status.get("video_paused") else "playing"
                    fps_label_parts.append(f"Video: {paused_text}")
                self.fps_var.set(" | ".join(fps_label_parts))

                if not self._seeking:
                    self.seek_var.set(status.get("video_position", 0.0) * 100)
            else:
                self.status_var.set("Connecting...")

        self.root.after(100, self._tick)

    def on_close(self):
        if self.worker:
            self.worker.stop()
        if self.alert_server:
            self.alert_server.shutdown()
        self.root.destroy()


def main():
    root = tk.Tk()
    app = WeActApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()


if __name__ == "__main__":
    main()
