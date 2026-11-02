"""Global hotkeys (pynput listener) and synthetic key presses (Quartz or SendInput)."""
from __future__ import annotations

import sys
import threading
from collections.abc import Callable

from pynput import keyboard as _pk

if sys.platform == "win32":
    from input_win import KEY_NAMES, key_event
else:
    from input_mac import KEY_NAMES, key_event

__all__ = ["KEY_NAMES", "add_hotkey", "key_press", "key_release", "unhook_all"]

_lock = threading.Lock()
_hotkeys: dict[str, Callable[[], None]] = {}
_listener: _pk.Listener | None = None


def key_press(name: str) -> None:
    key_event(name, True)


def key_release(name: str) -> None:
    key_event(name, False)


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
