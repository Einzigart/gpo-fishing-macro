"""Raw mouse and key events through Quartz (macOS). See input_win for Windows."""
from __future__ import annotations

from Quartz import (
    CGEventCreate,
    CGEventCreateKeyboardEvent,
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

_MAC_KEYCODES = {
    "backspace": 51,
    "0": 29, "1": 18, "2": 19, "3": 20, "4": 21, "5": 23,
    "6": 22, "7": 26, "8": 28, "9": 25, "a": 0, "b": 11, "c": 8, "d": 2,
    "e": 14, "f": 3, "g": 5, "h": 4, "i": 34, "j": 38, "k": 40, "l": 37,
    "m": 46, "n": 45, "o": 31, "p": 35, "q": 12, "r": 15, "s": 1, "t": 17,
    "u": 32, "v": 9, "w": 13, "x": 7, "y": 16, "z": 6,
}
KEY_NAMES = frozenset(k for k in _MAC_KEYCODES if len(k) == 1)


def cursor_pos() -> tuple[float, float]:
    loc = CGEventGetLocation(CGEventCreate(None))
    return float(loc.x), float(loc.y)


def _post(kind, x: float, y: float) -> None:
    ev = CGEventCreateMouseEvent(None, kind, (float(x), float(y)), kCGMouseButtonLeft)
    if kind in (kCGEventLeftMouseDown, kCGEventLeftMouseUp):
        CGEventSetIntegerValueField(ev, kCGMouseEventClickState, 1)
    CGEventPost(kCGHIDEventTap, ev)


def mouse_move(x: float, y: float, dragging: bool) -> None:
    _post(kCGEventLeftMouseDragged if dragging else kCGEventMouseMoved, x, y)


def left_down() -> None:
    _post(kCGEventLeftMouseDown, *cursor_pos())


def left_up() -> None:
    _post(kCGEventLeftMouseUp, *cursor_pos())


def key_event(name: str, down: bool) -> None:
    code = _MAC_KEYCODES.get(str(name).lower())
    if code is None:
        raise ValueError(f"key {name!r} is not supported, use one of 0-9 or a-z")
    CGEventPost(kCGHIDEventTap, CGEventCreateKeyboardEvent(None, code, down))
