# Siratek Technologies WeAct 0.96" Display Controller

A standalone GUI app, plus the lower-level scripts it's built on, for driving
a **WeAct Studio Display FS V1 0.96"** (160×80 RGB565 panel, USB-attached as a
CDC/virtual serial port via a WCH chip). Works on **Windows, Linux, and
macOS** - the app itself is pure Python/Tkinter with no OS-specific code path.

## Download and run

Requires [Python 3.10+](https://www.python.org/downloads/) (the Linux/macOS
notes below cover a couple of platform-specific extras).

```bash
git clone https://github.com/faculty12000/siratek-weact-display-controller.git
cd siratek-weact-display-controller
```

**Windows:** double-click `run_app.bat`, or from a terminal:
```powershell
run_app.bat
```

**Linux / macOS:**
```bash
chmod +x run_app.sh   # only needed if the executable bit didn't survive your download method
./run_app.sh
```

Either launcher sets up a `.venv` and installs dependencies automatically on
first run, then just launches on every run after that.

### Linux / macOS platform notes

- **Linux:** Tkinter usually isn't installed by default with system Python -
  install it first: `sudo apt install python3-tk` (Debian/Ubuntu),
  `sudo dnf install python3-tkinter` (Fedora), or the equivalent for your
  distro. No display driver is normally needed (see Driver handling below);
  if the device isn't detected, it's almost always a permissions issue, not
  a missing driver - the app's "device not found" dialog explains the fix.
- **macOS:** the python.org installer bundles Tk already. If you're using
  Homebrew's Python instead, also run `brew install python-tk`.
- Both: if `python3 -m venv` fails because `venv` isn't installed, install
  your distro's `python3-venv` package (Linux) or reinstall Python from
  python.org (macOS).

- **Dashboard** — tick which live system parameters to show (CPU, RAM, disk,
  network up/down, battery, volume, local/public IP, approximate location,
  uptime, date/time). Checkboxes grey out once you've picked as many as fit
  on screen at the chosen font size, so nothing silently gets clipped. Public
  IP and location are off by default and clearly marked - they're the only
  two parameters that make an outbound network call.
- **Image / Video** — show a single image, a slideshow from a folder, or play
  a video file. Playback controls: Play/Pause, Next/Prev (slideshow), and a
  seek bar (video). A loaded image or slideshow **stays on screen** until you
  stop it or load something else - it doesn't revert to the dashboard on its
  own.
- **Orientation** — Portrait (80×160) or Landscape (160×80), applies to the
  dashboard, images, and video alike.
- **Alerts** — push a temporary message (text, color, duration) that overlays
  whatever's currently showing, then reverts. Can also be triggered by other
  local scripts via a `127.0.0.1`-only HTTP endpoint (never reachable from
  the network) - see the Alerts tab for the exact `curl` example.

**Driver handling** (per OS, and it won't silently download/run anything on
its own - only ever offers a link for you to click):
- **Windows:** a compatible WCH driver is usually supplied automatically via
  Windows Update (this device worked with zero manual steps during
  development). If not detected, the app offers WCH's official driver page.
- **macOS:** same idea, offers WCH's macOS VCP driver page if needed.
- **Linux:** the `ch341` driver has shipped in the mainline kernel for years,
  so there's normally nothing to install. If the device still isn't
  detected, the app explains the far more likely cause - your user account
  needing to be in the `dialout` (or `uucp`) group - rather than pointing at
  a driver download that wouldn't fix it.

## This is built on an existing open-source project

The library code, system-monitor app, and themes here come from
[mathoudebine/turing-smart-screen-python](https://github.com/mathoudebine/turing-smart-screen-python)
(GPL-3.0-or-later), which already ships a dedicated driver for this exact
hardware (`library/lcd/lcd_comm_weact_b.py`, `REVISION: WEACT_B`). All
original copyright/license files are kept as-is, and the original README is
preserved at [`UPSTREAM_README.md`](UPSTREAM_README.md). This repo adds:

- `app/` — the standalone GUI described above (`driver_check.py`,
  `sensors.py`, `layout.py`, `media.py`, `alerts.py`, `worker.py`, `gui.py`)
- `run_app.py` / `run_app.bat` / `run_app.sh` — entrypoint and one-click
  launchers for Windows and Linux/macOS
- `config.yaml` set up for this specific device (`REVISION: WEACT_B`, `COM_PORT: COM5`)
- `test_display.py` — minimal standalone script: connects, reads the device's
  own firmware version back (proves bidirectional comms), then draws text and
  an animated progress bar
- `make_test_image.py` / `show_test_image.py`, `make_platformer_image.py` /
  `show_platformer_image.py` — generate and push test images to prove bitmap
  rendering

## Confirmed working

- Device identified: VID `0x1A86` / PID `0xFE0C` (WCH chip), enumerates as a
  serial port
- Firmware reported by the device itself: `V1.0.0.2`
- Verified on Windows: solid fills, live-drawn text, progress bars, full
  bitmap images, video playback, and the dashboard/media/text/alert app
  end-to-end
- Linux/macOS: supported by design (pure Python/Tkinter, no Windows-specific
  code path, platform-aware driver guidance) but not yet run on either by
  anyone - if you try it, letting us know how it went is genuinely useful.

![Test image sent to the display](test_image.png)

*The 80×160 test image above (generated by `make_test_image.py`) is what gets
pushed to the physical screen by `show_test_image.py`.*

## Hardware

- [WeAct Studio Display FS V1, 0.96"](https://github.com/WeActStudio/WeActStudio.SystemMonitor) —
  160×80 RGB565 IPS panel, USB-C, no SPI wiring needed (plug-and-play as a
  virtual COM port)

## Setup (manual, if not using the launcher scripts)

**Windows:**
```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

**Linux / macOS:**
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

The `app/` GUI auto-detects the serial port regardless of OS. `config.yaml`'s
`COM_PORT: COM5` only matters for the standalone scripts below and the
upstream `main.py` - change it to your actual port (e.g. `/dev/ttyUSB0`) if
you use those on Linux/macOS.

## Other scripts

**Quick proof-of-life test:**

```powershell
.venv\Scripts\python.exe test_display.py
```

**Push a custom image to the screen:**

```powershell
.venv\Scripts\python.exe make_test_image.py   # generates test_image.png
.venv\Scripts\python.exe show_test_image.py   # sends it to the display
```

**Full upstream system monitor** (CPU/RAM/disk/network stats, theme-YAML driven):

```powershell
.venv\Scripts\python.exe main.py
```

Pick a 0.96"-sized theme in `config.yaml` (`config.THEME`) — see
`res/themes/Example_0.96Inch_1`, `Example_0.96Inch_2`, `Digital_CPU_0.96Inch`,
or build your own via `theme-editor.py`.

## License

GPL-3.0-or-later, inherited from the upstream project. See `LICENSE` and
`COPYRIGHT`.
