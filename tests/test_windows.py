"""Windows port checks that run on any system (no Windows APIs are called)."""
import ast
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import ocr_win  # loads winrt only on first use, so it imports anywhere

SRC = Path(__file__).resolve().parents[1] / "src"


def public_names(module: str) -> set[str]:
    """Top-level functions, classes and constants a module defines, without importing it."""
    tree = ast.parse((SRC / f"{module}.py").read_text(encoding="utf-8"))
    names = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            names.update(t.id for t in node.targets if isinstance(t, ast.Name))
    return {n for n in names if not n.startswith("_")}


class ParityTests(unittest.TestCase):
    def test_platform_modules_match(self):
        # Each Windows module must give what the shared code imports from the macOS one.
        for mac, win, used in (
            ("focus_mac", "focus_win", {"WindowRect", "close_roblox", "find_roblox_hwnd", "focus_roblox",
                                        "focus_switched", "roblox_running", "roblox_window_rect"}),
            ("input_mac", "input_win", {"KEY_NAMES", "cursor_pos", "key_event", "left_down", "left_up",
                                        "mouse_move"}),
            ("ocr_mac", "ocr_win", {"recognize"}),
        ):
            with self.subTest(win=win):
                self.assertLessEqual(used, public_names(mac))
                self.assertLessEqual(used, public_names(win))

    def test_same_keys(self):
        def keys(module, table):
            tree = ast.parse((SRC / f"{module}.py").read_text(encoding="utf-8"))
            node = next(n for n in tree.body if isinstance(n, ast.Assign)
                        and any(getattr(t, "id", "") == table for t in n.targets))
            return set(ast.literal_eval(node.value))

        self.assertEqual(keys("input_mac", "_MAC_KEYCODES"), keys("input_win", "_SCAN_CODES"))


class OcrLineTests(unittest.TestCase):
    def test_words_make_a_line(self):
        words = [("Common", (10, 20, 60, 20)), ("Fish", (75, 20, 35, 20)), ("Bait", (115, 21, 35, 20)),
                 ("x296", (160, 19, 40, 22))]
        dist, text, span_box, box, alts = ocr_win.words_to_line(words, lambda t: None, height=60, scale=1.0)
        self.assertEqual(text, "Common Fish Bait x296")
        self.assertEqual(box, (10, 19, 200, 41))
        self.assertAlmostEqual(dist, abs(30 / 60 - 0.5))
        self.assertIsNone(span_box)
        self.assertEqual(alts, ())

    def test_boxes_map_back_from_the_upscale(self):
        words = [("x44", (100, 40, 60, 40))]
        _, _, _, box, _ = ocr_win.words_to_line(words, lambda t: None, height=50, scale=2.0)
        self.assertEqual(box, (50, 20, 80, 40))

    def test_item_name_box_covers_the_name_words(self):
        import screen_text

        words = [("New", (0, 0, 30, 10)), ("Item", (35, 0, 30, 10)), ("<Blue-Lip", (70, 0, 60, 10)),
                 ("Grouper>", (135, 0, 50, 10))]
        _, text, span_box, _, _ = ocr_win.words_to_line(words, screen_text._item_span, height=10, scale=1.0)
        self.assertEqual(text, "New Item <Blue-Lip Grouper>")
        self.assertEqual(span_box, (70, 0, 185, 10))

    def test_no_words(self):
        self.assertIsNone(ocr_win.words_to_line([], lambda t: None, height=10, scale=1.0))


if __name__ == "__main__":
    unittest.main()
