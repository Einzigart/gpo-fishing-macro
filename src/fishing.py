"""The fishing run loop: select bait, cast, play the minigame, repeat.

GPO puts the catch straight into the inventory, so there is no collect step.
The loop runs on a worker thread and talks to the UI only through `Hooks`.
"""
from __future__ import annotations

import sys
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass

import cv2
import mss
import numpy as np

import mac_grab
from config import BAIT_MAX, BAIT_TYPES, CONFIG_PATH
from detect import PROGRESS_REACH, Detector, Reading
from input_actions import click_point, sleep_interruptible, tap_key
from mouse_control import LeftClickController, click_at
from point_selector import FracPoint
from roblox_geo import PixelRect, resolve_origin, roblox_client_rect
from screen_text import (
    DISCONNECT_AREA,
    SHOP_AREA,
    area_rect,
    disconnected_text,
    item_rect,
    read_count,
    read_item,
    row_bait,
    row_selected,
    shop_max,
    strip_rect,
    text_boxes,
)
from track_control import TrackController
from win_focus import close_roblox, focus_roblox, roblox_running

AbortFn = Callable[[], bool]

_MSS = getattr(mss, "MSS", None) or mss.mss
cv2.setNumThreads(1)

# Recovery when casts get no bite: reselect bait after every miss and re-equip
# the rod every this many misses in a row. The run never stops on misses: a
# stop on 2026-10-24 left the game idle until Roblox kicked the player for AFK,
# and each recast is input that prevents that.
REEQUIP_AFTER_MISSES = 3
# A picture of the game is saved on each cast with no bite, to see why it
# happened (2026-10-24: bites stopped mid-run and the log could not say why).
SNAPSHOT_DIR = CONFIG_PATH.parent / "no-bite-snapshots"
SNAPSHOT_KEEP = 20
# The bars hang beside the character, so they move and scale with the camera.
# The whole Roblox window is searched until they are found, at this rate (a full
# search measured 5-16 ms on 2026-10-24, plus the capture); after that only a
# box around them is read, at the full scan rate.
SEARCH_FPS = 15.0
# Box around found bars: track widths left and right (the progress bar sits
# within PROGRESS_REACH widths to the right), track lengths above and below.
BOX_LEFT_WIDTHS = 4
BOX_RIGHT_WIDTHS = PROGRESS_REACH + 4
BOX_PAD_TRACKS = 0.3
# Release the button when the bars vanish for this long (from the Slayers macro).
RELEASE_WHEN_LOST_SEC = 0.3
# How long to look for the "New Item" banner after the bars vanish.
# NOT MEASURED YET: the banner was still up in both after-catch screenshots.
ITEM_LOOK_SEC = 2.0
ITEM_LOOK_GAP_SEC = 0.25
# Bait count reads: tries per read and the gap between them. A read that
# agrees at once stops early, so more tries cost time only on bad reads.
# NOT MEASURED YET: the count text may animate for a moment after it changes.
COUNT_READ_TRIES = 5
COUNT_READ_GAP_SEC = 0.4
# Tries per panel row when mapping the rows by name. The scan ends at the
# first row that never reads, so each try there costs a full read.
SCAN_READ_TRIES = 3
# Equal reads needed before a count is trusted. A count at or below
# KEEP_LAST_BAIT ends the bait (switch, or anti-AFK idle when it is the last
# one), so a wrong low read does the most harm and needs more reads.
COUNT_AGREE = 2
LOW_COUNT_AGREE = 3
# Auto-buy: only Common Fish Bait is sold by an NPC (wiki, 2026-10-24).
COMMON_BAIT = "Common Fish Bait"
# NOT MEASURED YET: how fast each step of the seller's dialog appears, and how
# long the purchase takes to land in the bait panel.
SHOP_STEP_WAIT_SEC = 4.0
SHOP_POLL_SEC = 0.3
SHOP_AFTER_SEC = 1.0
# The seller's dialog darkens the game behind it. In the three shop fixtures
# (screenshots of 2026-10-25, measured 2026-11-02) the deck read 39-65 grey
# inside it and 108-139 just outside, about 0.45x. The dialog counts as open
# while the band between its question and Yes/No is below this share of the
# band's brightness before E. A scene that is dark already (night) may not dim
# this much; then the dialog is left open and the run says so.
SHOP_DIM_RATIO = 0.75
# The "Fishing Baits" panel lists only the baits the player owns, one row each,
# from the top. Measured on 2026-10-26 in 3-, 2- and 1-row screenshots of two
# window sizes: rows centred across, the first at 74.1-74.2% down, each next
# 3.55-3.6% lower. Which bait sits in which row is read from the row names.
PANEL_ROW_X = 0.5
PANEL_FIRST_ROW_Y = 0.742
PANEL_ROW_STEP = 0.0355
# Bait selection: clicks per try, and the wait before checking the gold frame.
# NOT MEASURED YET: how fast the frame moves after a click.
SELECT_TRIES = 2
SELECT_SETTLE_SEC = 0.5
# The user keeps the last bait of each type and wants anti-AFK casts once
# it is reached (2026-10-24).
KEEP_LAST_BAIT = 1
# NOT MEASURED YET: how soon after a cast a click reels the line back in.
# Bites came 9-11 s after a cast, so 1 s is far from one.
DECAST_AFTER_SEC = 1.0
# NOT MEASURED YET: pause after the anti-AFK reel-in before J, so the reel-in
# animation has ended. 0.5 s was too short (2026-10-24).
BUSO_SETTLE_SEC = 1.0
# Buso Haki (armament) toggles with J in GPO (user report, 2026-10-24).
BUSO_KEY = "j"
# The fill is full on a catch and empty on an escape, so the midpoint splits them.
CAUGHT_PROGRESS = 0.5
REEQUIP_GAP_SEC = 0.7


@dataclass(frozen=True)
class Catch:
    name: str
    rarity: str  # "Common", "Rare", "Legendary" or "unknown (<colour>)"


@dataclass
class Hooks:
    """Callbacks from the worker thread. The UI must marshal them to Tk."""

    status: Callable[[str], None]
    # "cast", "bite", "caught", "lost", "unclear", "timeout"; a Catch only with "caught".
    event: Callable[[str, Catch | None], None]
    frame: Callable[[np.ndarray, Reading | None], None]  # scan-area BGR frame
    bait_changed: Callable[[], None]


class StopRun(Exception):
    """Ends the run with a message for the user."""


class Disconnected(StopRun):
    """Roblox showed its "Disconnected" dialog; Roblox has been closed."""


class OutOfBait(StopRun):
    """Every ticked bait is down to KEEP_LAST_BAIT."""


def bar_box(reading: Reading, rect: PixelRect, window: PixelRect) -> PixelRect:
    """Screen box around the bars found in `rect`, clamped to the Roblox window.

    The box holds the track, the progress bar to its right, and room for the
    bars to move between frames.
    """
    w = reading.bar_x1 - reading.bar_x0 + 1
    pad_y = int(BOX_PAD_TRACKS * (reading.track_bot - reading.track_top + 1))
    x0 = max(window.x, rect.x + reading.bar_x0 - BOX_LEFT_WIDTHS * w)
    x1 = min(window.x + window.w, rect.x + reading.bar_x1 + 1 + BOX_RIGHT_WIDTHS * w)
    y0 = max(window.y, rect.y + reading.track_top - pad_y)
    y1 = min(window.y + window.h, rect.y + reading.track_bot + 1 + pad_y)
    return PixelRect(x0, y0, max(1, x1 - x0), max(1, y1 - y0))


def grab(rect: PixelRect, sct) -> np.ndarray:
    """BGR capture of a screen rect in points, from the Roblox window only when possible."""
    frame = mac_grab.grab(rect.x, rect.y, rect.w, rect.h)
    if frame is None:
        shot = sct.grab({"left": rect.x, "top": rect.y, "width": rect.w, "height": rect.h})
        frame = np.asarray(shot, dtype=np.uint8)[:, :, :3]
    if frame.shape[0] != rect.h or frame.shape[1] != rect.w:
        frame = cv2.resize(frame, (rect.w, rect.h), interpolation=cv2.INTER_AREA)
    return np.ascontiguousarray(frame)


def _backdrop_band(rect: PixelRect, ask: dict) -> tuple[int, int, int, int]:
    """The middle of the dialog backdrop, between the question and Yes/No, in `rect` pixels."""
    (yes_x, yes_y), (no_x, _), (_, q_y) = ask["yes"][1], ask["no"][1], ask["question"][1]
    gap = yes_y - q_y
    return (yes_x - rect.x, int(q_y + 0.3 * gap) - rect.y, no_x - rect.x, int(q_y + 0.7 * gap) - rect.y)


def _dimmed(image: np.ndarray, before: np.ndarray, band: tuple[int, int, int, int]) -> bool:
    """Whether `band` is darker in `image` than in `before` by SHOP_DIM_RATIO."""
    x0, y0, x1, y1 = band
    return image[y0:y1, x0:x1].mean() < SHOP_DIM_RATIO * before[y0:y1, x0:x1].mean()


def bait_selected(point: dict) -> bool | None:
    """Whether the panel row at `point` shows the gold "selected" frame (None: no row seen)."""
    with _MSS() as sct:
        image = grab(strip_rect(point, resolve_origin()), sct)
    return row_selected(image)


def read_bait_count(point: dict) -> tuple[int | None, str]:
    """(Bait count or None, text of the panel row at `point`; "" when none was read)."""
    with _MSS() as sct:
        image = grab(strip_rect(point, resolve_origin()), sct)
    return read_count(image)


def read_new_item() -> tuple[Catch | None, str]:
    """The catch in the "New Item" banner, and the text read (or why it failed)."""
    with _MSS() as sct:
        image = grab(item_rect(resolve_origin()), sct)
    name, rarity, text = read_item(image)
    return (Catch(name, rarity) if name else None), text


def row_spot(k: int) -> dict:
    """Centre of row k (0 = top) of the "Fishing Baits" panel, as window fractions."""
    return {"x": PANEL_ROW_X, "y": PANEL_FIRST_ROW_Y + PANEL_ROW_STEP * k}


def _pt(raw: dict) -> FracPoint:
    return FracPoint(float(raw["x"]), float(raw["y"]))


def check_ready(cfg: dict) -> str | None:
    """Reason the run cannot start, or None."""
    if not cfg["cast_point"]:
        return "Set the cast point first."
    if not any(b["use"] for b in cfg["baits"]):
        return "Tick at least one bait to use."
    return None


def _has_stock(bait: dict) -> bool:
    return bait["use"] and (bait["count"] is None or bait["count"] > KEEP_LAST_BAIT)


def reads_needed(count: int, expect: set[int] | None) -> int:
    """How many equal reads of `count` make it trusted.

    An expected count needs one read, or two when it ends the bait. Any
    other count needs COUNT_AGREE, or LOW_COUNT_AGREE when it ends the bait.
    """
    low = count <= KEEP_LAST_BAIT
    if expect is not None and count in expect:
        return 2 if low else 1
    return LOW_COUNT_AGREE if low else COUNT_AGREE


class Fisher:
    def __init__(self, cfg: dict, hooks: Hooks, should_abort: AbortFn) -> None:
        self.cfg = cfg
        self.adv = cfg["advanced"]
        self.hooks = hooks
        self.abort = should_abort
        self.detector = Detector()
        self.tracker = TrackController()
        self.click = LeftClickController()
        self._read_ok = True
        self._buso_at: float | None = None
        self._rows: dict[str, int] = {}  # bait name -> panel row, from _scan_panel
        self.disconnected = False

    def run(self) -> str:
        """Fish until stopped. Returns the reason the run ended.

        Sets `self.disconnected` when the run ended because Roblox
        disconnected; Roblox is closed by then.
        """
        try:
            return self._fish()
        except OutOfBait:
            try:
                return self._idle()
            except StopRun as exc:
                return str(exc)
        except StopRun as exc:
            return str(exc)
        finally:
            self.click.release()

    def _fish(self) -> str:
        self._focus()
        self._read_all_baits()
        self.cfg["bait_index"] = 0
        self._next_bait(select=True)
        misses = 0
        while not self.abort():
            if not roblox_running():
                raise StopRun("Roblox closed.")
            self._focus()
            self._cast()
            outcome = self._play()
            if outcome == "aborted":
                break
            if outcome == "none":
                misses += 1
                self._check_connection()
                self._snapshot()
                hint = (" Check that nothing covers the cast spot and that the bait is selected."
                        if misses >= REEQUIP_AFTER_MISSES else "")
                self.hooks.status(f"No bite ({misses} in a row), reselecting bait and casting again.{hint}")
                if misses % REEQUIP_AFTER_MISSES == 0:
                    self._reequip()
                self._select_bait()
                continue
            misses = 0
            catch, why = self._look_for_item()
            if catch is not None:
                outcome = "caught"  # The banner is proof, whatever the catch meter showed.
            elif outcome == "caught":
                self.hooks.status(f"Caught a fish, but could not read its name: {why}.")
            self.hooks.event(outcome, catch)
            self._use_bait()
            if outcome == "caught":
                self._buso()
            self.hooks.status("Waiting before the next cast...")
            if sleep_interruptible(self.adv["after_catch_sec"], self.abort):
                break
        return "Stopped."

    def buy_once(self) -> str:
        """Run the Common Fish Bait purchase once (the Test buy button). Returns what happened."""
        try:
            why = self._buy_common()
            if why is not None:
                return f"Test buy failed: {why}."
            common = next(b for b in self.cfg["baits"] if b["name"] == COMMON_BAIT)
            self._scan_panel()
            self._set_count(common, None)
            self.hooks.bait_changed()
            n = common["count"]
            return f"Test buy done. {COMMON_BAIT}: {'count unknown' if n is None else f'{n} left'}."
        except StopRun as exc:
            return str(exc)

    def _check_connection(self) -> None:
        """Close Roblox and end the run when its "Disconnected" dialog shows."""
        window = roblox_client_rect()
        if window is None:
            return
        with _MSS() as sct:
            image = grab(area_rect(DISCONNECT_AREA, resolve_origin()), sct)
        text = disconnected_text(image)
        if text is None:
            return
        self.disconnected = True
        closed = close_roblox()
        raise Disconnected(f"Roblox disconnected ({text}). "
                           + ("Closed Roblox." if closed else "Could not close Roblox; quit it by hand."))

    def _restock(self) -> bool:
        """Buy Common Fish Bait when that is on; True when Common now has stock."""
        if not self.cfg["auto_buy_common"]:
            return False
        baits = self.cfg["baits"]
        i = next((j for j, b in enumerate(baits) if b["name"] == COMMON_BAIT), None)
        if i is None or not baits[i]["use"]:
            self.hooks.status("Auto-buy needs Common Fish Bait ticked.")
            return False
        why = self._buy_common()
        if why is not None:
            self.hooks.status(f"Could not buy {COMMON_BAIT}: {why}.")
            return False
        # A first Common purchase adds its row, so map the panel again.
        self._scan_panel()
        self._set_count(baits[i], None)
        self.hooks.bait_changed()
        if not _has_stock(baits[i]):
            self.hooks.status(f"Bought {COMMON_BAIT}, but the panel still shows {baits[i]['count']}.")
            return False
        n = baits[i]["count"]
        self.hooks.status(f"Bought {COMMON_BAIT}; {'count unknown' if n is None else f'{n} left'}.")
        self.cfg["bait_index"] = i
        self._select_bait()
        return True

    def _shop_image(self) -> tuple[PixelRect, np.ndarray]:
        """The seller's dialog area: its screen rect and a capture of it."""
        rect = area_rect(SHOP_AREA, resolve_origin())
        with _MSS() as sct:
            return rect, grab(rect, sct)

    def _shop_wait(self, read: Callable[[PixelRect, np.ndarray], object]) -> object:
        """Capture the seller's dialog area until `read(rect, image)` is not None.

        Returns that result, or None after SHOP_STEP_WAIT_SEC.
        """
        end = time.monotonic() + SHOP_STEP_WAIT_SEC
        while not self.abort():
            found = read(*self._shop_image())
            if found is not None:
                return found
            if time.monotonic() >= end:
                return None
            sleep_interruptible(SHOP_POLL_SEC, self.abort)
        return None

    def _shop_find(self, want: dict[str, Callable[[str], bool]]) -> dict[str, tuple[str, tuple[int, int]]] | None:
        """Wait until the seller's dialog shows a line for every test in `want`.

        Returns each match's text and screen centre, or None after SHOP_STEP_WAIT_SEC.
        """
        def read(rect: PixelRect, image: np.ndarray) -> dict | None:
            lines = text_boxes(image)
            hits = {}
            for name, test in want.items():
                for text, (x0, y0, x1, y1) in lines:
                    if test(text):
                        hits[name] = (text, (rect.x + (x0 + x1) // 2, rect.y + (y0 + y1) // 2))
                        break
            return hits if len(hits) == len(want) else None
        return self._shop_wait(read)

    def _close_shop(self, before: np.ndarray, ask: dict, box: tuple[int, int]) -> None:
        """Click the "..." that ends the purchase once it shows, then check the dialog closed.

        The "..." shows where the amount box was. Its text is not read: an
        ability label behind it garbled the read into "Loaie" (2026-11-02),
        and the labels differ per fruit. The dialog's dark backdrop tells that
        it is still open, so the click never lands on the game behind it.
        """
        def dimmed(rect: PixelRect, image: np.ndarray) -> bool:
            return _dimmed(image, before, _backdrop_band(rect, ask))

        def dots_step(rect: PixelRect, image: np.ndarray) -> bool | None:
            if not dimmed(rect, image):
                return None
            buy_shown = any(t.strip().lower() == "buy" for t, _ in text_boxes(image))
            return None if buy_shown else True

        if self._shop_wait(dots_step) is None:
            self.hooks.status("The closing '...' did not show; left the dialog as it is.")
            return
        click_at(*box)
        if self._shop_wait(lambda rect, image: None if dimmed(rect, image) else True) is None:
            self.hooks.status("Clicked the closing '...', but the seller's dialog stayed open.")

    def _buy_common(self) -> str | None:
        """Buy as much Common Fish Bait as the seller allows. Returns why it failed, or None.

        Steps, from the user's screenshots (2026-10-25): E opens the seller,
        "Yes", type the MAX amount in the box, "Buy", then "..." closes it.
        """
        self.hooks.status(f"Buying {COMMON_BAIT}...")
        self._focus()
        _, before = self._shop_image()
        hold = self.adv["key_hold_sec"]
        tap_key("e", hold_s=hold, should_abort=self.abort)
        # The question must be the Common Fish Bait seller's: E near another NPC
        # could open a different Yes/No dialog.
        ask = self._shop_find({"yes": lambda t: t.strip().lower() == "yes",
                               "no": lambda t: t.strip().lower() == "no",
                               "question": lambda t: "purchase" in t.lower() and "common fish" in t.lower()})
        if ask is None:
            return "the Common Fish Bait seller's question did not open; stand next to that seller"
        click_at(*ask["yes"][1])
        how = self._shop_find({"buy": lambda t: t.strip().lower() == "buy",
                               "max": lambda t: shop_max(t) is not None})
        if how is None:
            # No on the question and Cancel on the next step share a spot
            # (screenshots, 2026-10-25), so this closes whichever is open.
            click_at(*ask["no"][1])
            return "the 'How many' step did not show; closed the dialog"
        amount = shop_max(how["max"][0])
        # The amount box sits where Yes and No were centred, on the Buy row.
        box = ((ask["yes"][1][0] + ask["no"][1][0]) // 2, how["buy"][1][1])
        if amount == 0:
            cancel = (2 * box[0] - how["buy"][1][0], box[1])  # Cancel mirrors Buy
            click_at(*cancel)
            return "the seller allows 0 (not enough Peli, or the bait is full)"
        click_at(*box)
        for _ in range(4):
            tap_key("backspace", hold_s=hold, should_abort=self.abort)
        for digit in str(amount):
            tap_key(digit, hold_s=hold, should_abort=self.abort)
        click_at(*how["buy"][1])
        self._close_shop(before, ask, box)
        sleep_interruptible(SHOP_AFTER_SEC, self.abort)
        return None

    def _snapshot(self) -> None:
        """Save the Roblox window as a PNG, keeping the newest SNAPSHOT_KEEP."""
        rect = roblox_client_rect()
        if rect is None:
            return
        with _MSS() as sct:
            image = grab(rect, sct)
        SNAPSHOT_DIR.mkdir(exist_ok=True)
        path = SNAPSHOT_DIR / time.strftime("no-bite-%Y%m%d-%H%M%S.png")
        if not cv2.imwrite(str(path), image):
            raise RuntimeError(f"could not write {path}")
        for old in sorted(SNAPSHOT_DIR.glob("no-bite-*.png"))[:-SNAPSHOT_KEEP]:
            old.unlink()

    def _focus(self) -> None:
        for _ in range(6):
            if self.abort():
                return
            if focus_roblox():
                return
            sleep_interruptible(0.15, self.abort)
        if not roblox_running():
            raise StopRun("Roblox isn't running. Open GPO first.")
        raise StopRun("Could not bring the Roblox window to the front. If it is minimized, open it from the "
                      + ("taskbar." if sys.platform == "win32" else "Dock."))

    def _cast(self) -> None:
        self.hooks.status("Casting...")
        self.hooks.event("cast", None)
        click_point(_pt(self.cfg["cast_point"]), settle_s=self.adv["cast_settle_sec"], should_abort=self.abort)
        sleep_interruptible(self.adv["cast_after_sec"], self.abort)

    def _bait(self) -> dict:
        return self.cfg["baits"][self.cfg["bait_index"]]

    def _select_bait(self) -> None:
        """Click the bait's row and confirm the game selected it.

        A click that did not take let a cast use the last Legendary bait
        (2026-10-29), so a row that stays unselected stops the run. When the
        panel is hidden (rod away), nothing can be used up, so it carries on.
        """
        bait = self._bait()
        spot = self._spot(bait)
        if spot is None:
            raise StopRun(f"{bait['name']} is not in the Fishing Baits panel any more.")
        for _ in range(SELECT_TRIES):
            self.hooks.status(f"Selecting {bait['name']}...")
            click_point(_pt(spot), settle_s=SELECT_SETTLE_SEC, should_abort=self.abort)
            if self.abort():
                return
            selected = bait_selected(spot)
            if selected is None:
                self.hooks.status(f"Could not see the bait panel to confirm {bait['name']} is selected.")
                return
            if selected:
                return
        raise StopRun(f"Clicked {bait['name']} {SELECT_TRIES} times but the game did not select it. "
                      "Stopped before casting so no other bait is used by mistake.")

    def _read_count(self, bait: dict, expect: set[int] | None) -> tuple[int | None, str]:
        """Read a bait count from the panel, retrying until it can be trusted.

        A count is trusted after `reads_needed` equal reads. The count text can
        be caught mid-animation or misread, so a single odd read is not taken
        (2026-10-24: misreads drifted the count to 1 while the game still had 4).
        """
        reads: list[int] = []
        seen: Counter[int] = Counter()
        why = "not read"
        rescanned = False
        for attempt in range(COUNT_READ_TRIES):
            if attempt and sleep_interruptible(COUNT_READ_GAP_SEC, self.abort):
                break
            spot = self._spot(bait)
            if spot is None:
                return 0, "not in the Fishing Baits panel"
            try:
                count, row = read_bait_count(spot)
            except (RuntimeError, OSError) as exc:
                # One failed text recognition is a bad read, not the end of the run.
                # (Vision fails with RuntimeError, Windows OCR with OSError.)
                why = str(exc)
                continue
            found = row_bait(row, list(BAIT_TYPES)) if row else None
            if (found is not None and found != bait["name"]) or not row:
                # Another bait or nothing at this row: the rows may have moved
                # (a bait type gained or used up), so map them once more.
                if found is not None and rescanned:
                    raise StopRun(f"The Fishing Baits panel keeps changing: {bait['name']}'s row shows {found}.")
                if not rescanned:
                    rescanned = True
                    self._scan_panel()
                    continue
            if count is None or count > BAIT_MAX:
                why = (f"read {count}, more than the game maximum of {BAIT_MAX} ({row!r})" if count
                       else f"no bait count in {row!r}" if row else "no text at the bait's row")
                continue
            reads.append(count)
            seen[count] += 1
            if seen[count] >= reads_needed(count, expect):
                return count, row
            why = f"reads did not agree enough ({', '.join(map(str, reads))})"
        return None, why

    def _spot(self, bait: dict) -> dict | None:
        """Where the bait's row is now, or None when the panel does not list it."""
        k = self._rows.get(bait["name"])
        return None if k is None else row_spot(k)

    def _scan_panel(self) -> None:
        """Map each bait in the "Fishing Baits" panel to its row by reading the names.

        The panel lists only owned baits, from the top, so a missing bait type
        moves the rows below it up (2026-10-26/30: a gained or used-up Legendary
        shifted Rare and Common). Ticked baits that are not listed get count 0.
        """
        rows: dict[str, int] = {}
        for k in range(len(BAIT_TYPES)):
            name = None
            for attempt in range(SCAN_READ_TRIES):
                if attempt and sleep_interruptible(COUNT_READ_GAP_SEC, self.abort):
                    break
                try:
                    _, row = read_bait_count(row_spot(k))
                except (RuntimeError, OSError):
                    continue  # one failed text recognition; try the row again
                name = row_bait(row, list(BAIT_TYPES)) if row else None
                if name is not None:
                    break
            if name is None or name in rows:
                break  # rows run from the top without gaps
            rows[name] = k
        if not rows:
            # Nothing readable (panel hidden or covered for a moment): keep the
            # last map rather than treat every bait as gone.
            self.hooks.status("Bait panel: nothing readable, keeping the last layout.")
            return
        if all(self._rows.get(n) == k for n, k in rows.items()):
            # Every bait read is where it was, so nothing moved: a row that did
            # not read is a misread, not a bait that is gone.
            rows = {**self._rows, **rows}
        self._rows = rows
        self.hooks.status("Bait panel: " + ", ".join(f"{n} (row {k + 1})" for n, k in rows.items()) + ".")
        for bait in self.cfg["baits"]:
            if bait["use"] and bait["name"] not in rows:
                bait["count"] = 0

    def _set_count(self, bait: dict, expect: set[int] | None) -> None:
        """Store the panel count, or None (unknown) when it can't be trusted.

        An unknown count counts as stock: bait is switched, and anti-AFK
        starts, only on a count that was actually read.
        """
        count, why = self._read_count(bait, expect)
        if count is None and self._read_ok:
            self.hooks.status(f"Could not read the {bait['name']} count: {why}. "
                              "Keeping on with it until a read works.")
        self._read_ok = count is not None
        bait["count"] = count

    def _read_all_baits(self) -> None:
        """Map the panel, then update the count of every ticked bait it lists.

        A ticked bait the player has none of is skipped (count 0). With no bait
        panel at all the rod is not out, so the run stops and says so.
        """
        self._scan_panel()
        if not self._rows:
            raise StopRun("Couldn't see the Fishing Baits panel. Equip the rod so it shows, then start again.")
        for bait in self.cfg["baits"]:
            if not bait["use"]:
                continue
            if bait["name"] in self._rows:
                self._set_count(bait, None)
            else:
                self.hooks.status(f"{bait['name']} isn't in your bait panel, so it is skipped.")
        self.hooks.bait_changed()

    def _next_bait(self, select: bool) -> None:
        """Move to the first bait in use with stock, starting at the current one.

        A bait that gets selected is read from the panel; when the panel shows
        it empty, the search moves on. An unknown count counts as stock.
        """
        baits = self.cfg["baits"]
        for _ in range(len(baits) + 1):
            start = self.cfg["bait_index"]
            order = list(range(start, len(baits))) + list(range(start))
            i = next((j for j in order if _has_stock(baits[j])), None)
            if i is None:
                break
            changed = i != start
            self.cfg["bait_index"] = i
            if not (changed or select):
                return
            self._select_bait()
            self._set_count(baits[i], None)
            self.hooks.bait_changed()
            if _has_stock(baits[i]):
                return
            select = False
        if self._restock():
            return
        raise OutOfBait("Every ticked bait is down to its last one.")

    def _use_bait(self) -> None:
        bait = self._bait()
        before = bait["count"]
        # One bite uses one bait; the same count is fine if the panel lags.
        self._set_count(bait, None if before is None else {before - 1, before})
        self.hooks.bait_changed()
        if not _has_stock(bait):
            self._next_bait(select=False)

    def _look_for_item(self) -> tuple[Catch | None, str]:
        """Read the "New Item" banner, retrying for ITEM_LOOK_SEC while it appears."""
        end = time.monotonic() + ITEM_LOOK_SEC
        while True:
            catch, why = read_new_item()
            if catch is not None or time.monotonic() >= end:
                return catch, why
            if sleep_interruptible(ITEM_LOOK_GAP_SEC, self.abort):
                return None, "stopped"

    def _buso(self) -> bool:
        """Press J once when Buso Haki is on and the last press was long enough ago.

        Returns True when J was pressed.
        """
        if not self.cfg["use_buso"]:
            return False
        now = time.monotonic()
        if self._buso_at is not None and now - self._buso_at < self.adv["buso_every_sec"]:
            return False
        self.hooks.status("Using Buso Haki (J)...")
        tap_key(BUSO_KEY, hold_s=self.adv["key_hold_sec"], should_abort=self.abort)
        self._buso_at = now
        return True

    def _idle(self) -> str:
        """Anti-AFK after the bait runs low: cast and reel straight back in on an
        interval, plus Buso Haki when ticked, until stopped."""
        every = self.adv["idle_every_sec"]
        buso = " and pressing J for Buso Haki" if self.cfg["use_buso"] else ""
        self.hooks.status(f"Bait is down to the last one, so fishing stopped. Anti-AFK: casting and "
                          f"reeling in{buso} every {every:g} s until you stop.")
        while not self.abort():
            if not roblox_running():
                return "Roblox closed."
            self._focus()
            self._check_connection()
            # Clicked here, not through _cast, so anti-AFK casts stay out of the cast count.
            spot = _pt(self.cfg["cast_point"])
            self.hooks.status("Casting (anti-AFK)...")
            click_point(spot, settle_s=self.adv["cast_settle_sec"], should_abort=self.abort)
            sleep_interruptible(DECAST_AFTER_SEC, self.abort)
            self.hooks.status("Reeling in (anti-AFK)...")
            click_point(spot, settle_s=self.adv["cast_settle_sec"], should_abort=self.abort)
            # J after the line is pulled in, as the user asked. On 2026-10-24 J sent
            # about 0.5 s after the reel-in click did nothing in game, so wait first.
            if self.cfg["use_buso"]:
                sleep_interruptible(BUSO_SETTLE_SEC, self.abort)
                self._buso()
            self.hooks.status(f"Anti-AFK: next cast in {every:g} s.")
            sleep_interruptible(every, self.abort)
        return "Stopped."

    def _reequip(self) -> None:
        key = self.cfg["rod_key"]
        if not key:
            return
        self.hooks.status(f"Re-equipping the rod ({key.upper()} twice)...")
        for _ in range(2):
            tap_key(key, hold_s=self.adv["key_hold_sec"], should_abort=self.abort)
            sleep_interruptible(REEQUIP_GAP_SEC, self.abort)

    def _play(self) -> str:
        """Wait for the bars, then steer the gap until they vanish.

        Returns "none" (no bite), "caught", "lost", "unclear" (progress bar not
        seen), "timeout", or "aborted".
        """
        adv = self.adv
        budget = 1.0 / max(5.0, adv["task_fps"])
        confirm = max(1, round(adv["start_confirm_frames"]))
        deadline = time.perf_counter() + adv["wait_bite_sec"]
        started = False
        hits = 0
        last_seen = 0.0
        progress = None
        box = None
        self.detector.reset()
        self.hooks.status("Waiting for a bite...")
        with _MSS() as sct:
            while not self.abort():
                t0 = time.perf_counter()
                window = roblox_client_rect()
                if window is None:
                    # The window left the screen (another Space, minimized): bring it back.
                    self._focus()
                    continue
                rect = box or window
                image = grab(rect, sct)
                reading = self.detector.find(image)
                now = time.perf_counter()
                box = bar_box(reading, rect, window) if reading is not None else None
                if reading is not None:
                    # Screen coordinates, so moving the box does not look like motion.
                    gap_y, fish_y = rect.y + reading.gap_y, rect.y + reading.fish_y
                if not started:
                    hits = hits + 1 if reading is not None else 0
                    if hits >= confirm:
                        started = True
                        last_seen = now
                        deadline = now + adv["minigame_max_sec"]
                        self.tracker.configure(adv)
                        self.tracker.start(gap_y, fish_y, reading.gap_h, now)
                        self.hooks.event("bite", None)
                        self.hooks.status("Reeling...")
                    elif now >= deadline:
                        return "none"
                elif reading is None:
                    if now - last_seen > RELEASE_WHEN_LOST_SEC:
                        self.click.release()
                    if now - last_seen > adv["lost_timeout_s"]:
                        if progress is None:
                            return "unclear"
                        return "caught" if progress >= CAUGHT_PROGRESS else "lost"
                else:
                    last_seen = now
                    if reading.progress is not None:
                        progress = reading.progress
                    self.tracker.observe(gap_y, reading.gap_h, fish_y, now)
                    self.click.set(self.tracker.decide(now))
                if started and now >= deadline:
                    self.click.release()
                    return "timeout"
                self.hooks.frame(image, reading)
                left = (budget if box is not None else max(budget, 1.0 / SEARCH_FPS)) - (time.perf_counter() - t0)
                if left > 0:
                    time.sleep(left)
        self.click.release()
        return "aborted"
