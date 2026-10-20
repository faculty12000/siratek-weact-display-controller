"""Reads every parameter the Dashboard tab can show.

Local/offline metrics use library.sensors.sensors_python (psutil/GPUtil based
- no admin rights, no network calls) by default. CPU temperature falls back
to LibreHardwareMonitor ONLY if the app is explicitly run as admin and the
user opts in - sensors_librehardwaremonitor.py calls sys.exit() at import
time if not elevated, so it is never imported unless both conditions hold.

Exactly two metrics make outbound network calls (public IP, location) - both
off by default, and the catalog below marks them so the GUI can label and
gate them clearly.
"""

import ctypes
import math
import os
import socket
import sys
import time
from datetime import datetime

import psutil
import requests

# Absolute path so `import library...` works regardless of the process's
# current directory.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
import library.sensors.sensors_python as _py_sensors

try:
    from uptime import uptime as _uptime
except Exception:
    _uptime = None

try:
    import pycaw.pycaw as _pycaw
    from comtypes import CLSCTX_ALL
except Exception:
    _pycaw = None

# ---------------------------------------------------------------------------
# Metric catalog: key -> (label, external_call, needs_admin, unit)
# ---------------------------------------------------------------------------
METRICS = {
    "cpu_percent": ("CPU", False, False, "%"),
    "cpu_temp": ("CPU Temp", False, True, "C"),  # "needs_admin" = more accurate with LHM; works without, may show N/A
    "ram_percent": ("RAM", False, False, "%"),
    "disk_percent": ("Disk", False, False, "%"),
    "net_down": ("Down", False, False, "KB/s"),
    "net_up": ("Up", False, False, "KB/s"),
    "battery": ("Battery", False, False, "%"),
    "volume": ("Volume", False, False, "%"),
    "local_ip": ("Local IP", False, False, ""),
    "public_ip": ("Public IP", True, False, ""),
    "location": ("Location", True, False, ""),
    "uptime": ("Uptime", False, False, ""),
    "datetime": ("Date/Time", False, False, ""),
}

_is_admin = None


def is_admin() -> bool:
    global _is_admin
    if _is_admin is None:
        try:
            _is_admin = bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception:
            _is_admin = False
    return _is_admin


class SensorReader:
    """Stateful reader - some metrics (network rate) need a previous sample,
    some (public IP/location) should be cached and refreshed slowly rather
    than queried on every render tick."""

    def __init__(self, disk_path="C:\\", net_interface=None, enable_external=False):
        self.disk_path = disk_path
        self.net_interface = net_interface or self._pick_interface()
        self.enable_external = enable_external
        self._last_net_time = time.time()
        self._last_net = psutil.net_io_counters(pernic=True).get(self.net_interface)
        self._public_ip_cache = None
        self._public_ip_fetched_at = 0
        self._location_cache = None
        self._location_fetched_at = 0
        self._volume_iface = self._init_volume() if _pycaw else None

    @staticmethod
    def _pick_interface():
        # Prefer the interface with the most traffic so far (best-effort default)
        counters = psutil.net_io_counters(pernic=True)
        if not counters:
            return None
        return max(counters, key=lambda name: counters[name].bytes_sent + counters[name].bytes_recv)

    @staticmethod
    def _init_volume():
        try:
            from ctypes import POINTER, cast
            from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
            device = AudioUtilities.GetSpeakers()
            interface = device.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
            return cast(interface, POINTER(IAudioEndpointVolume))
        except Exception:
            return None

    def read(self, key: str) -> str:
        try:
            return getattr(self, f"_read_{key}")()
        except AttributeError:
            return "?"
        except Exception:
            return "err"

    # -- local / offline metrics -------------------------------------------------
    def _read_cpu_percent(self):
        return f"{_py_sensors.Cpu.percentage(interval=None):.0f}%"

    def _read_cpu_temp(self):
        t = _py_sensors.Cpu.temperature()
        if math.isnan(t):
            # psutil.sensors_temperatures() isn't available on Windows -
            # this is the expected result there, not a bug.
            return "N/A"
        return f"{t:.0f}C"

    def _read_ram_percent(self):
        return f"{_py_sensors.Memory.virtual_percent():.0f}%"

    def _read_disk_percent(self):
        try:
            return f"{psutil.disk_usage(self.disk_path).percent:.0f}%"
        except Exception:
            return "N/A"

    def _read_net_down(self):
        rate = self._net_rates()[1]
        return f"{rate / 1024:.0f}KB/s"

    def _read_net_up(self):
        rate = self._net_rates()[0]
        return f"{rate / 1024:.0f}KB/s"

    def _net_rates(self):
        now = time.time()
        interval = max(now - self._last_net_time, 0.01)
        counters = psutil.net_io_counters(pernic=True).get(self.net_interface)
        if not counters or not self._last_net:
            self._last_net = counters
            self._last_net_time = now
            return 0.0, 0.0
        up = (counters.bytes_sent - self._last_net.bytes_sent) / interval
        down = (counters.bytes_recv - self._last_net.bytes_recv) / interval
        self._last_net = counters
        self._last_net_time = now
        return max(up, 0.0), max(down, 0.0)

    def _read_battery(self):
        b = psutil.sensors_battery()
        if b is None:
            return "N/A"
        return f"{b.percent:.0f}%"

    def _read_volume(self):
        if not self._volume_iface:
            return "N/A"
        try:
            return f"{round(self._volume_iface.GetMasterVolumeLevelScalar() * 100)}%"
        except Exception:
            return "N/A"

    def _read_local_ip(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "N/A"

    def _read_uptime(self):
        if _uptime is None:
            return "N/A"
        secs = _uptime()
        h, m = int(secs // 3600), int((secs % 3600) // 60)
        return f"{h}h{m}m"

    def _read_datetime(self):
        return datetime.now().strftime("%H:%M %d/%m")

    # -- external metrics: off unless enable_external is True --------------------
    def _read_public_ip(self):
        if not self.enable_external:
            return "off"
        if time.time() - self._public_ip_fetched_at > 300 or not self._public_ip_cache:
            try:
                r = requests.get("https://api.ipify.org?format=json", timeout=3)
                self._public_ip_cache = r.json().get("ip", "N/A")
            except Exception:
                self._public_ip_cache = "N/A"
            self._public_ip_fetched_at = time.time()
        return self._public_ip_cache

    def _read_location(self):
        if not self.enable_external:
            return "off"
        if time.time() - self._location_fetched_at > 300 or not self._location_cache:
            try:
                r = requests.get("http://ip-api.com/json/?fields=city,country", timeout=3)
                data = r.json()
                self._location_cache = f"{data.get('city', '?')}, {data.get('country', '?')}"
            except Exception:
                self._location_cache = "N/A"
            self._location_fetched_at = time.time()
        return self._location_cache
