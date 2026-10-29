"""Synthetic left-mouse input through Quartz events (macOS)."""
from __future__ import annotations

import random
import time

from Quartz import (
    CGEventCreate,
    CGEventCreateMouseEvent,
    CGEventGetLocation,
    CGEventPost,
    CGEventSetIntegerValueField,
    kCGEventLeftMouseDown,
    kCGEventLeftMouseDragged,
    kCGEventLeftMouseUp,
    kCGEventMouseMoved,
    kCGHIDEventTap,
    kCGMouseButtonLeft,
    kCGMouseEventClickState,
)

# Roblox ignores a click when the cursor teleports onto the target, so the
# cursor wiggles first. Values carried over from the Slayers 2 macro.
_WIGGLE_PX = (6, 12)
_WIGGLE_SEC = 0.04
_SETTLE_SEC = 0.09
_PRESS_SEC = 0.06

_down = False


def _cursor_pos() -> tuple[float, float]:
    loc = CGEventGetLocation(CGEventCreate(None))
    return float(loc.x), float(loc.y)


def _post(kind, x: float, y: float) -> None:
    ev = CGEventCreateMouseEvent(None, kind, (float(x), float(y)), kCGMouseButtonLeft)
    if kind in (kCGEventLeftMouseDown, kCGEventLeftMouseUp):
        CGEventSetIntegerValueField(ev, kCGMouseEventClickState, 1)
    CGEventPost(kCGHIDEventTap, ev)


def _move(x: float, y: float) -> None:
    _post(kCGEventLeftMouseDragged if _down else kCGEventMouseMoved, x, y)


def _left_down() -> None:
    global _down
    x, y = _cursor_pos()
    _post(kCGEventLeftMouseDown, x, y)
    _down = True


def _left_up() -> None:
    global _down
    x, y = _cursor_pos()
    _post(kCGEventLeftMouseUp, x, y)
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
