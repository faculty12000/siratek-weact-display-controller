"""Detects whether the WeAct 0.96" display's serial port is present, and
offers a guided (user-clicked, not silent) path to the driver if it isn't -
the story is very different per OS:

- Windows: a compatible WCH (CH340-family) driver is usually supplied
  automatically via Windows Update. If not, WCH's own installer is one click.
- macOS: needs WCH's separate VCP driver package, also one click away.
- Linux: the ch341 driver has shipped in the mainline kernel for years, so
  there's normally nothing to install at all - the far more common snag is a
  permissions issue (the user's account isn't in the group that owns the
  serial device), which a driver download can't fix anyway.

Deliberately not done anywhere: silently downloading and running a
kernel-driver installer unattended.
"""

import platform
import webbrowser

from serial.tools.list_ports import comports

VID = 0x1A86
PID = 0xFE0C

# Official WCH (manufacturer of the CH340-family USB-serial chip this device
# uses) driver download pages, per OS.
DRIVER_PAGES = {
    "Windows": "https://www.wch.cn/downloads/CH341SER_EXE.html",
    "Darwin": "https://www.wch.cn/downloads/CH34XSER_MAC_ZIP.html",
}

LINUX_GUIDANCE = (
    "Linux usually needs no driver at all - the ch341 driver has been built "
    "into the mainline kernel for years.\n\n"
    "If the display still isn't showing up as a serial device:\n"
    "  1. Check it's detected at all: run `dmesg | tail` right after "
    "plugging it in, or look for it with `ls /dev/ttyUSB* /dev/ttyACM*`.\n"
    "  2. Most likely cause: your user isn't in the group that owns the "
    "serial device (often `dialout`, sometimes `uucp`). Run:\n"
    "       sudo usermod -aG dialout $USER\n"
    "     then log out and back in (group membership only applies to new "
    "sessions)."
)


def find_device_port():
    """Returns the serial port device name (e.g. 'COM5' on Windows,
    '/dev/ttyUSB0' on Linux, '/dev/cu.wchusbserial...' on macOS) if the WeAct
    display's VID/PID is found among connected serial devices, else None."""
    for port in comports():
        if port.vid == VID and port.pid == PID:
            return port.device
    return None


def driver_guidance():
    """Returns (message, url_or_None) describing what to do next for this OS.
    url_or_None is a driver download page to offer opening, or None when
    there's nothing to download (Linux)."""
    system = platform.system()
    if system == "Linux":
        return LINUX_GUIDANCE, None
    if system in DRIVER_PAGES:
        label = "Windows Update" if system == "Windows" else "WCH's site"
        return (
            f"Most machines get a compatible driver automatically (via {label}) "
            "the first time the device is plugged in.\n\n"
            "Open the official WCH driver download page?"
        ), DRIVER_PAGES[system]
    return "Could not determine driver guidance for this OS.", None


def open_driver_download_page(url: str = None):
    """Opens a driver download page in the user's default browser."""
    webbrowser.open(url or DRIVER_PAGES.get(platform.system(), DRIVER_PAGES["Windows"]))
