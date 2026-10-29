"""Find, measure and focus the Roblox window on macOS, plus Tk overlay helpers."""
from __future__ import annotations

import os
import signal
import subprocess
import threading
import time
import tkinter as tk

from AppKit import NSApplicationActivateIgnoringOtherApps, NSWorkspace

# Names are bound here, at import, on purpose. PyObjC loads a Quartz function on
# first attribute access, and that first load is not thread-safe: on 2026-10-24
# the UI and fishing threads loaded CGWindowListCopyWindowInfo at the same time
# and one got KeyError: 'CGWindowListCopyWindowInfo'.
from Quartz import (
    CGDisplayBounds,
    CGGetActiveDisplayList,
    CGWindowListCopyWindowInfo,
    kCGNullWindowID,
    kCGWindowListExcludeDesktopElements,
    kCGWindowListOptionOnScreenOnly,
)

_TITLE_HINTS = ("roblox",)


class WindowRect:
    __slots__ = ("x", "y", "w", "h")

    def __init__(self, x: int, y: int, w: int, h: int) -> None:
        self.x, self.y, self.w, self.h = int(x), int(y), int(w), int(h)


def _roblox_window_info() -> dict | None:
    opts = kCGWindowListOptionOnScreenOnly | kCGWindowListExcludeDesktopElements
    weak = None
    for info in CGWindowListCopyWindowInfo(opts, kCGNullWindowID) or []:
        if int(info.get("kCGWindowLayer", 0)) != 0:
            continue
        b = info.get("kCGWindowBounds") or {}
        if float(b.get("Width", 0)) < 32 or float(b.get("Height", 0)) < 32:
            continue
        owner = str(info.get("kCGWindowOwnerName", "") or "").strip().lower()
        title = str(info.get("kCGWindowName", "") or "").strip().lower()
        if owner in ("roblox", "robloxplayer"):
            return dict(info)
        if weak is None and any(h in owner + " " + title for h in _TITLE_HINTS):
            weak = dict(info)
    return weak


def find_roblox_hwnd() -> int | None:
    """Return the Quartz window number of the Roblox window, or None."""
    info = _roblox_window_info()
    return int(info["kCGWindowNumber"]) if info else None


_MAC_TITLE_H = 28
_LAST_RECT_HOLD_SEC = 2.0
_last_rect: list = [None, 0.0]


def _is_fullscreen(x: int, y: int, w: int, h: int) -> bool:
    _, ids, count = CGGetActiveDisplayList(16, None, None)
    for did in (ids or [])[:count]:
        d = CGDisplayBounds(did)
        if (abs(int(d.origin.x) - x) <= 1 and abs(int(d.origin.y) - y) <= 1
                and abs(int(d.size.width) - w) <= 1 and abs(int(d.size.height) - h) <= 1):
            return True
    return False


def _query_roblox_window_rect() -> WindowRect | None:
    info = _roblox_window_info()
    if not info:
        rect, seen = _last_rect
        if rect is not None and time.perf_counter() - seen < _LAST_RECT_HOLD_SEC:
            return rect
        return None
    b = info["kCGWindowBounds"]
    x, y = int(b["X"]), int(b["Y"])
    w, h = int(b["Width"]), int(b["Height"])
    title_h = 0 if _is_fullscreen(x, y, w, h) else _MAC_TITLE_H
    y, h = y + title_h, h - title_h
    if w < 32 or h < 32:
        return None
    rect = WindowRect(x, y, w, h)
    _last_rect[0], _last_rect[1] = rect, time.perf_counter()
    return rect


_RECT_TTL = 0.2
_rect_lock = threading.Lock()
_rect_cache: list = [0.0, None]


def roblox_window_rect() -> WindowRect | None:
    """Client area of Roblox in screen points (title bar removed), cached for 0.2 s."""
    now = time.monotonic()
    with _rect_lock:
        stamp, rect = _rect_cache
        if stamp and now - stamp < _RECT_TTL:
            return rect
    rect = _query_roblox_window_rect()
    with _rect_lock:
        _rect_cache[0], _rect_cache[1] = now, rect
    return rect


def _active_app_pid() -> int | None:
    try:
        asn = subprocess.run(["lsappinfo", "front"], capture_output=True,
                             text=True, timeout=2).stdout.strip()
        out = subprocess.run(["lsappinfo", "info", "-only", "pid", asn],
                             capture_output=True, text=True, timeout=2).stdout
        return int(out.strip().rsplit("=", 1)[-1])
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


_focus_state = {"switched": False}


def focus_switched() -> bool:
    """True when the last focus_roblox() call had to bring Roblox to the front."""
    return _focus_state["switched"]


def _roblox_app():
    """The running Roblox app, found even when its window is in another Space or minimized."""
    for app in NSWorkspace.sharedWorkspace().runningApplications():
        if str(app.localizedName() or "").strip().lower() in ("roblox", "robloxplayer"):
            return app
    return None


def roblox_running() -> bool:
    return _roblox_app() is not None


def focus_roblox(wait_s: float = 2.0) -> bool:
    """Bring Roblox to the front, switching to its Space when needed.

    Returns True when Roblox is the active app and its window is on screen.
    The window list only shows windows of the current Space, so the app is
    found through the running-apps list instead (2026-10-24: a full-screen
    GPO in its own Space read as "window not found").
    """
    app = _roblox_app()
    if app is None:
        return False
    pid = int(app.processIdentifier())
    _focus_state["switched"] = False
    if _active_app_pid() == pid and _roblox_window_info() is not None:
        return True
    _focus_state["switched"] = True
    app.activateWithOptions_(NSApplicationActivateIgnoringOtherApps)
    # A Space switch animates for about 0.7 s.
    end = time.perf_counter() + max(0.0, wait_s)
    while time.perf_counter() < end:
        if _active_app_pid() in (pid, None) and _roblox_window_info() is not None:
            time.sleep(0.3)
            return True
        time.sleep(0.05)
    return False


def close_roblox() -> bool:
    """Kill Roblox like Force Quit. True only when the process is gone.

    NSRunningApplication.forceTerminate() returned True but Roblox kept running
    (Slayers 2 macro, 2026-10-05), so the process is killed directly.
    """
    app = _roblox_app()
    if app is None:
        return True
    pid = int(app.processIdentifier())
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        return True
    # A killed process is normally gone at once; 3 s is generous.
    end = time.monotonic() + 3.0
    while time.monotonic() < end:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        time.sleep(0.05)
    return False


def detach_window(widget: tk.Misc) -> None:
    pass


def style_overlay_window(widget: tk.Misc) -> None:
    try:
        widget.update_idletasks()
        widget.attributes("-topmost", False)
        widget.attributes("-topmost", True)
    except tk.TclError:
        pass


def keep_overlay_on_top(widget: tk.Misc) -> None:
    try:
        widget.attributes("-topmost", True)
    except tk.TclError:
        pass


def pin_topmost_realised(widget: tk.Misc) -> None:
    style_overlay_window(widget)


def force_destroy_window(widget: tk.Misc | None) -> None:
    if widget is None:
        return
    try:
        widget.destroy()
    except tk.TclError:
        pass
