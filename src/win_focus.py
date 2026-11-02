"""Find, measure and focus the Roblox window, plus Tk overlay helpers.

The window and process parts are per platform: focus_mac (Quartz, AppKit) and
focus_win (Win32). Both give the same functions.
"""
from __future__ import annotations

import sys
import tkinter as tk

if sys.platform == "win32":
    from focus_win import (
        WindowRect,
        close_roblox,
        find_roblox_hwnd,
        focus_roblox,
        focus_switched,
        roblox_running,
        roblox_window_rect,
    )
else:
    from focus_mac import (
        WindowRect,
        close_roblox,
        find_roblox_hwnd,
        focus_roblox,
        focus_switched,
        roblox_running,
        roblox_window_rect,
    )

__all__ = [
    "WindowRect",
    "close_roblox",
    "detach_window",
    "find_roblox_hwnd",
    "focus_roblox",
    "focus_switched",
    "force_destroy_window",
    "keep_overlay_on_top",
    "pin_topmost_realised",
    "roblox_running",
    "roblox_window_rect",
    "style_overlay_window",
]


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
