"""Detector for the Grand Piece Online fishing minigame.

The minigame shows two vertical bars:

* Control bar: a light-blue track with a dark gap. Holding left click moves
  the gap. A white horizontal line (the fish) crosses the track.
* Progress bar: a dark bar that fills with green from the bottom. Full means
  the fish is caught. Empty means it escapes.

All colour limits come from three GPO screenshots of a 2000x1258 Roblox
window, measured on 2026-10-24 (see tests/fixtures):
track blue RGB (87,170,254), gap and outline grey (24,24,24), sea (0,31,116),
night deck (47,25,21), character cape (143,165,203), fish line core (247,247,247),
progress green (171,255,127).
"""
from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

# Track blue: B 254, B-R 167. The cape (B 203, B-R 60) must fail.
BLUE_MIN_B = 225
BLUE_MIN_B_MINUS_R = 110
BLUE_MIN_G = 120
# Gap and outline: neutral grey, max 33, saturation <= 6. Deck (sat 26) must fail.
DARK_MAX = 50
DARK_MAX_SAT = 16
# Fish line: core 247; its faded edge is still >= 120 with saturation <= 30.
WHITE_MIN = 190
LIGHT_MIN = 120
LIGHT_MAX_SAT = 50
# Progress green: G 255, G-R 84, G-B 128.
GREEN_MIN_G = 200
GREEN_MIN_G_MINUS_R = 50
GREEN_MIN_G_MINUS_B = 80

# The bars move and scale with the camera, so the whole window is searched and
# the track is found by shape. Measured on 2026-10-24 over 7 full frames (night
# and day sea, two zoom levels) and the fixtures at 0.4x-2x:
#   track pieces: fill 0.78-0.85, height/width 7.6-15.3, dark outline 0.81-1.0
#   everything else: height/width <= 2.8, or fill 0.37 with no outline.
# A blue piece (the gap or the fish line can split the track) must be:
PIECE_MIN_H = 20
PIECE_MIN_ASPECT = 5
PIECE_MIN_FILL = 0.6
# Share of piece rows with the dark outline right beside it, on each side:
OUTLINE_MIN = 0.6
# Blue rows of the whole track (pieces joined) per px of width:
BAR_MIN_ASPECT = 8
# Width limits allow about 3x zoom out and 5x zoom in from the measured 11 px.
BAR_MIN_W, BAR_MAX_W = 3, 60
# Fish line light run measured 31-36 px across a 10-12 px track (about 3x).
# Text glyphs over the bar measured 2-4 px.
FISH_MIN_SPAN = 1.8
# Antialias rows between colours measured at 1-2 rows on an 11 px track.
# They grow with zoom, so the bridge is a share of the track width (min 3).
BRIDGE_PER_W = 0.3
BRIDGE_MIN = 3
# The progress bar sits about 5x the track width right of the track.
PROGRESS_REACH = 10


@dataclass(frozen=True)
class Reading:
    """One frame of the minigame, in pixel coordinates of the searched image."""

    bar_x0: int
    bar_x1: int
    track_top: int
    track_bot: int
    gap_top: int
    gap_bot: int
    fish_y: float
    progress: float | None

    @property
    def gap_y(self) -> float:
        return (self.gap_top + self.gap_bot) / 2.0

    @property
    def gap_h(self) -> int:
        return self.gap_bot - self.gap_top + 1


def _channels(bgr: np.ndarray) -> tuple[np.ndarray, ...]:
    b = bgr[:, :, 0].astype(np.int16)
    g = bgr[:, :, 1].astype(np.int16)
    r = bgr[:, :, 2].astype(np.int16)
    mn = np.minimum(np.minimum(b, g), r)
    mx = np.maximum(np.maximum(b, g), r)
    return b, g, r, mn, mx


def _runs(flags: np.ndarray) -> list[tuple[int, int]]:
    """Inclusive (start, end) index pairs of True runs."""
    d = np.diff(np.concatenate(([0], flags.astype(np.int8), [0])))
    return list(zip(np.where(d == 1)[0].tolist(), (np.where(d == -1)[0] - 1).tolist()))


def _bridge(w: int) -> int:
    return max(BRIDGE_MIN, round(BRIDGE_PER_W * w))


def _close(flags: np.ndarray, hole: int) -> np.ndarray:
    """Fill False holes of at most `hole` items that have True on both sides."""
    out = flags.copy()
    runs = _runs(~flags)
    for s, e in runs:
        if s > 0 and e < len(flags) - 1 and e - s + 1 <= hole:
            out[s:e + 1] = True
    return out


def _reach(flags: np.ndarray, start: int, step: int, bridge: int) -> int:
    """Last True index reached from `start` in direction `step`, crossing up to `bridge` False items."""
    last = i = start
    miss = 0
    while 0 <= i + step < len(flags):
        i += step
        if flags[i]:
            last, miss = i, 0
        else:
            miss += 1
            if miss > bridge:
                break
    return last


def _outlined(dark: np.ndarray, x: int, y: int, w: int, h: int) -> bool:
    """True when dark outline pixels sit right beside the piece on both sides."""
    k = max(2, w // 4)
    left = dark[y:y + h, max(0, x - k - 1):x]
    right = dark[y:y + h, x + w:x + w + k + 1]
    if left.shape[1] == 0 or right.shape[1] == 0:
        return False
    return left.any(axis=1).mean() >= OUTLINE_MIN and right.any(axis=1).mean() >= OUTLINE_MIN


def _track(blue: np.ndarray, dark: np.ndarray) -> tuple[int, int, int, int, int] | None:
    """(x0, x1, y0, y1, blue rows) of the most track-like set of blue pieces."""
    n, _, st, _ = cv2.connectedComponentsWithStats(blue.view(np.uint8), connectivity=8)
    pieces = []
    for i in range(1, n):
        x, y, w, h, area = (int(v) for v in st[i])
        if (BAR_MIN_W <= w <= BAR_MAX_W and h >= PIECE_MIN_H and h >= PIECE_MIN_ASPECT * w
                and area >= PIECE_MIN_FILL * w * h and _outlined(dark, x, y, w, h)):
            pieces.append([x, x + w - 1, y, y + h - 1, h])
    tracks: list[list[int]] = []
    for p in sorted(pieces):
        for t in tracks:
            # Pieces of one track share columns: the gap or fish line split it.
            if min(t[1], p[1]) - max(t[0], p[0]) + 1 >= 0.5 * min(t[1] - t[0], p[1] - p[0]) + 1:
                t[0], t[1] = min(t[0], p[0]), max(t[1], p[1])
                t[2], t[3] = min(t[2], p[2]), max(t[3], p[3])
                t[4] += p[4]
                break
        else:
            tracks.append(list(p))
    tracks = [t for t in tracks if t[4] >= BAR_MIN_ASPECT * (t[1] - t[0] + 1)]
    return tuple(max(tracks, key=lambda t: t[4])) if tracks else None


class Detector:
    """Finds the control bar, gap, fish line and progress in a game frame.

    Keeps the gap height from the last frame where blue bounded the gap on
    both sides, so a gap pressed against a track end is not stretched by dark
    background beyond the track.
    """

    def __init__(self) -> None:
        self.last = ""
        self.gap_h: int | None = None

    def reset(self) -> None:
        self.gap_h = None

    def find(self, bgr: np.ndarray) -> Reading | None:
        b, g, r, mn, mx = _channels(bgr)

        blue = (b >= BLUE_MIN_B) & (b - r >= BLUE_MIN_B_MINUS_R) & (g >= BLUE_MIN_G)
        dark_px = (mx <= DARK_MAX) & (mx - mn <= DARK_MAX_SAT)
        track = _track(blue, dark_px)
        if track is None:
            self.last = "no fishing bar on screen (no tall blue strip with a dark outline)"
            return None
        x0, x1, y0, y1, _ = track
        w = x1 - x0 + 1

        core = slice(x0 + w // 4, x1 + 1 - w // 4)
        white_px = (mn >= WHITE_MIN) & (mx - mn <= LIGHT_MAX_SAT)
        blue_row = blue[:, core].mean(axis=1) >= 0.5
        dark_row = dark_px[:, core].mean(axis=1) >= 0.5
        white_row = white_px[:, core].mean(axis=1) >= 0.5

        # The gap may sit at a track end, so extend over dark or white rows.
        bridge = _bridge(w)
        gapish = _close(dark_row | white_row, bridge)
        inside = blue_row | gapish
        top = _reach(inside, y0, -1, bridge)
        bot = _reach(inside, y1, 1, bridge)

        gaps = [(s, e) for s, e in _runs(gapish[top:bot + 1])]
        if not gaps:
            self.last = "track found, no dark gap"
            return None
        s, e = max(gaps, key=lambda se: se[1] - se[0])
        gap_top, gap_bot = top + s, top + e
        at_top, at_bot = gap_top == top, gap_bot == bot
        if not (at_top or at_bot):
            self.gap_h = gap_bot - gap_top + 1
        elif self.gap_h is not None:
            if at_bot and not at_top:
                gap_bot = min(gap_bot, gap_top + self.gap_h - 1)
            elif at_top and not at_bot:
                gap_top = max(gap_top, gap_bot - self.gap_h + 1)

        fish = self._fish(mn, mx, white_row, x0, x1, top, bot)
        if fish is None:
            self.last = "track and gap found, no fish line"
            return None

        progress = self._progress(g, r, b, dark_px, x1, w)
        self.last = "found"
        return Reading(x0, x1, top, bot, gap_top, gap_bot, fish, progress)

    @staticmethod
    def _fish(mn, mx, white_row, x0, x1, top, bot) -> float | None:
        """Centre row of the widest white line that crosses the track."""
        light = (mn >= LIGHT_MIN) & (mx - mn <= LIGHT_MAX_SAT)
        cx = (x0 + x1) // 2
        need = FISH_MIN_SPAN * (x1 - x0 + 1)
        best = None
        for s, e in _runs(white_row[top:bot + 1]):
            y = top + (s + e) // 2
            row = light[y]
            left = cx
            while left > 0 and row[left - 1]:
                left -= 1
            right = cx
            while right < len(row) - 1 and row[right + 1]:
                right += 1
            span = right - left + 1
            if span >= need and (best is None or span > best[0]):
                best = (span, top + (s + e) / 2.0)
        return None if best is None else best[1]

    @staticmethod
    def _progress(g, r, b, dark_px, x1, w) -> float | None:
        """Green share of the progress bar right of the track, or None if not seen."""
        lo, hi = x1 + 1, min(g.shape[1], x1 + 1 + PROGRESS_REACH * w)
        if lo >= hi:
            return None
        green = ((g >= GREEN_MIN_G) & (g - r >= GREEN_MIN_G_MINUS_R)
                 & (g - b >= GREEN_MIN_G_MINUS_B))[:, lo:hi]
        counts = green.sum(axis=0)
        if counts.max(initial=0) < 2:
            return None
        cols = _runs(counts >= 0.5 * counts.max())
        c0, c1 = max(cols, key=lambda se: int(counts[se[0]:se[1] + 1].sum()))
        col = lo + (c0 + c1) // 2
        fill = _runs(green[:, col - lo])
        g0, g1 = max(fill, key=lambda se: se[1] - se[0])
        # The fill starts at the bar bottom, so the bar spans from its dark top
        # to g1. The walk up crosses the lime tick line on top of the fill.
        top = _reach(dark_px[:, col] | green[:, col - lo], g0, -1, _bridge(w))
        return (g1 - g0 + 1) / float(g1 - top + 1)
