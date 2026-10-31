from __future__ import annotations

import ctypes
import ctypes.util
import threading
import time
from ctypes import Structure, c_double, c_int32, c_long, c_size_t, c_ubyte, c_uint32, c_void_p

import numpy as np

from win_focus import find_roblox_hwnd

LIST_ON_SCREEN = 1 << 0
LIST_INCLUDING_WINDOW = 1 << 3
IMAGE_NOMINAL = 1 << 4

ALPHA_FIRST = (2, 4, 6)
ORDER_MASK = 0x7000
ORDER_32_LITTLE = 2 << 12
COLOR_MODEL_RGB = 1

WINDOW_TTL_SEC = 1.0

_CG_PATHS = (
    "/System/Library/Frameworks/CoreGraphics.framework/Versions/A/CoreGraphics",
    "/System/Library/Frameworks/CoreGraphics.framework/Versions/Current/CoreGraphics",
    "/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics",
    "/System/Library/Frameworks/ApplicationServices.framework/Frameworks/CoreGraphics.framework/CoreGraphics",
)
_CF_PATHS = (
    "/System/Library/Frameworks/CoreFoundation.framework/Versions/A/CoreFoundation",
    "/System/Library/Frameworks/CoreFoundation.framework/Versions/Current/CoreFoundation",
    "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation",
)


class _Point(Structure):
    _fields_ = (("x", c_double), ("y", c_double))


class _Size(Structure):
    _fields_ = (("width", c_double), ("height", c_double))


class _Rect(Structure):
    _fields_ = (("origin", _Point), ("size", _Size))


def _open(paths, name):
    for path in paths:
        try:
            return ctypes.cdll.LoadLibrary(path)
        except OSError:
            continue
    found = ctypes.util.find_library(name)
    if found:
        return ctypes.cdll.LoadLibrary(found)
    raise OSError(f"{name} not found")


def _bind(lib, name, argtypes, restype):
    fn = getattr(lib, name)
    fn.argtypes = argtypes
    fn.restype = restype
    return fn


class _Lib:
    def __init__(self) -> None:
        cg = _open(_CG_PATHS, "CoreGraphics")
        cf = _open(_CF_PATHS, "CoreFoundation")
        self.create_image = _bind(cg, "CGWindowListCreateImage", [_Rect, c_uint32, c_uint32, c_uint32], c_void_p)
        self.width = _bind(cg, "CGImageGetWidth", [c_void_p], c_size_t)
        self.height = _bind(cg, "CGImageGetHeight", [c_void_p], c_size_t)
        self.bits_per_pixel = _bind(cg, "CGImageGetBitsPerPixel", [c_void_p], c_size_t)
        self.bits_per_component = _bind(cg, "CGImageGetBitsPerComponent", [c_void_p], c_size_t)
        self.bytes_per_row = _bind(cg, "CGImageGetBytesPerRow", [c_void_p], c_size_t)
        self.bitmap_info = _bind(cg, "CGImageGetBitmapInfo", [c_void_p], c_uint32)
        self.provider = _bind(cg, "CGImageGetDataProvider", [c_void_p], c_void_p)
        self.copy_data = _bind(cg, "CGDataProviderCopyData", [c_void_p], c_void_p)
        self.color_space = _bind(cg, "CGImageGetColorSpace", [c_void_p], c_void_p)
        self.space_model = _bind(cg, "CGColorSpaceGetModel", [c_void_p], c_int32)
        self.device_rgb = _bind(cg, "CGColorSpaceCreateDeviceRGB", [], c_void_p)
        self.bitmap_context = _bind(
            cg, "CGBitmapContextCreate",
            [c_void_p, c_size_t, c_size_t, c_size_t, c_size_t, c_void_p, c_uint32], c_void_p,
        )
        self.draw_image = _bind(cg, "CGContextDrawImage", [c_void_p, _Rect, c_void_p], None)
        self.context_release = _bind(cg, "CGContextRelease", [c_void_p], None)
        self.byte_ptr = _bind(cf, "CFDataGetBytePtr", [c_void_p], c_void_p)
        self.length = _bind(cf, "CFDataGetLength", [c_void_p], c_long)
        self.release = _bind(cf, "CFRelease", [c_void_p], None)
        self._rgb = None

    def rgb_space(self):
        if self._rgb is None:
            self._rgb = self.device_rgb()
        return self._rgb


_lib: _Lib | None = None
_lib_failed = False
_lock = threading.Lock()
_window = [0.0, None]


def _load() -> _Lib | None:
    global _lib, _lib_failed
    if _lib is None and not _lib_failed:
        with _lock:
            if _lib is None and not _lib_failed:
                try:
                    _lib = _Lib()
                except Exception:  # noqa: BLE001 -- any load failure means: use the mss fallback
                    _lib_failed = True
    return _lib


def _roblox_window() -> int | None:
    now = time.monotonic()
    if now - _window[0] > WINDOW_TTL_SEC:
        try:
            _window[1] = find_roblox_hwnd()
        except Exception:  # noqa: BLE001 -- no window id means: capture the whole screen area
            _window[1] = None
        _window[0] = now
    return _window[1]


def _forget_window() -> None:
    _window[0] = 0.0


def _read_direct(lib: _Lib, img) -> np.ndarray | None:
    iw, ih = int(lib.width(img)), int(lib.height(img))
    if lib.bits_per_pixel(img) != 32 or lib.bits_per_component(img) != 8:
        return None
    info = int(lib.bitmap_info(img))
    if (info & ORDER_MASK) != ORDER_32_LITTLE or (info & 0x1F) not in ALPHA_FIRST:
        return None
    data = lib.copy_data(lib.provider(img))
    if not data:
        return None
    try:
        ptr = lib.byte_ptr(data)
        n = int(lib.length(data))
        bpr = int(lib.bytes_per_row(img))
        if not ptr or bpr < iw * 4 or n < bpr * (ih - 1) + iw * 4:
            return None
        raw = np.ctypeslib.as_array((c_ubyte * n).from_address(ptr))
        view = np.lib.stride_tricks.as_strided(raw, shape=(ih, iw, 3), strides=(bpr, 4, 1))
        return np.array(view)
    finally:
        lib.release(data)


def _read_drawn(lib: _Lib, img) -> np.ndarray | None:
    iw, ih = int(lib.width(img)), int(lib.height(img))
    space = lib.color_space(img)
    if not space or lib.space_model(space) != COLOR_MODEL_RGB:
        space = lib.rgb_space()
    buf = np.zeros((ih, iw, 4), np.uint8)
    ctx = lib.bitmap_context(buf.ctypes.data, iw, ih, 8, iw * 4, space, 6 | ORDER_32_LITTLE)
    if not ctx:
        return None
    try:
        lib.draw_image(ctx, _Rect(_Point(0.0, 0.0), _Size(float(iw), float(ih))), img)
    finally:
        lib.context_release(ctx)
    return np.ascontiguousarray(buf[:, :, :3])


def _capture(lib: _Lib, rect: _Rect, option: int, window: int) -> np.ndarray | None:
    img = lib.create_image(rect, option, window, IMAGE_NOMINAL)
    if not img:
        return None
    try:
        if lib.width(img) == 0 or lib.height(img) == 0:
            return None
        frame = _read_direct(lib, img)
        if frame is None:
            frame = _read_drawn(lib, img)
        return frame
    finally:
        lib.release(img)


def grab(x: int, y: int, w: int, h: int) -> np.ndarray | None:
    lib = _load()
    if lib is None:
        return None
    rect = _Rect(_Point(float(x), float(y)), _Size(float(max(1, w)), float(max(1, h))))
    try:
        window = _roblox_window()
        if window:
            frame = _capture(lib, rect, LIST_INCLUDING_WINDOW, int(window))
            if frame is not None:
                return frame
            _forget_window()
        frame = _capture(lib, rect, LIST_ON_SCREEN, 0)
        return frame
    except Exception:  # noqa: BLE001 -- None tells the caller to use the mss fallback
        return None
