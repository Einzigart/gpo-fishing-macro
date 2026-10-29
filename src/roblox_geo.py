"""Convert between fractions of the Roblox window and screen points."""
from __future__ import annotations

from dataclasses import dataclass

import mss

from win_focus import roblox_window_rect


@dataclass(frozen=True)
class PixelRect:
    """A rectangle in screen points."""

    x: int
    y: int
    w: int
    h: int


_MSS = getattr(mss, "MSS", None) or mss.mss


@dataclass(frozen=True)
class CoordOrigin:
    x: int
    y: int
    w: int
    h: int
    source: str


def _monitor(index: int) -> PixelRect:
    with _MSS() as sct:
        m = sct.monitors[index]
        return PixelRect(int(m["left"]), int(m["top"]), max(1, int(m["width"])), max(1, int(m["height"])))


def virtual_screen_rect() -> PixelRect:
    """Bounding box of all displays."""
    return _monitor(0)


def roblox_client_rect() -> PixelRect | None:
    r = roblox_window_rect()
    if r is None:
        return None
    return PixelRect(r.x, r.y, r.w, r.h)


def resolve_origin() -> CoordOrigin:
    """The Roblox client area, or the main display when Roblox is not open."""
    client = roblox_client_rect()
    if client is not None:
        return CoordOrigin(client.x, client.y, client.w, client.h, "roblox")
    prim = _monitor(1)
    return CoordOrigin(prim.x, prim.y, prim.w, prim.h, "primary")


def point_to_screen(fx: float, fy: float, origin: CoordOrigin | None = None) -> tuple[int, int]:
    o = origin or resolve_origin()
    return int(round(o.x + float(fx) * o.w)), int(round(o.y + float(fy) * o.h))


def point_from_screen(sx: int, sy: int, origin: CoordOrigin | None = None) -> tuple[float, float]:
    o = origin or resolve_origin()
    return (sx - o.x) / max(o.w, 1), (sy - o.y) / max(o.h, 1)


def clamp_point(fx: float, fy: float) -> tuple[float, float]:
    return max(0.0, min(1.0, float(fx))), max(0.0, min(1.0, float(fy)))


def rect_to_screen(fx: float, fy: float, fw: float, fh: float, origin: CoordOrigin | None = None) -> PixelRect:
    o = origin or resolve_origin()
    return PixelRect(
        x=int(round(o.x + float(fx) * o.w)),
        y=int(round(o.y + float(fy) * o.h)),
        w=max(1, int(round(float(fw) * o.w))),
        h=max(1, int(round(float(fh) * o.h))),
    )
