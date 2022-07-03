import io
import subprocess
import time

import PIL.Image
import PIL.ImageGrab
import gi

gi.require_version('Wnck', '3.0')
from gi.repository import Wnck


def get_all_windows():
    # process raises SIGSEGV if Screen is instantiated
    # noinspection PyArgumentList
    screen = Wnck.Screen.get_default()

    screen.force_update()

    return screen.get_windows()


def get_window_title(window: Wnck.Window):
    return window.get_name()


def window_make_foreground(window: Wnck.Window):
    window.activate(int(time.time()))


def get_bbox(window: Wnck.Window):
    geometry = window.get_geometry()

    return geometry.xp, geometry.yp, geometry.xp + geometry.widthp, geometry.yp + geometry.heightp


def get_screenshot(window: Wnck.Window) -> PIL.Image:
    x, y, x2, y2 = get_bbox(window)

    _img = PIL.ImageGrab.grab(bbox=(x, y, x2, y2))

    window_make_foreground(window)

    bbox = get_bbox(window)

    time.sleep(0.1)

    return PIL.ImageGrab.grab(bbox)


def get_borderless_screenshot(window: Wnck.Window) -> PIL.Image:
    window_make_foreground(window)

    time.sleep(0.1)

    out = subprocess.check_output(["scrot", "-u", "-"])

    return PIL.Image.open(io.BytesIO(out))


def get_content_bbox(window: Wnck.Window) -> PIL.Image:
    # screenshot = get_screenshot(window)
    # borderless_screenshot = get_borderless_screenshot(window)
    #
    # x, y, x2, y2 = get_bbox(window)
    #
    # dx = screenshot.width - borderless_screenshot.width
    # dy = screenshot.height - borderless_screenshot.height
    #
    # content_bbox = x + dx / 2, y + dy, x2 - dx / 2, y2
    #
    # return content_bbox

    xid = window.get_xid()

    out = subprocess.check_output(["xwininfo", "-id", str(xid)], encoding="utf-8")

    x = y = width = height = None

    for line in out.splitlines():
        line = line.strip()

        if line.startswith("Absolute upper-left X:"):
            x = int(line.split(":")[1].strip())
        elif line.startswith("Absolute upper-left Y:"):
            y = int(line.split(":")[1].strip())
        elif line.startswith("Width:"):
            width = int(line.split(":")[1].strip())
        elif line.startswith("Height:"):
            height = int(line.split(":")[1].strip())

    assert None not in (x, y, width, height), "xwininfo output is invalid"

    return x, y, x + width, y + height
