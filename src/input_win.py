"""Raw mouse and key events through SendInput (Windows). See input_mac for macOS.

Keys go as scan codes: Roblox reads the keyboard through Raw Input, which
ignores virtual-key-only events. Coordinates are physical screen pixels
(focus_win makes the process DPI aware).
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes

import focus_win  # noqa: F401 -- makes the process DPI aware before any coordinate is used

user32 = ctypes.WinDLL("user32", use_last_error=True)

INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_VIRTUALDESK = 0x4000
MOUSEEVENTF_ABSOLUTE = 0x8000
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008
SM_XVIRTUALSCREEN, SM_YVIRTUALSCREEN, SM_CXVIRTUALSCREEN, SM_CYVIRTUALSCREEN = 76, 77, 78, 79


class MOUSEINPUT(ctypes.Structure):
    _fields_ = (("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t))


class KEYBDINPUT(ctypes.Structure):
    _fields_ = (("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t))


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = (("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD), ("wParamH", wintypes.WORD))


class _INPUTUNION(ctypes.Union):
    _fields_ = (("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT))


class INPUT(ctypes.Structure):
    _fields_ = (("type", wintypes.DWORD), ("u", _INPUTUNION))


user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
user32.SendInput.restype = wintypes.UINT
user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
user32.GetCursorPos.restype = wintypes.BOOL
user32.GetSystemMetrics.argtypes = [ctypes.c_int]
user32.GetSystemMetrics.restype = ctypes.c_int

# Set 1 scan codes of a US keyboard. Windows maps them through the active
# layout, so a typed digit lands as that digit in a text box.
_SCAN_CODES = {
    "backspace": 0x0E,
    "1": 0x02, "2": 0x03, "3": 0x04, "4": 0x05, "5": 0x06, "6": 0x07, "7": 0x08, "8": 0x09,
    "9": 0x0A, "0": 0x0B, "q": 0x10, "w": 0x11, "e": 0x12, "r": 0x13, "t": 0x14, "y": 0x15,
    "u": 0x16, "i": 0x17, "o": 0x18, "p": 0x19, "a": 0x1E, "s": 0x1F, "d": 0x20, "f": 0x21,
    "g": 0x22, "h": 0x23, "j": 0x24, "k": 0x25, "l": 0x26, "z": 0x2C, "x": 0x2D, "c": 0x2E,
    "v": 0x2F, "b": 0x30, "n": 0x31, "m": 0x32,
}
KEY_NAMES = frozenset(k for k in _SCAN_CODES if len(k) == 1)


def _send(inp: INPUT) -> None:
    if user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT)) != 1:
        raise OSError(ctypes.get_last_error(), "SendInput was blocked; is Roblox running as administrator?")


def _mouse(flags: int, dx: int = 0, dy: int = 0) -> None:
    inp = INPUT(type=INPUT_MOUSE)
    inp.u.mi = MOUSEINPUT(dx, dy, 0, flags, 0, 0)
    _send(inp)


def absolute(x: float, y: float, vx: int, vy: int, vw: int, vh: int) -> tuple[int, int]:
    """Screen pixel to SendInput's 0-65535 range over the virtual desktop."""
    nx = round((float(x) - vx) * 65535 / max(1, vw - 1))
    ny = round((float(y) - vy) * 65535 / max(1, vh - 1))
    return max(0, min(65535, nx)), max(0, min(65535, ny))


def cursor_pos() -> tuple[float, float]:
    pt = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    return float(pt.x), float(pt.y)


def mouse_move(x: float, y: float, dragging: bool) -> None:
    # A held button turns a move into a drag by itself on Windows.
    m = user32.GetSystemMetrics
    nx, ny = absolute(x, y, m(SM_XVIRTUALSCREEN), m(SM_YVIRTUALSCREEN),
                      m(SM_CXVIRTUALSCREEN), m(SM_CYVIRTUALSCREEN))
    _mouse(MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE | MOUSEEVENTF_VIRTUALDESK, nx, ny)


def left_down() -> None:
    _mouse(MOUSEEVENTF_LEFTDOWN)


def left_up() -> None:
    _mouse(MOUSEEVENTF_LEFTUP)


def key_event(name: str, down: bool) -> None:
    code = _SCAN_CODES.get(str(name).lower())
    if code is None:
        raise ValueError(f"key {name!r} is not supported, use one of 0-9 or a-z")
    inp = INPUT(type=INPUT_KEYBOARD)
    inp.u.ki = KEYBDINPUT(0, code, KEYEVENTF_SCANCODE | (0 if down else KEYEVENTF_KEYUP), 0, 0)
    _send(inp)
