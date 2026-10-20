#!/usr/bin/env python
"""Displays test_image.png on the WeAct 0.96" screen full-frame."""

from library.lcd.lcd_comm_weact_b import LcdCommWeActB
from library.lcd.lcd_comm import Orientation

COM_PORT = "COM5"
WIDTH, HEIGHT = 80, 160

print(f"Connecting to WeAct 0.96\" display on {COM_PORT} ...")
lcd = LcdCommWeActB(com_port=COM_PORT, display_width=WIDTH, display_height=HEIGHT)
lcd.Reset()
lcd.InitializeComm()
lcd.SetOrientation(orientation=Orientation.PORTRAIT)
lcd.SetBrightness(level=40)

print("Displaying test_image.png ...")
lcd.DisplayBitmap("test_image.png")
print("Done. Check the physical display.")
