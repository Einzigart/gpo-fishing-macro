import sys
import unittest
from pathlib import Path
from unittest import mock

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import screen_text  # noqa: E402
import config  # noqa: E402
import fishing  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def make(counts: list[int | None], use: list[bool] | None = None) -> fishing.Fisher:
    use = use or [True] * len(counts)
    cfg = {**config.DEFAULTS, "advanced": dict(config.ADVANCED_DEFAULTS), "bait_index": 0,
           "baits": [{"name": f"b{i}", "use": u, "count": n} for i, (n, u) in enumerate(zip(counts, use))]}
    hooks = fishing.Hooks(status=lambda m: None, event=lambda k, catch: None, frame=lambda i, r: None,
                          bait_changed=lambda: None)
    f = fishing.Fisher(cfg, hooks, should_abort=lambda: False)
    f._rows = {f"b{i}": i for i in range(len(counts))}  # bait b<i> in panel row i
    return f


def image(name: str):
    return cv2.imread(str(FIXTURES / f"{name}.png"))


class ReaderTests(unittest.TestCase):
    def test_reads_count_from_panel(self):
        for n in (298, 296, 295):
            with self.subTest(n=n):
                count, text = screen_text.read_count(image(f"bait_x{n}"))
                self.assertEqual(count, n, text)

    def test_reads_the_picked_row_of_two(self):
        for name, n in (("rare_x30", 30), ("common_x299", 299)):
            with self.subTest(name=name):
                count, text = screen_text.read_count(image(f"bait_two_rows_{name}"))
                self.assertEqual(count, n, text)

    def test_lookalike_digits(self):
        # Misreads from real runs on 2026-10-24.
        for text, n in (("Rare Fish Bait | ХЦ4", 44), ("Rare Fish Bait ×З6", 36),
                        ("Common Fish Bait ×G4", 64), ("Common Fish Bait ×S", 5)):
            with self.subTest(text=text):
                m = screen_text._COUNT.search(text)
                self.assertEqual(int(m.group(1).translate(screen_text._DIGIT_LOOKALIKES)), n)
        self.assertIsNone(screen_text._COUNT.search("Exotic Tigerfin"))

    def test_no_count_in_other_ui(self):
        count, why = screen_text.read_count(image("gap_middle")[:120])
        self.assertIsNone(count)

    def test_reads_new_item_banner_and_rarity(self):
        # Rarities from the wiki Bestiary; colours measured on 2026-10-24.
        for name, item, rarity in (("crimson_polka_puffer", "Crimson Polka Puffer", "Rare"),
                                   ("blue_lip_grouper", "Blue-Lip Grouper", "Common"),
                                   ("jack_o_rod_blueprint", "Jack-O'Rod Blueprint", "Epic")):
            with self.subTest(name=name):
                got, got_rarity, text = screen_text.read_item(image(f"item_{name}"))
                self.assertEqual((got, got_rarity), (item, rarity), text)

    def test_no_banner(self):
        got, rarity, why = screen_text.read_item(image("item_none"))
        self.assertIsNone(got)

    def _recoloured(self, colour_at):
        """The Blue-Lip Grouper banner with its green name text recoloured."""
        img = image("item_blue_lip_grouper")
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        green = (hsv[:, :, 0] >= 45) & (hsv[:, :, 0] <= 75) & (hsv[:, :, 1] >= 100) & (hsv[:, :, 2] >= 180)
        ys, xs = np.where(green)
        x0, x1 = xs.min(), xs.max()
        for y, x in zip(ys, xs):
            hsv[y, x, 0] = colour_at((x - x0) / max(1, x1 - x0))
        return cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)

    def _colour_rarity(self, colour_at) -> str:
        img = self._recoloured(colour_at)
        box = next(b for _, _, b, _ in screen_text._lines(img) if b)
        return screen_text.rarity_of(img[box[1]:box[3], box[0]:box[2]])

    def test_name_colours(self):
        for hue, rarity in ((60, "Common"), (93, "Rare"), (118, "Epic"), (10, "unknown (orange)")):
            with self.subTest(hue=hue):
                self.assertEqual(self._colour_rarity(lambda f, h=hue: h), rarity)

    def test_rainbow_name_is_legendary(self):
        self.assertEqual(self._colour_rarity(lambda f: int(f * 179)), "Legendary")

    def test_wiki_names_fix_misreads(self):
        # Misreads seen in a real run on 2026-10-24.
        self.assertEqual(screen_text._known("Tigerfins"), "Tigerfin")
        self.assertEqual(screen_text._known("Blue-Lip Grouper-"), "Blue-Lip Grouper")
        self.assertEqual(screen_text._known("Skeletal Shark"), "Skeletal Shark")
        self.assertEqual(screen_text._known("Dark Skeletal Shark"), "Dark Skeletal Shark")
        self.assertIsNone(screen_text._known("Mera Mera no Mi"))


class BaitTests(unittest.TestCase):
    def setUp(self):
        self.clicks = []
        self.selected = []  # results of the gold-frame check, in order; True once empty
        # Panel row k sits at x = k/10. self.screen: x -> count shown there
        # (missing = row unreadable or empty; a list is read one value per try,
        # misreads first). self.names: row k -> bait name, "b<k>" by default.
        self.screen = {}
        self.names = {}

        def read(p):
            if p["x"] not in self.screen:
                return None, ""
            k = round(p["x"] * 10)
            v = self.screen[p["x"]]
            if isinstance(v, list):
                v = v.pop(0) if len(v) > 1 else v[0]
            return v, f"{self.names.get(k, f'b{k}')} x{v}"

        for name, fake in (
            ("click_point", lambda pt, **kw: self.clicks.append(pt.x)),
            ("read_bait_count", read),
            ("sleep_interruptible", lambda *a, **kw: False),
            ("row_spot", lambda k: {"x": k / 10, "y": 0.5}),
            ("row_bait", lambda row, names: row.split()[0] if row else None),
            ("bait_selected", lambda p: self.selected.pop(0) if self.selected else True),
        ):
            patcher = mock.patch.object(fishing, name, side_effect=fake)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_unreadable_panel_makes_count_unknown_and_keeps_fishing(self):
        # A failed read must not drift the count to "last one" (2026-10-24 bug).
        f = make([2, 5])
        f._use_bait()
        self.assertIsNone(f.cfg["baits"][0]["count"])
        self.assertEqual(f.cfg["bait_index"], 0)
        self.assertEqual(self.clicks, [])

    def test_misread_is_retried(self):
        f = make([45])
        self.screen[0.0] = [4, 44]  # "x44" read once as "x4", then correctly
        f._use_bait()
        self.assertEqual(f.cfg["baits"][0]["count"], 44)

    def test_rare_on_last_one_moves_to_common_with_stock(self):
        # The reported case: Rare first with 1 left, Common with 4 left.
        f = make([1, 4])
        self.screen.update({0.0: 1, 0.1: 4})
        f._read_all_baits()
        f._next_bait(select=True)
        self.assertEqual(f.cfg["bait_index"], 1)
        self.assertEqual(self.clicks, [0.1])

    def test_bait_missing_from_panel_is_skipped(self):
        # The panel lists only owned baits; one you have none of is skipped.
        f = make([5, 5])
        f._rows = {}  # a run starts with no map
        self.screen[0.0] = 5  # only b0 is listed
        f._read_all_baits()
        self.assertEqual(f._rows, {"b0": 0})
        self.assertEqual(f.cfg["baits"][1]["count"], 0)
        f._next_bait(select=True)
        self.assertEqual(f.cfg["bait_index"], 0)
        self.assertEqual(self.clicks, [0.0])

    def test_rows_moved_up_when_a_bait_type_is_missing(self):
        # The user's case (2026-10-30): no Legendary, so Rare and Common sit one row higher.
        f = make([None, 5, 5])
        f._rows = {}
        self.names = {0: "b1", 1: "b2"}
        self.screen.update({0.0: 18, 0.1: 114})
        f._read_all_baits()
        self.assertEqual(f._rows, {"b1": 0, "b2": 1})
        self.assertEqual([b["count"] for b in f.cfg["baits"]], [0, 18, 114])

    def test_no_panel_stops_at_start(self):
        f = make([5])
        f._rows = {}
        with self.assertRaises(fishing.StopRun) as ctx:
            f._read_all_baits()
        self.assertIn("Equip the rod", str(ctx.exception))

    def test_rows_shift_mid_run_are_remapped(self):
        # b0 is gone, so b1 moved up to row 0 while the app was using it at row 1.
        f = make([5, 5])
        f.cfg["bait_index"] = 1
        self.names = {0: "b1"}
        self.screen[0.0] = 4
        f._use_bait()
        self.assertEqual(f._rows, {"b1": 0})
        self.assertEqual(f.cfg["baits"][1]["count"], 4)

    def test_unreadable_row_without_a_shift_is_kept(self):
        # Row 1 fails to read for a moment while row 0 is unchanged: keep b1.
        f = make([5, 5])
        self.screen[0.0] = 5
        f._scan_panel()
        self.assertEqual(f._rows, {"b0": 0, "b1": 1})
        self.assertEqual(f.cfg["baits"][1]["count"], 5)

    def test_blank_scan_keeps_the_layout(self):
        f = make([5, 5])
        f._scan_panel()  # nothing readable
        self.assertEqual(f._rows, {"b0": 0, "b1": 1})
        self.assertEqual([b["count"] for b in f.cfg["baits"]], [5, 5])

    def test_select_retries_then_confirms(self):
        f = make([5])
        self.selected = [False, True]
        f._select_bait()
        self.assertEqual(self.clicks, [0.0, 0.0])

    def test_select_that_never_takes_stops_before_casting(self):
        # 2026-10-29: an unregistered click let a cast use the last Legendary bait.
        f = make([5])
        self.selected = [False, False]
        with self.assertRaises(fishing.StopRun) as ctx:
            f._select_bait()
        self.assertIn("did not select it", str(ctx.exception))

    def test_hidden_panel_does_not_stop(self):
        f = make([5])
        self.selected = [None]
        f._select_bait()
        self.assertEqual(self.clicks, [0.0])

    def test_unknown_count_mid_run_keeps_fishing(self):
        f = make([1, 1])
        self.screen.update({0.0: 1, 0.1: 5})
        f._read_all_baits()
        f._next_bait(select=True)
        del self.screen[0.1]  # Common's count can't be read after a catch
        f._use_bait()
        self.assertEqual(f.cfg["bait_index"], 1)
        self.assertIsNone(f.cfg["baits"][1]["count"])

    def test_panel_count_wins(self):
        f = make([10])
        self.screen[0.0] = 250
        f._use_bait()
        self.assertEqual(f.cfg["baits"][0]["count"], 250)

    def test_switches_when_panel_shows_last_one(self):
        f = make([40, 5])
        self.screen.update({0.0: 1, 0.1: 5})
        f._use_bait()
        self.assertEqual(f.cfg["bait_index"], 1)

    def test_start_reads_all_and_skips_empty(self):
        f = make([0, 0, 7])
        self.screen.update({0.0: 0, 0.1: 1, 0.2: 12})
        f._read_all_baits()
        f._next_bait(select=True)
        self.assertEqual(f.cfg["bait_index"], 2)
        self.assertEqual(f.cfg["baits"][2]["count"], 12)
        self.assertEqual(self.clicks, [0.2])

    def test_stale_zero_count_refreshed_at_start(self):
        f = make([0])
        self.screen[0.0] = 300
        f._read_all_baits()
        f._next_bait(select=True)
        self.assertEqual(f.cfg["baits"][0]["count"], 300)

    def test_skips_unticked_bait(self):
        f = make([2, 50, 9], use=[True, False, True])
        self.screen.update({0.0: 1, 0.2: 9})
        f._use_bait()
        self.assertEqual(f.cfg["bait_index"], 2)

    def test_unknown_count_keeps_fishing(self):
        f = make([None])
        f._use_bait()
        self.assertIsNone(f.cfg["baits"][0]["count"])
        self.assertEqual(f.cfg["bait_index"], 0)

    def test_out_of_bait_keeps_the_last_one(self):
        f = make([2])
        self.screen[0.0] = 1
        with self.assertRaises(fishing.OutOfBait):
            f._use_bait()
        self.assertEqual(f.cfg["baits"][0]["count"], 1)

    def test_check_ready_needs_a_ticked_bait(self):
        f = make([3], use=[False])
        self.assertIn("Tick at least one", fishing.check_ready(f.cfg))


class ItemTests(unittest.TestCase):
    def test_retries_until_banner_shows(self):
        f = make([10])
        grouper = fishing.Catch("Blue-Lip Grouper", "Common")
        reads = iter([(None, "no text"), (None, "no text"), (grouper, "New Item <Blue-Lip Grouper>")])
        with mock.patch.object(fishing, "read_new_item", side_effect=lambda: next(reads)), \
                mock.patch.object(fishing, "sleep_interruptible", return_value=False):
            self.assertEqual(f._look_for_item()[0], grouper)


class SpotTests(unittest.TestCase):
    def test_row_spots_follow_the_measured_layout(self):
        ys = [fishing.row_spot(k)["y"] for k in range(3)]
        self.assertAlmostEqual(ys[0], 0.742, places=3)
        self.assertAlmostEqual(ys[1] - ys[0], 0.0355, places=4)
        self.assertAlmostEqual(ys[2] - ys[1], 0.0355, places=4)
        self.assertEqual({fishing.row_spot(k)["x"] for k in range(3)}, {0.5})

    def test_selected_frame(self):
        # Gold frame above and below = selected (the user's screenshots).
        for name, want in (("panel3_legendary", True), ("panel3_rare", False), ("panel3_common", False),
                           ("bait_two_rows_common_x299", True), ("bait_two_rows_rare_x30", False),
                           ("bait_x296", True)):
            with self.subTest(name=name):
                self.assertIs(screen_text.row_selected(image(name)), want)
        self.assertIsNone(screen_text.row_selected(image("item_none")[:80, :560]))

    def test_computed_spots_read_their_own_rows(self):
        # Strips cut at the computed spots from the user's 3-row screenshot (2026-10-26).
        for name, count in (("Legendary Fish Bait", 33), ("Rare Fish Bait", 22), ("Common Fish Bait", 300)):
            with self.subTest(name=name):
                got, row = screen_text.read_count(image("panel3_" + name.split()[0].lower()))
                self.assertEqual(got, count, row)
                self.assertEqual(screen_text.row_bait(row, list(config.BAIT_TYPES)), name)


class BusoTests(unittest.TestCase):
    def test_presses_j_at_most_once_per_interval(self):
        f = make([10])
        f.cfg["use_buso"] = True
        presses = []
        clock = [1000.0]
        with mock.patch.object(fishing, "tap_key", side_effect=lambda k, **kw: presses.append(k)), \
                mock.patch.object(fishing.time, "monotonic", side_effect=lambda: clock[0]):
            for t in (1000.0, 1030.0, 1059.0, 1061.0, 1100.0, 1125.0):
                clock[0] = t
                f._buso()
        self.assertEqual(presses, ["j", "j", "j"])  # at 1000, 1061 and 1125

    def test_bait_read_does_not_reset_the_timer(self):
        # Bug on 2026-10-24: each successful bait read reset the timer, so J
        # was pressed after every catch.
        f = make([200])
        f.cfg["use_buso"] = True
        presses = []
        clock = [1000.0]
        with mock.patch.object(fishing, "tap_key", side_effect=lambda k, **kw: presses.append(k)), \
                mock.patch.object(fishing.time, "monotonic", side_effect=lambda: clock[0]), \
                mock.patch.object(fishing, "read_bait_count", return_value=(150, "x150")), \
                mock.patch.object(fishing, "row_spot", return_value={"x": 0.5, "y": 0.8}), \
                mock.patch.object(fishing, "click_point"):
            for t in (1000.0, 1020.0, 1040.0):  # a catch every 20 s
                clock[0] = t
                f._use_bait()
                f._buso()
        self.assertEqual(presses, ["j"])

    def test_off_by_default(self):
        f = make([10])
        with mock.patch.object(fishing, "tap_key") as tap:
            f._buso()
        tap.assert_not_called()


class OutOfBaitTests(unittest.TestCase):
    def test_goes_idle_instead_of_stopping(self):
        f = make([1])
        with mock.patch.object(f, "_focus"), mock.patch.object(f, "_read_all_baits"), \
                mock.patch.object(f, "_idle", return_value="idle"):
            self.assertEqual(f.run(), "idle")

    def _idle_presses(self, use_buso: bool) -> list:
        clock = [0.0]
        log = []

        def sleep(sec, abort=None):
            clock[0] += sec
            return False

        f = make([1])
        f.cfg["use_buso"] = use_buso
        f.abort = lambda: sum(1 for e in log if e[0] == "click") >= 6
        with mock.patch.object(fishing.time, "monotonic", side_effect=lambda: clock[0]), \
                mock.patch.object(fishing, "sleep_interruptible", side_effect=sleep), \
                mock.patch.object(fishing, "click_point", side_effect=lambda pt, **kw: log.append(("click", clock[0]))), \
                mock.patch.object(fishing, "tap_key", side_effect=lambda k, **kw: log.append((k, clock[0]))), \
                mock.patch.object(fishing, "roblox_running", return_value=True), \
                mock.patch.object(f, "_focus"), \
                mock.patch.object(f, "_check_connection"), \
                mock.patch.object(f.hooks, "event", side_effect=lambda k, c: log.append(("event", k))):
            self.assertEqual(f._idle(), "Stopped.")
        return log

    def test_idle_casts_reels_in_and_uses_haki(self):
        log = self._idle_presses(use_buso=True)
        every = config.ADVANCED_DEFAULTS["idle_every_sec"]
        clicks = [t for k, t in log if k == "click"]
        self.assertEqual(len(clicks), 6)
        casts = clicks[::2]
        self.assertEqual(clicks[1] - clicks[0], fishing.DECAST_AFTER_SEC)
        self.assertEqual(casts[1] - casts[0],
                         every + fishing.DECAST_AFTER_SEC + fishing.BUSO_SETTLE_SEC)
        # The cast, the reel-in click, then J once the reel-in is done; no
        # cast is counted as fishing.
        self.assertEqual([k for k, _ in log[:3]], ["click", "click", "j"])
        j_at = [t for k, t in log if k == "j"]
        self.assertEqual(j_at[0] - clicks[1], fishing.BUSO_SETTLE_SEC)
        self.assertNotIn("event", [k for k, _ in log])

    def test_idle_without_buso_never_presses_j(self):
        log = self._idle_presses(use_buso=False)
        self.assertNotIn("j", [k for k, _ in log])


class CatalogTests(unittest.TestCase):
    def test_saved_order_kept_unknown_dropped_missing_added(self):
        saved = [{"name": "Legendary Fish Bait", "use": True, "point": None, "count": 4},
                 {"name": "Bait 2", "use": True, "point": None, "count": 300},
                 {"name": "Common Fish Bait", "use": True, "point": {"x": 0.5, "y": 0.8}, "count": 295}]
        out = config._baits(saved)
        self.assertEqual([b["name"] for b in out], ["Legendary Fish Bait", "Common Fish Bait", "Rare Fish Bait"])
        self.assertEqual(out[1]["count"], 295)
        self.assertFalse(out[2]["use"])

    def test_bad_count_rejected(self):
        with self.assertRaises(config.ConfigError):
            config._baits([{"name": "Rare Fish Bait", "use": True, "point": None, "count": 400}])


if __name__ == "__main__":
    unittest.main()
