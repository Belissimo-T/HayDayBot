from window_utils import *

import os.path
import pyautogui

pyautogui.PAUSE = 1

UI_PATHS = {
    "farm": {"newspaper": "newspaper.png", "shop": "shop.png"},
    "newspaper": {"farm": (0.86, 0.13)},
    "shop": {"farm": (0.86, 0.13)}
}


class UIController:
    def __init__(self, window):
        self.window = window
        self.ui_stack = ["farm"]

    def locate_image(self, image: str):
        image_path = os.path.join("images", image)

        for trial in range(10):
            _img, bbox = get_screenshot(self.window)

            x_stretch = _img.width / 1600
            y_stretch = _img.height / 900

            img = _img.resize((1600, 900))
            img.save("img.png")

            _button_location = pyautogui.locate(image_path, img, confidence=0.8)
            if _button_location is not None:
                break

        else:
            raise Exception(
                f"UI state doesn't match internal state. Couldn't find button ({image_path})."
            )

        r_x, r_y = pyautogui.center(_button_location)

        win_x, win_y, _, _ = bbox

        return int(r_x * x_stretch + win_x), int(r_y * y_stretch + win_y)

    def locate_ratio_coords(self, x: float, y: float):
        win_x, win_y, win_x2, win_y2 = get_bbox(self.window)

        win_width = win_x2 - win_x
        win_height = win_y2 - win_y

        return int(x * win_width + win_x), int(y * win_height + win_y)

    def get_click_location(self, target_ui_state: str):
        selector = UI_PATHS[self.current_ui_state][target_ui_state]

        if isinstance(selector, str):
            return self.locate_image(selector)
        elif isinstance(selector, tuple):
            return self.locate_ratio_coords(*selector)
        else:
            raise Exception(f"Unknown selector type: {selector!r}")

    def _click_ui(self, target_ui_state: str):
        try:
            pyautogui.click(self.get_click_location(target_ui_state))
        except Exception as e:
            raise Exception(f"Failed to navigate {self.current_ui_state} -> {target_ui_state}") from e

    def navigate_to(self, target_ui_state: str):
        if self.current_ui_state == target_ui_state:
            return

        self._click_ui(target_ui_state)
        self.ui_stack.append(target_ui_state)

        print(f" * Navigated to {self.current_ui_state}")

    def back(self):
        self._click_ui(self.ui_stack[-2])
        self.ui_stack.pop()

        print(f" * Went back to {self.current_ui_state}")

    @property
    def current_possible_navigations(self) -> list[str]:
        return UI_PATHS[self.current_ui_state].keys()

    @property
    def current_ui_state(self):
        return self.ui_stack[-1]


if __name__ == "__main__":
    win = next(filter(lambda x: "Android Emulator" in get_window_title(x), get_all_windows()))

    controller = UIController(win)

    controller.navigate_to("newspaper")
    controller.back()
    controller.navigate_to("shop")
    controller.back()
