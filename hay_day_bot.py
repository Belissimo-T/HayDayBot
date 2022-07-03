import time

import PIL.Image
import cv2
import numpy as np
import pytesseract

from window_utils import *

import os.path
import pyautogui

pyautogui.PAUSE = .25

UI_PATHS = {
    "farm": {"newspaper": "newspaper.png", "shop": "shop.png"},
    "newspaper": {"farm": (0.86, 0.13)},
    "shop": {"farm": (0.86, 0.13)}
}


class FailedNavigationException(Exception): ...


class UIController:
    def __init__(self, window):
        self.window = window
        self.ui_stack = ["farm"]

    def get_screenshot(self, x: float = 0, y: float = 0, x2: float = 1, y2: float = 1):
        img = get_borderless_screenshot(self.window)

        bbox = (x * img.width, y * img.height, x2 * img.width, y2 * img.height)

        img = img.crop(bbox)
        # img.save("img.png")
        return img

    def locate_image(self, image: str, tries=10, confidence=0.9):
        x, y, x2, y2 = self.locate_image_bbox(image, tries, confidence)

        dx = x2 - x
        dy = y2 - y

        return x + dx / 2, y + dy / 2

    def locate_image_bbox(self, image: str, tries=10, confidence=0.9):
        image_path = os.path.join("images", image)

        common_width = 1600
        common_height = 900

        needle_img_scale_factor = common_width / 1600

        needle_image = PIL.Image.open(image_path)
        needle_image = needle_image.resize(
            (int(needle_image.width * needle_img_scale_factor), int(needle_image.height * needle_img_scale_factor)),
            PIL.Image.LANCZOS
        )

        for trial in range(tries):
            img = self.get_screenshot().resize((common_width, common_height))
            img.save("img.png")
            image_rect = pyautogui.locate(needle_image, img, confidence=confidence)

            if image_rect is not None:
                break
        else:
            raise FailedNavigationException(
                f"UI state doesn't match internal state. Couldn't find button ({image_path})."
            )

        x, y, width, height = image_rect

        return x / common_width, y / common_height, (x + width) / common_width, (y + height) / common_height

    def ratio_coords_to_absolute(self, x: float, y: float):
        win_x, win_y, win_x2, win_y2 = get_content_bbox(self.window)

        win_width = win_x2 - win_x
        win_height = win_y2 - win_y

        return int(x * win_width + win_x), int(y * win_height + win_y)

    def get_click_location(self, target_ui_state: str):
        selector = UI_PATHS[self.current_ui_state][target_ui_state]

        if isinstance(selector, str):
            return self.locate_image(selector)
        elif isinstance(selector, tuple):
            return selector

        raise FailedNavigationException(f"Unknown selector type: {selector!r}")

    def _click_ui(self, target_ui_state: str):
        try:
            click_location = self.ratio_coords_to_absolute(*self.get_click_location(target_ui_state))

            pyautogui.click(click_location)
        except Exception as e:
            raise FailedNavigationException(f"Failed to navigate {self.current_ui_state} -> {target_ui_state}") from e

        time.sleep(1)

    def navigate_to(self, target_ui_state: str):
        print(f" * Navigating to {target_ui_state}...")
        if self.current_ui_state == target_ui_state:
            return

        self._click_ui(target_ui_state)
        self.ui_stack.append(target_ui_state)

    def back(self):
        print(f" * Going back to {self.ui_stack[-2]}...")
        self._click_ui(self.ui_stack[-2])
        self.ui_stack.pop()

    def reset(self):
        while len(self.ui_stack) > 1:
            self.back()

    def get_text_at(self, bbox: tuple[float, float, float, float], lang=None, custom_config="", scale_factor=10,
                    threshold=126, dilation=8) -> str:
        img = self.get_screenshot(*bbox)

        img = img.resize((int(img.width * scale_factor), int(img.height * scale_factor)), PIL.Image.QUAD)

        # Grayscale image
        img = img.convert('L')
        ret, img = cv2.threshold(np.array(img), threshold, 255, cv2.THRESH_BINARY)

        kernel = np.ones((dilation, dilation), np.uint8)

        img = cv2.dilate(img, kernel, iterations=1)

        img = PIL.Image.fromarray(img.astype(np.uint8))

        # img.save("2img.png")

        return pytesseract.image_to_string(
            img,
            lang=lang,
            config=custom_config
        )

    @property
    def current_possible_navigations(self) -> list[str]:
        return UI_PATHS[self.current_ui_state].keys()

    @property
    def current_ui_state(self):
        return self.ui_stack[-1]


class HayDayController(UIController):
    def list_advertisements(self):
        self.reset()
        self.navigate_to("newspaper")
        # self.reset_newspaper()

        time.sleep(1)

        ...

    def scroll_right(self):
        pyautogui.moveTo(*self.ratio_coords_to_absolute(0.7, 0.5))
        pyautogui.dragTo(*self.ratio_coords_to_absolute(0.4, 0.5), .3, button='left')

    def scroll_left(self):
        pyautogui.moveTo(*self.ratio_coords_to_absolute(0.4, 0.5))
        pyautogui.dragTo(*self.ratio_coords_to_absolute(0.7, 0.5), .3, button='left')

    def get_current_newspaper_page(self):
        # find number by searching for 2 with low confidence

        x, y = self.locate_image("newspaper_two.png", tries=1, confidence=0.5)

        return int(self.get_text_at(
            (x - .02, y - .015, x + .02, y + 0.02),
            custom_config="--psm 8 -c tessedit_char_whitelist=0123456789",
            scale_factor=10,
            threshold=126,
            dilation=8
        ))

    def change_newspaper_page(self, to: int = 2):
        to = to // 2 * 2

        assert 2 <= to <= 18, f"Invalid page number: {to}"

        failures = -1

        while (curr := self.get_current_newspaper_page()) != to:
            failures += 1
            print(f"Measuring page: {curr}, {failures=}")

            while curr != to:
                if curr < to:
                    self.scroll_right()
                    curr += 2
                else:
                    self.scroll_left()
                    curr -= 2

                print(f"Current Newspaper nr: {curr} desired: {to}")

            time.sleep(2)


if __name__ == "__main__":
    win = next(filter(lambda x: "Android Emulator" in get_window_title(x), get_all_windows()))

    controller = HayDayController(win)

    controller.navigate_to("shop")
    controller.back()
    controller.navigate_to("newspaper")
    #
    # # print(controller.locate_image_bbox("newspaper_two.png"))

    print(f"{controller.get_current_newspaper_page()!r}")

    controller.change_newspaper_page(7)
    controller.change_newspaper_page(18)
    controller.change_newspaper_page(2)

    controller.back()
