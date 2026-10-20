#!/usr/bin/env python
"""Minimal proof-of-life test for the WeAct Studio Display FS V1 0.96".

Connects directly over COM5, proves bidirectional comms (reads the device's
own version string back), then draws a few things to visually confirm it
works: a fill, some text, and a progress bar.
"""

import time

from library.lcd.lcd_comm_weact_b import LcdCommWeActB
from library.lcd.lcd_comm import Orientation

COM_PORT = "COM5"
WIDTH, HEIGHT = 80, 160  # native portrait size of the 0.96" panel

print(f"Connecting to WeAct 0.96\" display on {COM_PORT} ...")
lcd = LcdCommWeActB(com_port=COM_PORT, display_width=WIDTH, display_height=HEIGHT)

lcd.Reset()
lcd.InitializeComm()  # logs the device's own reported firmware version

lcd.SetOrientation(orientation=Orientation.PORTRAIT)
lcd.SetBrightness(level=40)

print("Filling screen with a solid color ...")
lcd.Full((10, 20, 60))  # dark blue

print("Drawing text ...")
lcd.DisplayText(
    "Hello from\nClaude Code",
    5, 20,
    font="res/fonts/roboto/Roboto-Bold.ttf",
    font_size=14,
    font_color=(255, 255, 255),
    background_color=(10, 20, 60),
)

lcd.DisplayText(
    "WeAct 0.96\"",
    5, 70,
    font="res/fonts/roboto/Roboto-Regular.ttf",
    font_size=12,
    font_color=(0, 255, 150),
    background_color=(10, 20, 60),
)

print("Drawing a progress bar ...")
for value in range(0, 101, 10):
    lcd.DisplayProgressBar(
        5, 110,
        width=70, height=18,
        min_value=0, max_value=100, value=value,
        bar_color=(255, 200, 0), bar_outline=True,
        background_color=(10, 20, 60),
    )
    time.sleep(0.1)

lcd.DisplayText(
    "It works!",
    5, 135,
    font="res/fonts/roboto/Roboto-Bold.ttf",
    font_size=14,
    font_color=(255, 80, 80),
    background_color=(10, 20, 60),
)

print("Done. Check the physical display.")
# Leave content on screen - don't close/clear, so it stays visible.
