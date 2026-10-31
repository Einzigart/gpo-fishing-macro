import sys
import unittest
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from detect import Detector

FIXTURES = Path(__file__).resolve().parent / "fixtures"

# Ground truth read by hand from the fixture crops (2026-10-24).
TRUTH = {
    "gap_middle": {"gap": (142, 233), "fish": 226.5, "progress": 0.23},
    "gap_bottom": {"gap_top": 333, "fish": 237.0, "progress": 0.17},
}

BGR_BLUE = (254, 170, 87)
BGR_GREY = (24, 24, 24)
BGR_SEA = (116, 31, 0)
BGR_WHITE = (247, 247, 247)
BGR_GREEN = (127, 255, 171)


def load(name: str, scale: float = 1.0) -> np.ndarray:
    img = cv2.imread(str(FIXTURES / f"{name}.png"))
    if scale != 1.0:
        interp = cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR
        img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=interp)
    return img


def synthetic(gap_top: int, gap_h: int, fish_y: int, fill: float, h: int = 400) -> np.ndarray:
    """Sea background with a 12 px track (rows 40..360), a gap, a fish line and a progress bar."""
    img = np.full((h, 160, 3), BGR_SEA, np.uint8)
    t0, t1 = 40, 360
    cv2.rectangle(img, (40, t0 - 3), (55, t1 + 3), BGR_GREY, -1)
    cv2.rectangle(img, (42, t0), (53, t1), BGR_BLUE, -1)
    cv2.rectangle(img, (42, gap_top), (53, gap_top + gap_h - 1), BGR_GREY, -1)
    cv2.line(img, (25, fish_y), (70, fish_y), BGR_WHITE, 3)
    cv2.rectangle(img, (95, t0 + 20), (108, t1), BGR_GREY, -1)
    g0 = int(t1 - fill * (t1 - (t0 + 20)))
    if fill > 0:
        cv2.rectangle(img, (97, g0), (106, t1), BGR_GREEN, -1)
    return img


class FixtureTests(unittest.TestCase):
    def test_gap_in_middle(self):
        r = Detector().find(load("gap_middle"))
        t = TRUTH["gap_middle"]
        self.assertIsNotNone(r)
        self.assertAlmostEqual(r.gap_top, t["gap"][0], delta=3)
        self.assertAlmostEqual(r.gap_bot, t["gap"][1], delta=3)
        self.assertAlmostEqual(r.fish_y, t["fish"], delta=2)
        self.assertAlmostEqual(r.progress, t["progress"], delta=0.03)

    def test_gap_at_bottom(self):
        r = Detector().find(load("gap_bottom"))
        t = TRUTH["gap_bottom"]
        self.assertIsNotNone(r)
        self.assertAlmostEqual(r.gap_top, t["gap_top"], delta=3)
        self.assertAlmostEqual(r.fish_y, t["fish"], delta=2)
        self.assertAlmostEqual(r.progress, t["progress"], delta=0.03)

    def test_no_minigame(self):
        d = Detector()
        self.assertIsNone(d.find(load("no_minigame")))
        self.assertIn("no fishing bar", d.last)

    def test_camera_zoom(self):
        # The bars scale with camera zoom; results must scale with them.
        for scale in (0.5, 2.0):
            for name in TRUTH:
                with self.subTest(name=name, scale=scale):
                    r = Detector().find(load(name, scale))
                    self.assertIsNotNone(r)
                    self.assertAlmostEqual(r.fish_y / scale, TRUTH[name]["fish"], delta=2)
                    self.assertAlmostEqual(r.progress, TRUTH[name]["progress"], delta=0.03)


class FullWindowTests(unittest.TestCase):
    """The whole Roblox window is searched, because the bars move with the camera."""

    def full(self, name: str) -> np.ndarray:
        return cv2.imread(str(FIXTURES / f"full_{name}.webp"))

    def test_finds_bars_anywhere(self):
        # Fixture crops start at (980, 465) in these frames.
        for name in TRUTH:
            with self.subTest(name=name):
                r = Detector().find(self.full(name))
                self.assertIsNotNone(r)
                self.assertAlmostEqual(r.fish_y - 465, TRUTH[name]["fish"], delta=2)
                self.assertAlmostEqual(r.progress, TRUTH[name]["progress"], delta=0.03)

    def test_no_false_bar_in_bright_day_sea(self):
        d = Detector()
        self.assertIsNone(d.find(self.full("day_sea_no_bars")))

    def test_box_around_bars_reads_the_same(self):
        from fishing import bar_box
        from roblox_geo import PixelRect
        img = self.full("gap_middle")
        window = PixelRect(0, 0, img.shape[1], img.shape[0])
        r = Detector().find(img)
        box = bar_box(r, window, window)
        r2 = Detector().find(img[box.y:box.y + box.h, box.x:box.x + box.w])
        self.assertAlmostEqual(box.y + r2.fish_y, r.fish_y, delta=1)
        self.assertAlmostEqual(box.y + r2.gap_y, r.gap_y, delta=1)
        self.assertAlmostEqual(r2.progress, r.progress, delta=0.02)


class SyntheticTests(unittest.TestCase):
    def test_gap_middle(self):
        r = Detector().find(synthetic(gap_top=150, gap_h=70, fish_y=180, fill=0.5))
        self.assertIsNotNone(r)
        self.assertAlmostEqual(r.gap_top, 150, delta=1)
        self.assertAlmostEqual(r.gap_bot, 219, delta=1)
        self.assertAlmostEqual(r.fish_y, 180, delta=1)
        self.assertAlmostEqual(r.progress, 0.5, delta=0.03)

    def test_fish_over_blue(self):
        r = Detector().find(synthetic(gap_top=250, gap_h=70, fish_y=100, fill=0.2))
        self.assertAlmostEqual(r.fish_y, 100, delta=1)
        self.assertAlmostEqual(r.gap_top, 250, delta=1)

    def test_gap_at_top_uses_locked_height(self):
        d = Detector()
        d.find(synthetic(gap_top=150, gap_h=70, fish_y=180, fill=0.5))
        img = synthetic(gap_top=40, gap_h=70, fish_y=60, fill=0.5)
        # Dark background right above the track would stretch the gap without the lock.
        img[:37, 40:56] = BGR_GREY
        r = d.find(img)
        self.assertEqual(r.gap_h, 70)
        self.assertAlmostEqual(r.gap_bot, 109, delta=1)

    def test_empty_meter_is_unknown(self):
        r = Detector().find(synthetic(gap_top=150, gap_h=70, fish_y=180, fill=0.0))
        self.assertIsNone(r.progress)

    def test_no_fish_line(self):
        img = synthetic(gap_top=150, gap_h=70, fish_y=180, fill=0.5)
        img[176:185, 20:75] = BGR_SEA
        img[176:185, 42:54] = BGR_GREY
        d = Detector()
        self.assertIsNone(d.find(img))
        self.assertIn("no fish line", d.last)


if __name__ == "__main__":
    unittest.main()
