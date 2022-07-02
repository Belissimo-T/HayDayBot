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


def get_screenshot(window: Wnck.Window) -> tuple[PIL.Image, tuple[int, int, int, int]]:
    x, y, x2, y2 = get_bbox(window)

    _img = PIL.ImageGrab.grab(bbox=(x, y, x2, y2))

    window_make_foreground(window)

    bbox = get_bbox(window)

    time.sleep(0.1)

    return PIL.ImageGrab.grab(bbox), bbox
