"""Global hotkeys (pynput listener) and synthetic key presses (Quartz) on macOS."""
from __future__ import annotations

import threading
from typing import Callable

from pynput import keyboard as _pk
from Quartz import CGEventCreateKeyboardEvent, CGEventPost, kCGHIDEventTap

_lock = threading.Lock()
_hotkeys: dict[str, Callable[[], None]] = {}
_listener: _pk.Listener | None = None

_MAC_KEYCODES = {
    "backspace": 51,
    "0": 29, "1": 18, "2": 19, "3": 20, "4": 21, "5": 23,
    "6": 22, "7": 26, "8": 28, "9": 25, "a": 0, "b": 11, "c": 8, "d": 2,
    "e": 14, "f": 3, "g": 5, "h": 4, "i": 34, "j": 38, "k": 40, "l": 37,
    "m": 46, "n": 45, "o": 31, "p": 35, "q": 12, "r": 15, "s": 1, "t": 17,
    "u": 32, "v": 9, "w": 13, "x": 7, "y": 16, "z": 6,
}
KEY_NAMES = frozenset(k for k in _MAC_KEYCODES if len(k) == 1)


def _post_key(name: str, down: bool) -> None:
    code = _MAC_KEYCODES.get(str(name).lower())
    if code is None:
        raise ValueError(f"key {name!r} is not supported, use one of 0-9 or a-z")
    CGEventPost(kCGHIDEventTap, CGEventCreateKeyboardEvent(None, code, down))


def key_press(name: str) -> None:
    _post_key(name, True)


def key_release(name: str) -> None:
    _post_key(name, False)


def _on_press(key) -> None:
    name = (getattr(key, "name", "") or "").upper()
    with _lock:
        cb = _hotkeys.get(name)
    if cb is not None:
        cb()


def add_hotkey(name: str, callback: Callable[[], None]) -> None:
    """Call callback on a global key press. Name is a pynput key name such as "F1"."""
    global _listener
    with _lock:
        _hotkeys[name.upper()] = callback
    if _listener is None or not _listener.is_alive():
        _listener = _pk.Listener(on_press=_on_press)
        _listener.daemon = True
        _listener.start()


def unhook_all() -> None:
    global _listener
    with _lock:
        _hotkeys.clear()
    if _listener is not None:
        _listener.stop()
        _listener = None
