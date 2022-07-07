import dataclasses
import time
from enum import Enum

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


def get_bbox_center(x, y, x2, y2):
    dx = x2 - x
    dy = y2 - y

    return x + dx / 2, y + dy / 2


Bbox = tuple[float, float, float, float]


def do_bboxes_collide(bbox1, bbox2, /) -> bool:
    xa1, ya1, xa2, ya2 = bbox1
    xb1, yb1, xb2, yb2 = bbox2

    return xa1 < xb2 and xa2 > xb1 and ya1 < yb2 and ya2 > yb1


def group_bboxes(*bboxes: Bbox):
    groups: list[list[Bbox]] = []

    for bbox in bboxes:
        for group in groups:
            if do_bboxes_collide(bbox, group[0]):
                group.append(bbox)
                break
        else:
            groups.append([bbox])

    out = []

    for group in groups:
        x1s, y1s, x2s, y2s = zip(*group)

        avg_x1 = sum(x1s) / len(x1s)
        avg_y1 = sum(y1s) / len(y1s)
        avg_x2 = sum(x2s) / len(x2s)
        avg_y2 = sum(y2s) / len(y2s)

        out.append((avg_x1, avg_y1, avg_x2, avg_y2))

    return out


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

    def locate_image(self, image: str, tries=10, confidence=0.85):
        return get_bbox_center(*self.locate_image_bbox(image, tries, confidence))

    def locate_images_bbox(self, image: str, tries=10, confidence=0.85):
        image_path = os.path.join("images", image)

        common_width = 1600
        common_height = 900

        needle_img_scale_factor = common_width / 1600  # search images are always 1600x900 so they need to be scaled

        needle_image = PIL.Image.open(image_path)
        needle_image = needle_image.resize(
            (int(needle_image.width * needle_img_scale_factor), int(needle_image.height * needle_img_scale_factor)),
            PIL.Image.LANCZOS
        )

        for trial in range(tries):
            img = self.get_screenshot().resize((common_width, common_height))
            img.save("img.png")
            image_rects = pyautogui.locateAll(needle_image, img, confidence=confidence)

            if image_rects:
                break
        else:
            raise FailedNavigationException(
                f"UI state doesn't match internal state. Couldn't find button ({image_path})."
            )

        return [(x / common_width, y / common_height, (x + width) / common_width, (y + height) / common_height) for
                x, y, width, height in image_rects]

    def locate_image_bbox(self, image: str, tries=10, confidence=0.85):
        return self.locate_images_bbox(image, tries, confidence)[0]

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

    def get_text_at(self, bbox: tuple[float, float, float, float] = None, lang=None, custom_config="", scale_factor=10,
                    threshold=126, dilation=8, dilation_iterations=1, img=None, margin_factor=1,
                    do_threshold: bool = True, invert=False, outlined_compensation=False) -> str:
        img = self.get_screenshot(*bbox) if img is None else \
            img.crop((bbox[0] * img.width, bbox[1] * img.height, bbox[2] * img.width, bbox[3] * img.height))

        img = img.resize((int(img.width * scale_factor), int(img.height * scale_factor)), PIL.Image.QUAD)

        # add margin to image
        _img = PIL.Image.new(img.mode, (int(img.width * margin_factor), int(img.height * margin_factor)), color="white")
        _img.paste(img, (_img.width // 2 - img.width // 2, _img.height // 2 - img.height // 2))
        img = _img

        img = img.convert('L')
        img = np.array(img)
        if do_threshold:
            # Grayscale image
            ret, img = cv2.threshold(img, threshold, 255, cv2.THRESH_BINARY)

        kernel = np.ones((dilation, dilation), np.uint8)

        img = cv2.dilate(img, kernel, iterations=dilation_iterations)

        if outlined_compensation:
            # floodfill image black from 0, 0
            cv2.floodFill(img, None, (0, 0), 0)

        if invert:
            # invert image
            img = 255 - img

        img = PIL.Image.fromarray(img.astype(np.uint8))

        img.save("2img.png")

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


@dataclasses.dataclass(frozen=True)
class HayDayItem:
    name: str
    default_price: int

    def default_price_at(self, quantity: int) -> int:
        return int(self.default_price * quantity)

    def maximum_price_at(self, quantity: int) -> int:
        return int(self.default_price * quantity * 3.6)

    def __repr__(self):
        return self.name


class HayDayItems(Enum):
    wheat = HayDayItem("Wheat", 1)
    corn = HayDayItem("Corn", 2)
    carrot = HayDayItem("Carrot", 2)
    soybean = HayDayItem("Soybean", 3)
    sugarcane = HayDayItem("Sugarcane", 4)
    indigo = HayDayItem("Indigo", 7)
    cotton = HayDayItem("Cotton", 8)
    pumpkin = HayDayItem("Pumpkin", 9)
    chili_pepper = HayDayItem("Chili Pepper", 10)
    apples = HayDayItem("Apples", 11)
    tomato = HayDayItem("Tomato", 12)
    raspberries = HayDayItem("Raspberries", 13)
    cherries = HayDayItem("Cherries", 19)
    blackberries = HayDayItem("Blackberries", 23)

    dynamite = HayDayItem("Dynamite", 7)
    axe = HayDayItem("Axe", 10)
    saw = HayDayItem("Saw", 15)
    tnt_barrel = HayDayItem("TNT Barrel", 20)
    shovel = HayDayItem("Shovel", 30)
    plank = HayDayItem("Plank", 75)
    nail = HayDayItem("Nail", 75)
    bolt = HayDayItem("Bolt", 75)
    screw = HayDayItem("Screw", 75)
    duct_tape = HayDayItem("Duct Tape", 75)
    wood_panel = HayDayItem("Wood Panel", 75)
    land_deed = HayDayItem("Land Deed", 112)
    mallet = HayDayItem("Mallet", 112)
    marker_stake = HayDayItem("Marker Stake", 112)

    sheep_feed = HayDayItem("Sheep Feed", 4)
    silver_ore = HayDayItem("Silver Ore", 5)
    gold_ore = HayDayItem("Gold Ore", 6)
    popcorn = HayDayItem("Popcorn", 9)
    brown_sugar = HayDayItem("Brown Sugar", 9)
    white_sugar = HayDayItem("White Sugar", 14)
    cream = HayDayItem("Cream", 14)
    wool = HayDayItem("Wool", 15)
    corn_bread = HayDayItem("Corn Bread", 20)
    carrot_pie = HayDayItem("Carrot Pie", 23)
    butter = HayDayItem("Butter", 23)
    pancake = HayDayItem("Pancake", 30)
    cotton_fabric = HayDayItem("Cotton Fabric", 30)
    blue_woolly_hat = HayDayItem("Blue Woolly Hat", 31)
    chili_popcorn = HayDayItem("Chili Popcorn", 34)
    cheese = HayDayItem("Cheese", 34)
    buttered_popcorn = HayDayItem("Buttered Popcorn", 35)
    raspberry_muffin = HayDayItem("Raspberry Muffin", 39)
    silver_bar = HayDayItem("Silver Bar", 41)
    sweater = HayDayItem("Sweater", 42)
    pumpkin_pie = HayDayItem("Pumpkin Pie", 44)
    carrot_cake = HayDayItem("Carrot Cake", 46)
    syrup = HayDayItem("Syrup", 50)
    hamburger = HayDayItem("Hamburger", 50)
    gold_bar = HayDayItem("Gold Bar", 50)
    bacon_and_eggs = HayDayItem("Bacon and Eggs", 56)
    platinum_bar = HayDayItem("Platinum Bar", 57)
    blue_sweater = HayDayItem("Blue Sweater", 58)
    cream_cake = HayDayItem("Cream Cake", 61)
    bacon_pie = HayDayItem("Bacon Pie", 61)
    blackberry_muffin = HayDayItem("Blackberry Muffin", 63)
    fish_pie = HayDayItem("Fish pie", 63)
    red_berry_cake = HayDayItem("Red Berry Cake", 71)
    apple_pie = HayDayItem("Apple Pie", 75)
    cheesecake = HayDayItem("Cheesecake", 79)
    wooly_chaps = HayDayItem("Wooly Chaps", 86)
    violet_dress = HayDayItem("Violet Dress", 91)


@dataclasses.dataclass
class HayDayAd:
    item: HayDayItem
    quantity: int
    price: int

    @property
    def price_delta_to_maximum(self):
        price_delta = self.item.maximum_price_at(self.quantity) - self.price

        assert price_delta >= 0

        return price_delta

    def __repr__(self):
        return f"{self.quantity}x {self.item.name} ({self.price} Coins)"


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
        assert self.current_ui_state == "newspaper"

        # find number by searching for 2 with low confidence

        x, y = self.locate_image("newspaper_two.png", tries=1, confidence=0.5)

        try:
            return int(self.get_text_at(
                (x - .02, y - .015, x + .02, y + 0.02),
                custom_config="--psm 8 -c tessedit_char_whitelist=0123456789",
                scale_factor=10,
                threshold=126,
                dilation=8
            ))
        except Exception as e:
            raise FailedNavigationException(f"Failed to get current newspaper page.") from e

    def change_newspaper_page(self, to: int = 2):
        assert self.current_ui_state == "newspaper"

        to = to // 2 * 2

        assert 2 <= to <= 18, f"Invalid page number: {to}"

        failures = -1

        while (curr := self.get_current_newspaper_page()) != to and failures < 5:
            failures += 1
            print(f" -> Measured page: {curr}, {failures=}")

            while curr != to:
                if curr < to:
                    self.scroll_right()
                    curr += 2
                else:
                    self.scroll_left()
                    curr -= 2

                print(f" -> Current Newspaper nr: {curr} desired: {to}")

            time.sleep(2)

    def get_current_newspaper_ad_images(self):
        assert self.current_ui_state == "newspaper"

        finds = self.locate_images_bbox("newspaper_ad.png", confidence=0.95)
        bboxes = group_bboxes(*finds)

        ad_images = []
        for i, bbox in enumerate(bboxes):
            x1, y1, x2, y2 = bbox

            bbox = x1 + .02, y1 - .4, x2 - .02, y2 - .02

            # this could be optimized by not getting a new screenshot every time, but I prefer elegance over speed
            img = self.get_screenshot(*bbox)

            ad_images.append(img)

        return ad_images

    def parse_ad_image(self, img: PIL.Image) -> HayDayAd:
        name = self.get_text_at(bbox=(0, .41, 1, .6), img=img, custom_config="--psm 7 --oem 1").strip()

        for _item in HayDayItems:
            if _item.value.name.lower() == name.lower():
                item: HayDayItem = _item.value
                break
        else:
            raise FailedNavigationException(f"No item matches {name=}.")

        print(f" -> Item: {item.name}")

        _quantity = self.get_text_at(
            bbox=(0, .70, .18, .9),
            img=img,
            custom_config=f"--psm 7 --oem 0 "
                          f"-c tessedit_char_whitelist=0123456789x "
                          f"-c load_system_dawg=false "
                          f"-c load_freq_dawg=false",
            scale_factor=1,
            dilation_iterations=0,
            outlined_compensation=True
            # margin_factor=2
        ).strip().replace("x", "")
        try:
            quantity = int(_quantity)
        except ValueError as e:
            raise FailedNavigationException(
                f"Quantity of {item.name} was parsed as {_quantity!r} but cannot be interpreted as an int."
            ) from e

        assert 0 < quantity <= 10, \
            f"Quantity of {item.name} was parsed as {quantity} but it must be in the range [1, 10]."

        print(f"  -> x{quantity}")

        _price = self.get_text_at(
            bbox=(.50, .70, .84, .98),
            img=img,
            custom_config=f"--psm 7 --oem 0 "
                          f"-c tessedit_char_whitelist=0123456789 "
                          f"-c load_system_dawg=false "
                          f"-c load_freq_dawg=false",
            scale_factor=2,
            dilation_iterations=0,
            outlined_compensation=True
            # margin_factor=5,
            # do_threshold=False
        ).strip()
        try:
            price = int(_price)
        except ValueError as e:
            raise FailedNavigationException(
                f"Price of {item.name} was parsed as {_price!r} but cannot be interpreted as an int."
            ) from e

        assert 0 < price <= item.maximum_price_at(quantity), \
            f"Price of {item.name} was parsed as {price} but it should be at most {item.maximum_price_at(quantity)}."

        print(f"  -> {price} Coins")

        return HayDayAd(item, quantity, price)

    def get_current_newspaper_ads(self):
        ad_images = self.get_current_newspaper_ad_images()

        ads = []

        for img in ad_images:
            ads.append(self.parse_ad_image(img))

        return ads


if __name__ == "__main__":
    win = next(filter(lambda x: "Android Emulator" in get_window_title(x), get_all_windows()))

    controller = HayDayController(win)

    controller.ui_stack = ["newspaper"]

    print(controller.get_current_newspaper_ads())

    # controller.navigate_to("shop")
    # controller.back()
    # controller.navigate_to("newspaper")
    # #
    # # # print(controller.locate_image_bbox("newspaper_two.png"))
    #
    # # print(f"{controller.get_current_newspaper_page()!r}")
    #
    # controller.change_newspaper_page(7)
    # controller.change_newspaper_page(18)
    # controller.change_newspaper_page(2)
    #
    # controller.back()
