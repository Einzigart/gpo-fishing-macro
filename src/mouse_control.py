"""Synthetic left-mouse input: clicks with a cursor wiggle, and a held button."""
from __future__ import annotations

import random
import sys
import time

if sys.platform == "win32":
    from input_win import left_down as _raw_down
    from input_win import left_up as _raw_up
    from input_win import mouse_move
else:
    from input_mac import left_down as _raw_down
    from input_mac import left_up as _raw_up
    from input_mac import mouse_move

# Roblox ignores a click when the cursor teleports onto the target, so the
# cursor wiggles first. Values carried over from the Slayers 2 macro.
_WIGGLE_PX = (6, 12)
_WIGGLE_SEC = 0.04
_SETTLE_SEC = 0.09
_PRESS_SEC = 0.06

_down = False


def _move(x: float, y: float) -> None:
    mouse_move(x, y, _down)


def _left_down() -> None:
    global _down
    _raw_down()
    _down = True


def _left_up() -> None:
    global _down
    _raw_up()
    _down = False


def click_at(x: int, y: int) -> None:
    x, y = int(x), int(y)
    _move(x + random.randint(*_WIGGLE_PX), y + random.randint(*_WIGGLE_PX))
    time.sleep(_WIGGLE_SEC)
    _move(x - random.randint(*_WIGGLE_PX), y - random.randint(*_WIGGLE_PX))
    time.sleep(_WIGGLE_SEC)
    _move(x, y)
    time.sleep(_SETTLE_SEC)
    _left_down()
    time.sleep(_PRESS_SEC)
    _left_up()


class LeftClickController:
    """Hold or release the left button at the current cursor, with no duplicate events."""

    def __init__(self) -> None:
        self._held = False

    def set(self, want_hold: bool) -> None:
        if want_hold and not self._held:
            _left_down()
            self._held = True
        elif not want_hold and self._held:
            _left_up()
            self._held = False

    def release(self) -> None:
        self.set(False)
