"""Interruptible clicks, key taps and sleeps used by the run loop."""
from __future__ import annotations

import time
from typing import Callable

from mouse_control import click_at
from platform_keys import key_press, key_release
from point_selector import FracPoint
from roblox_geo import point_to_screen

AbortFn = Callable[[], bool]


def sleep_interruptible(seconds: float, should_abort: AbortFn | None = None) -> bool:
    """Sleep in 20 ms steps. Returns True when should_abort fired."""
    end = time.perf_counter() + max(0.0, float(seconds))
    while time.perf_counter() < end:
        if should_abort is not None and should_abort():
            return True
        time.sleep(min(0.02, max(0.0, end - time.perf_counter())))
    return False


def click_point(pt: FracPoint, settle_s: float = 0.05, should_abort: AbortFn | None = None) -> bool:
    """Click a point given as fractions of the Roblox window. Returns True when aborted."""
    if should_abort is not None and should_abort():
        return True
    click_at(*point_to_screen(pt.x, pt.y))
    return sleep_interruptible(settle_s, should_abort)


def tap_key(key: str, hold_s: float = 0.1, should_abort: AbortFn | None = None) -> bool:
    """Press and release one key. Returns True when aborted."""
    if should_abort is not None and should_abort():
        return True
    key_press(key)
    try:
        return sleep_interruptible(hold_s, should_abort)
    finally:
        key_release(key)
