import re
import sys
import unittest
from pathlib import Path
from unittest import mock

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import config
import fishing
import screen_text

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def image(name: str):
    return cv2.imread(str(FIXTURES / f"{name}.png"))


def centre(lines, test):
    for text, (x0, y0, x1, y1) in lines:
        if test(text):
            return (x0 + x1) // 2, (y0 + y1) // 2
    return None


def make(counts, auto_buy=True):
    cfg = {**config.DEFAULTS, "advanced": dict(config.ADVANCED_DEFAULTS), "bait_index": 0,
           "auto_buy_common": auto_buy,
           "baits": [{"name": n, "use": True, "count": c}
                     for n, c in zip(("Rare Fish Bait", "Common Fish Bait"), counts)]}
    hooks = fishing.Hooks(status=lambda m: None, event=lambda k, c: None, frame=lambda i, r: None,
                          bait_changed=lambda: None)
    f = fishing.Fisher(cfg, hooks, should_abort=lambda: False)
    f._rows = {"Rare Fish Bait": 0, "Common Fish Bait": 1}
    return f


class DialogReadTests(unittest.TestCase):
    """Crops of the user's shop screenshots (2026-10-25)."""

    def test_question_has_yes_and_no(self):
        lines = screen_text.text_boxes(image("shop_question"))
        self.assertIsNotNone(centre(lines, lambda t: "purchase" in t.lower() and "common fish" in t.lower()))
        self.assertIsNotNone(centre(lines, lambda t: t.strip().lower() == "yes"))
        self.assertIsNotNone(centre(lines, lambda t: t.strip().lower() == "no"))

    def test_how_many_has_buy_and_max(self):
        lines = screen_text.text_boxes(image("shop_how_many"))
        self.assertIsNotNone(centre(lines, lambda t: t.strip().lower() == "buy"))
        self.assertEqual([screen_text.shop_max(t) for t, _ in lines if screen_text.shop_max(t) is not None], [1])

    def test_amount_box_is_midway_between_yes_and_no(self):
        ask = screen_text.text_boxes(image("shop_question"))
        how = screen_text.text_boxes(image("shop_how_many"))
        yes = centre(ask, lambda t: t.strip().lower() == "yes")
        no = centre(ask, lambda t: t.strip().lower() == "no")
        amount = centre(how, lambda t: t.strip() == "1")
        self.assertAlmostEqual((yes[0] + no[0]) // 2, amount[0], delta=5)

    def test_closing_dots_show_where_the_amount_box_was(self):
        # The "..." read as ".••" here; over an ability label it read "Loaie" (2026-11-02).
        dots = centre(screen_text.text_boxes(image("shop_dots")),
                      lambda t: re.fullmatch(r"[.·•…]{2,}", t.replace(" ", "")) is not None)
        amount = centre(screen_text.text_boxes(image("shop_how_many")), lambda t: t.strip() == "1")
        self.assertAlmostEqual(dots[0], amount[0], delta=5)
        self.assertAlmostEqual(dots[1], amount[1], delta=8)

    def test_backdrop_band_is_inside_the_dialog_backdrop(self):
        ask = screen_text.text_boxes(image("shop_question"))
        band = fishing._backdrop_band(fishing.PixelRect(0, 0, 1000, 448), {
            "yes": ("Yes", centre(ask, lambda t: t.strip().lower() == "yes")),
            "no": ("No", centre(ask, lambda t: t.strip().lower() == "no")),
            "question": ("", centre(ask, lambda t: "purchase" in t.lower()))})
        x0, y0, x1, y1 = band
        for name in ("shop_question", "shop_how_many", "shop_dots"):
            # The deck outside the backdrop reads 108-139 grey.
            self.assertLess(image(name)[y0:y1, x0:x1].mean(), 70, name)

    def test_max_with_lookalikes(self):
        self.assertEqual(screen_text.shop_max("How many do you want? MAX: 1"), 1)
        self.assertEqual(screen_text.shop_max("How many do yoU want? MAX: 2S"), 25)
        self.assertIsNone(screen_text.shop_max("Would you like to purchase 1 Common Fish"))


class BuyFlowTests(unittest.TestCase):
    def setUp(self):
        self.log = []
        for name, fake in (
            ("click_at", lambda x, y: self.log.append(("click", x, y))),
            ("tap_key", lambda k, **kw: self.log.append(("key", k))),
            ("sleep_interruptible", lambda *a, **kw: False),
            ("click_point", lambda pt, **kw: self.log.append(("pick", pt.x))),
            ("bait_selected", lambda p: True),
        ):
            p = mock.patch.object(fishing, name, side_effect=fake)
            p.start()
            self.addCleanup(p.stop)
        p = mock.patch.object(fishing.Fisher, "_shop_image",
                              return_value=(fishing.PixelRect(0, 0, 10, 10), np.zeros((10, 10, 3), np.uint8)))
        p.start()
        self.addCleanup(p.stop)
        p = mock.patch.object(fishing.Fisher, "_close_shop",
                              side_effect=lambda before, ask, box: self.log.append(("close", *box)))
        p.start()
        self.addCleanup(p.stop)

    def _dialog(self, f, max_text):
        steps = iter([
            {"yes": ("Yes", (813, 1142)), "no": ("NO", (1187, 1142)),
             "question": ("Would you like to purchase 1 Common Fish", (963, 976))},
            {"buy": ("Buy", (812, 1146)), "max": (max_text, (900, 976))},
        ])
        return mock.patch.object(f, "_shop_find", side_effect=lambda want: next(steps)), \
            mock.patch.object(f, "_focus")

    def test_buys_the_max(self):
        f = make([1, 1])
        a, b = self._dialog(f, "How many do you want? MAX: 299")
        with a, b:
            self.assertIsNone(f._buy_common())
        self.assertEqual(self.log, [
            ("key", "e"), ("click", 813, 1142), ("click", 1000, 1146),
            ("key", "backspace"), ("key", "backspace"), ("key", "backspace"), ("key", "backspace"),
            ("key", "2"), ("key", "9"), ("key", "9"),
            ("click", 812, 1146), ("close", 1000, 1146),
        ])

    def test_max_zero_cancels(self):
        f = make([1, 1])
        a, b = self._dialog(f, "How many do you want? MAX: 0")
        with a, b:
            why = f._buy_common()
        self.assertIn("allows 0", why)
        self.assertEqual(self.log[-1], ("click", 1188, 1146))  # Cancel mirrors Buy

    def test_how_many_missing_closes_the_dialog(self):
        f = make([1, 1])
        steps = iter([{"yes": ("Yes", (813, 1142)), "no": ("NO", (1187, 1142)),
                       "question": ("purchase 1 Common Fish", (963, 976))}, None])
        with mock.patch.object(f, "_shop_find", side_effect=lambda want: next(steps)), \
                mock.patch.object(f, "_focus"):
            self.assertIn("closed the dialog", f._buy_common())
        self.assertEqual(self.log[-1], ("click", 1187, 1142))

    def test_other_npc_dialog_is_not_answered(self):
        f = make([1, 1])
        lines = [("Would you like to buy a Boat for 500 Peli?", (300, 100, 700, 130)),
                 ("Yes", (287, 335, 339, 361)), ("No", (667, 335, 707, 361))]
        clock = [0.0]

        def sleep(sec, abort=None):
            clock[0] += sec
            return False

        with mock.patch.object(fishing, "text_boxes", return_value=lines), \
                mock.patch.object(fishing, "grab", return_value=np.zeros((5, 5, 3), np.uint8)), \
                mock.patch.object(fishing, "resolve_origin"), \
                mock.patch.object(fishing, "area_rect", return_value=fishing.PixelRect(0, 0, 10, 10)), \
                mock.patch.object(fishing.time, "monotonic", side_effect=lambda: clock[0]), \
                mock.patch.object(fishing, "sleep_interruptible", side_effect=sleep), \
                mock.patch.object(f, "_focus"):
            self.assertIn("did not open", f._buy_common())
        self.assertNotIn("click", [e[0] for e in self.log])

    def test_no_seller_nearby(self):
        f = make([1, 1])
        with mock.patch.object(f, "_shop_find", return_value=None), mock.patch.object(f, "_focus"):
            self.assertIn("stand next to", f._buy_common())

    def test_buy_once_reports_the_new_count(self):
        f = make([1, 1])
        with mock.patch.object(f, "_buy_common", return_value=None), \
                mock.patch.object(fishing, "read_bait_count", return_value=(300, "x300")):
            self.assertEqual(f.buy_once(), "Test buy done. Common Fish Bait: 300 left.")

    def test_buy_once_reports_the_failure(self):
        f = make([1, 1])
        with mock.patch.object(f, "_buy_common", return_value="the 'How many' step did not show"):
            self.assertEqual(f.buy_once(), "Test buy failed: the 'How many' step did not show.")

    def test_restock_switches_to_common(self):
        f = make([1, 1])
        with mock.patch.object(f, "_buy_common", return_value=None), \
                mock.patch.object(fishing, "read_bait_count", return_value=(300, "x300")):
            f._next_bait(select=False)
        self.assertEqual(f.cfg["bait_index"], 1)
        self.assertEqual(f.cfg["baits"][1]["count"], 300)

    def test_failed_buy_goes_anti_afk(self):
        f = make([1, 1])
        with mock.patch.object(f, "_buy_common", return_value="the 'How many' step did not show"), \
                mock.patch.object(fishing, "read_bait_count", return_value=(1, "x1")), \
                self.assertRaises(fishing.OutOfBait):
            f._next_bait(select=False)

    def test_auto_buy_off_goes_anti_afk(self):
        f = make([1, 1], auto_buy=False)
        with mock.patch.object(f, "_buy_common") as buy, self.assertRaises(fishing.OutOfBait):
            f._next_bait(select=False)
        buy.assert_not_called()


SHOP_ASK = {"yes": ("Yes", (20, 80)), "no": ("No", (80, 80)), "question": ("purchase", (50, 20))}


class CloseShopTests(unittest.TestCase):
    """The "..." step, told apart by the dialog's dark backdrop, not by its text."""

    RECT = fishing.PixelRect(0, 0, 100, 100)
    BOX = (50, 80)

    def run_close(self, frames):
        """Run _close_shop over `frames` ("game", "how_many" or "dots"); the last one repeats."""
        before = np.full((100, 100, 3), 120, np.uint8)
        images = {"game": before, "how_many": np.full((100, 100, 3), 50, np.uint8),
                  "dots": np.full((100, 100, 3), 51, np.uint8)}
        shown = iter(frames)
        last = [frames[0]]

        def shop_image():
            last[0] = next(shown, last[0])
            return self.RECT, images[last[0]]

        clock = [0.0]

        def sleep(sec, abort=None):
            clock[0] += sec
            return False

        clicks, statuses = [], []
        f = make([1, 1])
        f.hooks = fishing.Hooks(status=statuses.append, event=lambda k, c: None,
                                frame=lambda i, r: None, bait_changed=lambda: None)
        with mock.patch.object(f, "_shop_image", side_effect=shop_image), \
                mock.patch.object(fishing, "text_boxes",
                                  side_effect=lambda im: [("Buy", (0, 0, 9, 9))] if im is images["how_many"] else []), \
                mock.patch.object(fishing, "click_at", side_effect=lambda x, y: clicks.append((x, y))), \
                mock.patch.object(fishing.time, "monotonic", side_effect=lambda: clock[0]), \
                mock.patch.object(fishing, "sleep_interruptible", side_effect=sleep):
            f._close_shop(before, SHOP_ASK, self.BOX)
        return clicks, statuses

    def test_clicks_the_amount_box_spot_once_the_dots_show(self):
        clicks, statuses = self.run_close(["how_many", "how_many", "dots", "game"])
        self.assertEqual(clicks, [self.BOX])
        self.assertEqual(statuses, [])

    def test_never_clicks_when_the_dialog_is_gone(self):
        # The click would land on the game, such as an ability button.
        clicks, statuses = self.run_close(["game"])
        self.assertEqual(clicks, [])
        self.assertIn("did not show", statuses[0])

    def test_never_clicks_while_the_how_many_step_shows(self):
        clicks, statuses = self.run_close(["how_many"])
        self.assertEqual(clicks, [])
        self.assertIn("did not show", statuses[0])

    def test_says_when_the_dialog_stays_open(self):
        clicks, statuses = self.run_close(["dots"])
        self.assertEqual(clicks, [self.BOX])
        self.assertIn("stayed open", statuses[0])


def dialog_image(lines) -> np.ndarray:
    img = np.full((420, 700, 3), (40, 40, 40), np.uint8)
    for i, text in enumerate(lines):
        cv2.putText(img, text, (30, 60 + i * 70), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (235, 235, 235), 2)
    return img


PANEL_NAMES = ["Rare Fish Bait", "Common Fish Bait", "Legendary Fish Bait"]


class RowCheckTests(unittest.TestCase):

    def test_row_names_from_real_reads(self):
        # Reads from the user's three-row panel (2026-10-26).
        self.assertEqual(screen_text.row_bait("Legendary FishTait | X33", PANEL_NAMES), "Legendary Fish Bait")
        self.assertEqual(screen_text.row_bait("Rare Fish Bait | X22", PANEL_NAMES), "Rare Fish Bait")
        self.assertEqual(screen_text.row_bait("Common Fish Bait x300", PANEL_NAMES), "Common Fish Bait")
        self.assertIsNone(screen_text.row_bait("×30", PANEL_NAMES))

    def _rows(self, by_row):
        ys = {fishing.row_spot(k)["y"]: v for k, v in enumerate(by_row)}
        return lambda p: ys.get(p["y"], (None, ""))

    def test_panel_without_rare_maps_common_to_the_top_row(self):
        f = make([20, 50])
        with mock.patch.object(fishing, "read_bait_count", side_effect=self._rows([(300, "Common Fish Bait x300")])), \
                mock.patch.object(fishing, "sleep_interruptible", return_value=False):
            f._read_all_baits()
        self.assertEqual(f._rows, {"Common Fish Bait": 0})
        self.assertEqual([b["count"] for b in f.cfg["baits"]], [0, 300])

    def test_full_panel_reads_each_bait_at_its_row(self):
        f = make([20, 50])
        rows = [(33, "Legendary FishTait | X33"), (22, "Rare Fish Bait | X22"), (300, "Common Fish Bait x300")]
        with mock.patch.object(fishing, "read_bait_count", side_effect=self._rows(rows)), \
                mock.patch.object(fishing, "sleep_interruptible", return_value=False):
            f._read_all_baits()
        self.assertEqual(f._rows, {"Legendary Fish Bait": 0, "Rare Fish Bait": 1, "Common Fish Bait": 2})
        self.assertEqual([b["count"] for b in f.cfg["baits"]], [22, 300])


class DisconnectTests(unittest.TestCase):
    def test_reads_the_dialog(self):
        # The user's screenshot text (2026-10-25), drawn plainly.
        img = dialog_image(["Disconnected", "Please check your internet connection",
                            "(Error Code: 277)", "Leave        Reconnect"])
        self.assertIsNotNone(screen_text.disconnected_text(img))

    def test_chat_word_alone_does_not_count(self):
        img = dialog_image(["Player123: lol i disconnected earlier"])
        self.assertIsNone(screen_text.disconnected_text(img))

    def test_closes_roblox_and_flags_the_quit(self):
        f = make([50, 50])
        with mock.patch.object(fishing, "roblox_client_rect", return_value=fishing.PixelRect(0, 0, 800, 600)), \
                mock.patch.object(fishing, "grab", return_value=np.zeros((10, 10, 3), np.uint8)), \
                mock.patch.object(fishing, "disconnected_text", return_value="Disconnected | Reconnect"), \
                mock.patch.object(fishing, "close_roblox", return_value=True) as close, \
                self.assertRaises(fishing.Disconnected):
            f._check_connection()
        close.assert_called_once()
        self.assertTrue(f.disconnected)

    def test_disconnect_during_anti_afk_ends_the_run_cleanly(self):
        f = make([1, 1], auto_buy=False)

        def idle():
            f.disconnected = True
            raise fishing.Disconnected("Roblox disconnected. Closed Roblox.")

        with mock.patch.object(f, "_fish", side_effect=fishing.OutOfBait("down to 1")), \
                mock.patch.object(f, "_idle", side_effect=idle):
            self.assertEqual(f.run(), "Roblox disconnected. Closed Roblox.")
        self.assertTrue(f.disconnected)


if __name__ == "__main__":
    unittest.main()
