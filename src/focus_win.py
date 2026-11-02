"""Find, measure and focus the Roblox window on Windows (Win32 through ctypes).

The same functions as focus_mac. Coordinates are physical screen pixels: the
process is made DPI aware at import, so window rects, mouse input, mss
captures and Tk all use one scale.
"""
from __future__ import annotations

import ctypes
import threading
import time
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)


def _make_dpi_aware() -> None:
    """Use physical pixels everywhere. Must run before any window or capture exists.

    Without it, Windows scales a 150% display and window rects, clicks and
    captures disagree by that factor.
    """
    try:
        # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 (Windows 10 1703+)
        if user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
            return
    except AttributeError:
        pass
    try:
        if ctypes.WinDLL("shcore").SetProcessDpiAwareness(2) == 0:  # per-monitor (Windows 8.1+)
            return
    except (AttributeError, OSError):
        pass
    try:
        user32.SetProcessDPIAware()
    except AttributeError:
        pass


_make_dpi_aware()

WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

user32.EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]
user32.EnumWindows.restype = wintypes.BOOL
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsWindowVisible.restype = wintypes.BOOL
user32.IsIconic.argtypes = [wintypes.HWND]
user32.IsIconic.restype = wintypes.BOOL
user32.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
user32.GetWindow.restype = wintypes.HWND
user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.GetWindowTextLengthW.restype = ctypes.c_int
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowTextW.restype = ctypes.c_int
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.GetWindowThreadProcessId.restype = wintypes.DWORD
user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.GetClientRect.restype = wintypes.BOOL
user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
user32.ClientToScreen.restype = wintypes.BOOL
user32.GetForegroundWindow.argtypes = []
user32.GetForegroundWindow.restype = wintypes.HWND
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.SetForegroundWindow.restype = wintypes.BOOL
user32.BringWindowToTop.argtypes = [wintypes.HWND]
user32.BringWindowToTop.restype = wintypes.BOOL
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.ShowWindow.restype = wintypes.BOOL
user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
user32.AttachThreadInput.restype = wintypes.BOOL
user32.keybd_event.argtypes = [wintypes.BYTE, wintypes.BYTE, wintypes.DWORD, ctypes.c_size_t]
user32.keybd_event.restype = None
kernel32.GetCurrentThreadId.argtypes = []
kernel32.GetCurrentThreadId.restype = wintypes.DWORD
kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
kernel32.CloseHandle.restype = wintypes.BOOL
kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                                ctypes.POINTER(wintypes.DWORD)]
kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
kernel32.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
kernel32.TerminateProcess.restype = wintypes.BOOL
kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
kernel32.WaitForSingleObject.restype = wintypes.DWORD
kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE

GW_OWNER = 4
SW_RESTORE = 9
VK_MENU = 0x12
KEYEVENTF_KEYUP = 0x0002
PROCESS_TERMINATE = 0x0001
SYNCHRONIZE = 0x00100000
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
WAIT_OBJECT_0 = 0
TH32CS_SNAPPROCESS = 0x00000002
INVALID_HANDLE_VALUE = wintypes.HANDLE(-1).value


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = (
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.c_size_t),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", ctypes.c_long),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", wintypes.WCHAR * 260),
    )


kernel32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
kernel32.Process32FirstW.restype = wintypes.BOOL
kernel32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
kernel32.Process32NextW.restype = wintypes.BOOL

# The game client from roblox.com, also when started through Bloxstrap. The
# Microsoft Store version runs as Windows10Universal.exe, a name other Store
# apps share, so it is only trusted together with a window titled "Roblox".
_ROBLOX_EXES = ("robloxplayerbeta.exe",)
_STORE_EXE = "windows10universal.exe"
_ROBLOX_TITLE = "roblox"


class WindowRect:
    __slots__ = ("h", "w", "x", "y")

    def __init__(self, x: int, y: int, w: int, h: int) -> None:
        self.x, self.y, self.w, self.h = int(x), int(y), int(w), int(h)


def _window_title(hwnd) -> str:
    n = user32.GetWindowTextLengthW(hwnd)
    if n <= 0:
        return ""
    buf = ctypes.create_unicode_buffer(n + 1)
    user32.GetWindowTextW(hwnd, buf, n + 1)
    return buf.value


def _window_pid(hwnd) -> int:
    pid = wintypes.DWORD(0)
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return int(pid.value)


def _exe_name(pid: int) -> str:
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return ""
    try:
        size = wintypes.DWORD(1024)
        buf = ctypes.create_unicode_buffer(size.value)
        if not kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return ""
        return buf.value.replace("/", "\\").rsplit("\\", 1)[-1].lower()
    finally:
        kernel32.CloseHandle(handle)


def _roblox_pids() -> list[int]:
    """Process ids of every running Roblox game client."""
    snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if not snap or snap == INVALID_HANDLE_VALUE:
        return []
    pids = []
    try:
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        ok = kernel32.Process32FirstW(snap, ctypes.byref(entry))
        while ok:
            if entry.szExeFile.lower() in _ROBLOX_EXES:
                pids.append(int(entry.th32ProcessID))
            ok = kernel32.Process32NextW(snap, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snap)
    return pids


def _find_roblox_window() -> int | None:
    """The Roblox game window (also when minimized), or None."""
    found: list[int] = []
    weak: list[int] = []

    def visit(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd) or user32.GetWindow(hwnd, GW_OWNER):
            return True
        # Browser tabs read "Roblox - <browser>", Studio "Roblox Studio": only an exact title counts.
        if _window_title(hwnd).strip().lower() != _ROBLOX_TITLE:
            return True
        exe = _exe_name(_window_pid(hwnd))
        if exe in _ROBLOX_EXES:
            found.append(int(hwnd))
            return False
        if exe == _STORE_EXE and not weak:
            weak.append(int(hwnd))
        return True

    user32.EnumWindows(WNDENUMPROC(visit), 0)
    if found:
        return found[0]
    return weak[0] if weak else None


def find_roblox_hwnd() -> int | None:
    """Return the window handle of the Roblox window, or None."""
    return _find_roblox_window()


_LAST_RECT_HOLD_SEC = 2.0
_last_rect: list = [None, 0.0]


def _client_rect(hwnd: int) -> WindowRect | None:
    if user32.IsIconic(hwnd):
        return None
    rc = wintypes.RECT()
    if not user32.GetClientRect(hwnd, ctypes.byref(rc)):
        return None
    origin = wintypes.POINT(0, 0)
    if not user32.ClientToScreen(hwnd, ctypes.byref(origin)):
        return None
    w, h = rc.right - rc.left, rc.bottom - rc.top
    if w < 32 or h < 32:
        return None
    return WindowRect(origin.x, origin.y, w, h)


def _query_roblox_window_rect() -> WindowRect | None:
    hwnd = _find_roblox_window()
    rect = _client_rect(hwnd) if hwnd else None
    if rect is None:
        held, seen = _last_rect
        if held is not None and time.perf_counter() - seen < _LAST_RECT_HOLD_SEC:
            return held
        return None
    _last_rect[0], _last_rect[1] = rect, time.perf_counter()
    return rect


_RECT_TTL = 0.2
_rect_lock = threading.Lock()
_rect_cache: list = [0.0, None]


def roblox_window_rect() -> WindowRect | None:
    """Client area of Roblox in screen pixels (frame and title bar removed), cached for 0.2 s."""
    now = time.monotonic()
    with _rect_lock:
        stamp, rect = _rect_cache
        if stamp and now - stamp < _RECT_TTL:
            return rect
    rect = _query_roblox_window_rect()
    with _rect_lock:
        _rect_cache[0], _rect_cache[1] = now, rect
    return rect


_focus_state = {"switched": False}


def focus_switched() -> bool:
    """True when the last focus_roblox() call had to bring Roblox to the front."""
    return _focus_state["switched"]


def roblox_running() -> bool:
    return bool(_roblox_pids()) or _find_roblox_window() is not None


def _is_front(hwnd: int) -> bool:
    return user32.GetForegroundWindow() == hwnd and not user32.IsIconic(hwnd)


def _bring_to_front(hwnd: int) -> None:
    """SetForegroundWindow, past Windows' focus-stealing guard.

    Windows lets only the process that owns the foreground, or that got the
    last input, change it. Joining the foreground thread's input queue
    usually passes; a synthetic Alt tap counts as that last input otherwise.
    """
    me = kernel32.GetCurrentThreadId()
    fg = user32.GetForegroundWindow()
    fg_thread = user32.GetWindowThreadProcessId(fg, None) if fg else 0
    attached = bool(fg_thread and fg_thread != me and user32.AttachThreadInput(me, fg_thread, True))
    try:
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
    finally:
        if attached:
            user32.AttachThreadInput(me, fg_thread, False)
    if user32.GetForegroundWindow() != hwnd:
        user32.keybd_event(VK_MENU, 0, 0, 0)
        user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)
        user32.SetForegroundWindow(hwnd)


def focus_roblox(wait_s: float = 2.0) -> bool:
    """Bring Roblox to the front, restoring it when minimized.

    Returns True when the Roblox window is the foreground window.
    """
    hwnd = _find_roblox_window()
    if hwnd is None:
        return False
    _focus_state["switched"] = False
    if _is_front(hwnd):
        return True
    _focus_state["switched"] = True
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)
    _bring_to_front(hwnd)
    # NOT MEASURED YET: how long a restore takes. Same settle time as on macOS.
    end = time.perf_counter() + max(0.0, wait_s)
    while time.perf_counter() < end:
        if _is_front(hwnd):
            time.sleep(0.3)
            return True
        time.sleep(0.05)
    return False


def close_roblox() -> bool:
    """Kill Roblox like End task in Task Manager. True only when it is gone."""
    pids = set(_roblox_pids())
    hwnd = _find_roblox_window()
    if hwnd:
        pids.add(_window_pid(hwnd))
    gone = True
    for pid in pids:
        handle = kernel32.OpenProcess(PROCESS_TERMINATE | SYNCHRONIZE, False, pid)
        if not handle:
            continue  # already gone, or not ours to end
        try:
            kernel32.TerminateProcess(handle, 1)
            # A killed process is normally gone at once; 3 s is generous.
            if kernel32.WaitForSingleObject(handle, 3000) != WAIT_OBJECT_0:
                gone = False
        finally:
            kernel32.CloseHandle(handle)
    return gone and not _roblox_pids()
