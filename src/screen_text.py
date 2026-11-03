"""Read game text with the system text recognition.

The recognition itself is per platform: Apple's Vision on macOS (ocr_mac),
Windows OCR on Windows (ocr_win). This module turns its lines into game facts.

Two things are read:
* Bait left, from the Fishing Baits panel rows like "Common Fish Bait x296".
  The reader captures a strip around the bait's picked spot.
* The catch, from the banner "New Item <Blue-Lip Grouper>" near the top.

Both are screen UI, so they do not change size with camera zoom; they only
scale with the window.
"""
from __future__ import annotations

import difflib
import re
import sys
from typing import NamedTuple

import cv2
import numpy as np

if sys.platform == "win32":
    from ocr_win import recognize
else:
    from ocr_mac import recognize
from roblox_geo import CoordOrigin, PixelRect, rect_to_screen

# Strip around the picked spot, as fractions of the window. Measured on
# 2026-10-24: the row "Common Fish Bait x296" spans about 13% of the window
# width and 3% of its height; this strip holds the whole row with margin.
STRIP_HALF_W = 0.14
STRIP_HALF_H = 0.03
# Only text centred in the middle half of the strip belongs to the picked row.
# Rows sit about 3.5% of the window apart (user config, 2026-10-24), so a
# neighbour row can enter the strip edge but not its middle half.
ROW_REACH = 0.25
# The count sits at the right end of the row. Vision dropped a short count
# ("X1") from the whole strip in a 1512-point-wide window but read it from the
# strip's right half alone (2026-11-02). The right half read the right count in
# all 12 strips on hand; the right 40% missed one ("Rare Fish Bait x1").
COUNT_PART_X = 0.5

# Vision reads the stylised count digits as look-alike letters at times. Seen
# in real runs on 2026-10-24: "ХЦ4" for x44, "×З6" for x36, "×G4" for x64,
# "×S" for x5 (Х is Cyrillic). The count must be 1-3 characters after the x.
_DIGIT_LOOKALIKES = str.maketrans({"S": "5", "s": "5", "G": "6", "З": "3", "з": "3",
                                   "Ц": "4", "ц": "4", "O": "0", "o": "0", "I": "1", "l": "1"})
_DIGIT = "[0-9SsGЗзЦцOoIl]"
# One space may split the digits ("x29 6"): without it, that read gave 29.
_COUNT = re.compile(rf"[xX×хХ]\s*({_DIGIT}(?: ?{_DIGIT}){{0,2}})(?![0-9A-Za-z])")
# NOT SEEN YET: a read that drops the x (Vision), or splits it off (Windows OCR). Then only real digits count, and
# only at the end of the name ("Common Fish Bait 296") or as a line alone.
_BARE_COUNT = re.compile(r"(?:(?<=[BbT8]a[il1]t)|^)\s*([0-9](?: ?[0-9]){0,2})\s*$")

# The selected bait row has a gold frame. Measured on 2026-10-30 on 8 row
# strips: selected rows had 208-572 gold pixels both above and below the text;
# unselected rows had 0-11 on at least one side (a selected neighbour's frame
# can show on the other side). Gold is the frame and count colour.
SELECTED_GOLD_MIN = 100

# A panel row's bait name (difflib ratio). Real reads scored 0.92-1.0 on
# 2026-10-26, including the rainbow "Legendary FishTait"; different bait names
# score at most 0.74 against each other.
ROW_NAME_MATCH = 0.85

# Area of the "New Item" banner as (x0, y0, x1, y1) fractions of the window.
# Measured on 2026-10-24 in two screenshots: the banner sat at 14-15% of the
# height, centred; this area holds it with margin. Vision read it in both.
ITEM_AREA = (0.25, 0.06, 0.75, 0.24)
# Vision reads the angle brackets as <, «, ‹ or > » › at random.
_ITEM = re.compile(r"New\s*Item\s*[<«‹(]?\s*(.+?)\s*[>»›)]?\s*$", re.IGNORECASE)

# Known catches and their rarity, from the wiki pages Fishing/Bestiary and
# Fishing/Items (read 2026-10-24); Jack-O'Rod Blueprint is Epic per the user.
# A known name beats the colour: one real read of a green Blue-Lip Grouper
# came out blue, likely mid fade-in.
WIKI_RARITY = {
    "Anglerfish": "Legendary", "Dark Skeletal Shark": "Legendary", "Jack-O'-Bite": "Legendary",
    "Swordfish": "Legendary", "Golden Polka Puffer": "Legendary", "Golden Ribbon Angelfish": "Legendary",
    "Golden Tigerfin": "Legendary", "Sunken Anchor": "Legendary", "Sunken Helmet": "Legendary",
    "Sunken Armor": "Legendary",
    "Skeletal Shark": "Epic", "Jack-O'Rod Blueprint": "Epic",
    "Candy Corn Squid": "Rare", "Crimson Polka Puffer": "Rare", "Crimson Snapper": "Rare",
    "Exotic Tigerfin": "Rare", "Fangfish": "Rare", "Zebra Ribbon Angelfish": "Rare",
    "Blue-Lip Grouper": "Common", "Tigerfin": "Common",
}
# Name match cutoff (difflib ratio). Real misreads scored 0.94 ("Tigerfins") and
# 0.97 ("Blue-Lip Grouper-"); the closest two different names, Skeletal Shark
# and Dark Skeletal Shark, score 0.85.
NAME_MATCH = 0.9

# The bait seller's dialog (question, "Yes"/"No", "MAX: n", "Buy", "...") as
# (x0, y0, x1, y1) fractions of the window. Measured on 2026-10-25 in six
# screenshots: its text and buttons sat at 25-75% across and 75-93% down.
SHOP_AREA = (0.25, 0.62, 0.75, 0.99)
_MAX = re.compile(r"MAX\s*[:;.]?\s*([0-9SsGЗзЦцOoIl]{1,3})(?![0-9A-Za-z])", re.IGNORECASE)

# Roblox's "Disconnected" dialog ("Error Code: 277", "Leave", "Reconnect") sits
# in the window centre: 37-63% across and down in the user's screenshot
# (2026-10-25). This area holds it with margin.
DISCONNECT_AREA = (0.25, 0.25, 0.75, 0.75)

# Rarity from the item name colour, for items not in WIKI_RARITY. Measured on 2026-10-24 (OpenCV hue 0-180):
# Blue-Lip Grouper (wiki Bestiary: Common) RGB (117,238,119), hue 60;
# Crimson Polka Puffer (wiki Bestiary: Rare) RGB (30,240,243), hue 93;
# Jack-O'Rod Blueprint RGB (145,148,237), hue 118; the wiki gives no tier, the
# user confirmed Epic. The user says legendary names are rainbow; no sample yet.
RARITY_HUES = (("Common", 45, 75), ("Rare", 80, 100), ("Epic", 105, 130))
# Name text is bright and coloured; white "New Item" and the dark outline are
# not. The Epic lavender has saturation 99, the lowest seen, so 60 is the floor.
TEXT_MIN_S = 60
TEXT_MIN_V = 180
TEXT_MIN_PX = 20
# Rainbow text: at least 3 of 6 hue sectors each hold 10% of the text pixels.
RAINBOW_SECTORS = 3
RAINBOW_SHARE = 0.10
_HUE_NAMES = ((10, "red"), (22, "orange"), (35, "yellow"), (78, "green"), (100, "teal"),
              (130, "blue"), (160, "purple"))


def strip_rect(point: dict, origin: CoordOrigin) -> PixelRect:
    x0 = max(0.0, point["x"] - STRIP_HALF_W)
    y0 = max(0.0, point["y"] - STRIP_HALF_H)
    x1 = min(1.0, point["x"] + STRIP_HALF_W)
    y1 = min(1.0, point["y"] + STRIP_HALF_H)
    return rect_to_screen(x0, y0, x1 - x0, y1 - y0, origin)


def area_rect(area: tuple[float, float, float, float], origin: CoordOrigin) -> PixelRect:
    """Screen rect of an (x0, y0, x1, y1) window-fraction area."""
    x0, y0, x1, y1 = area
    return rect_to_screen(x0, y0, x1 - x0, y1 - y0, origin)


def item_rect(origin: CoordOrigin) -> PixelRect:
    x0, y0, x1, y1 = ITEM_AREA
    return rect_to_screen(x0, y0, x1 - x0, y1 - y0, origin)


Box = tuple[int, int, int, int]  # x0, y0, x1, y1 in image pixels


class Line(NamedTuple):
    dist: float  # distance of the line's centre from the image centre, as a fraction of the height
    text: str  # the best reading
    name_box: Box | None  # box of the item name when the line is a "New Item" banner
    box: Box
    alts: tuple[str, ...]  # next-best readings, best first (Vision only)


def _item_span(text: str) -> tuple[int, int] | None:
    m = _ITEM.search(text)
    return (m.start(1), m.end(1)) if m and m.group(1) else None


def _lines(image: np.ndarray) -> list[Line]:
    """Each text line the system recognition finds in the image."""
    return [Line(*raw) for raw in recognize(image, _item_span)]


def parse_count(text: str) -> int | None:
    """The bait count in one line of panel text ("Common Fish Bait x296"), or None."""
    m = _COUNT.search(text)
    if m:
        return int(m.group(1).replace(" ", "").translate(_DIGIT_LOOKALIKES))
    m = _BARE_COUNT.search(text)
    if m:
        return int(m.group(1).replace(" ", ""))
    return None


def _strip_count(text: str) -> str:
    return _BARE_COUNT.sub("", _COUNT.sub("", text)).strip()


def read_count(image: np.ndarray) -> tuple[int | None, str]:
    """(Bait count or None, text of the panel row at the strip centre).

    The row text is "" when nothing was read there. Its pieces (the name and
    count may be read separately) are joined by " | ". Vision's best reading
    of every piece is tried first, then its other readings. With no count in
    the whole strip, the strip's right part is read alone.
    """
    n, row = _count_in(image)
    if n is None:
        n, _ = _count_in(image[:, int(image.shape[1] * COUNT_PART_X):])
    return n, row


def _count_in(image: np.ndarray) -> tuple[int | None, str]:
    lines = sorted((ln for ln in _lines(image) if ln.dist <= ROW_REACH), key=lambda ln: ln.dist)
    row = " | ".join(ln.text for ln in lines)
    for text in [ln.text for ln in lines] + [a for ln in lines for a in ln.alts]:
        n = parse_count(text)
        if n is not None:
            return n, row
    return None, row


def _hue_name(hue: float) -> str:
    for top, name in _HUE_NAMES:
        if hue < top:
            return name
    return "red"


def rarity_of(name_crop: np.ndarray) -> str:
    """Rarity from the colour of the item name text, or "unknown (<colour>)"."""
    hsv = cv2.cvtColor(name_crop, cv2.COLOR_BGR2HSV)
    text = (hsv[:, :, 1] >= TEXT_MIN_S) & (hsv[:, :, 2] >= TEXT_MIN_V)
    hues = hsv[:, :, 0][text].astype(np.float32)
    if hues.size < TEXT_MIN_PX:
        return "unknown (no coloured text)"
    sectors = np.histogram(hues, bins=6, range=(0, 180))[0] / hues.size
    if (sectors >= RAINBOW_SHARE).sum() >= RAINBOW_SECTORS:
        return "Legendary"
    hue = float(np.median(hues))
    for rarity, lo, hi in RARITY_HUES:
        if lo <= hue <= hi:
            return rarity
    return f"unknown ({_hue_name(hue)})"


def _known(name: str) -> str | None:
    """The wiki spelling of `name`, when it matches a known catch closely enough."""
    lower = {n.lower(): n for n in WIKI_RARITY}
    hit = difflib.get_close_matches(name.lower(), list(lower), n=1, cutoff=NAME_MATCH)
    return lower[hit[0]] if hit else None


def read_item(image: np.ndarray) -> tuple[str | None, str | None, str]:
    """(item name, rarity, text read) from a "New Item <name>" banner.

    A name the wiki lists gets the wiki spelling and rarity; any other name gets
    the rarity of its colour. Returns (None, None, reason) when no banner is found.
    """
    lines = _lines(image)
    for text, box in ((ln.text, ln.name_box) for ln in lines):
        m = _ITEM.search(text)
        if m and m.group(1):
            known = _known(m.group(1))
            if known is not None:
                return known, WIKI_RARITY[known], text
            rarity = "unknown (name not located)"
            if box is not None:
                x0, y0, x1, y1 = box
                crop = image[max(0, y0):max(0, y1), max(0, x0):max(0, x1)]
                if crop.size:
                    rarity = rarity_of(crop)
            # Vision sometimes lowercases a word ("Crimson polka Puffer").
            name = " ".join(w[:1].upper() + w[1:] for w in m.group(1).split())
            return name, rarity, text
    if not lines:
        return None, None, "no text in the banner area"
    return None, None, "no New Item banner in {!r}".format(" | ".join(ln.text for ln in lines))


def text_boxes(image: np.ndarray) -> list[tuple[str, Box]]:
    """Every text line in the image with its box."""
    return [(ln.text, ln.box) for ln in _lines(image)]


def shop_max(text: str) -> int | None:
    """The number in "How many do you want? MAX: n", or None."""
    m = _MAX.search(text)
    return int(m.group(1).translate(_DIGIT_LOOKALIKES)) if m else None


def disconnected_text(image: np.ndarray) -> str | None:
    """The text of Roblox's "Disconnected" dialog when it is in the image, else None.

    Both the title and its "Reconnect" button (or error code) must show, as in
    the Slayers 2 macro, so a chat line saying "disconnected" does not count.
    """
    text = " | ".join(ln.text for ln in _lines(image))
    low = text.lower()
    if "disconnected" in low and ("reconnect" in low or "error code" in low):
        return text
    return None


def is_panel_footer(row: str) -> bool:
    """Whether a panel row's text is the footer under the last bait row.

    The footer reads "Craft more bait types from | Blacksmith Sen!"; it moved
    up into the row of a bait that was used up (snapshot, 2026-11-02).
    """
    return "craft more" in row.lower()


def row_bait(row: str, names: list[str]) -> str | None:
    """The bait name in a panel row's text (pieces joined by " | "), or None."""
    best_score, best = 0.0, None
    for part in row.split("|"):
        part = _strip_count(part)
        for name in names:
            score = difflib.SequenceMatcher(None, part.lower(), name.lower()).ratio()
            if score > best_score:
                best_score, best = score, name
    return best if best_score >= ROW_NAME_MATCH else None


def row_selected(image: np.ndarray) -> bool | None:
    """True when the panel row at the strip centre has the gold "selected" frame.

    None when no row text is found there (for example the panel is hidden).
    """
    row = [ln.box for ln in _lines(image) if ln.dist <= ROW_REACH]
    if not row:
        return None
    b, g, r = (image[:, :, i].astype(np.int16) for i in range(3))
    gold = (r >= 180) & (g >= 110) & (g <= 215) & (b <= 110) & (r - b >= 100)
    for x0, y0, x1, y1 in row:  # the count is gold too; only the frame counts
        gold[max(0, y0 - 2):y1 + 2, max(0, x0 - 2):x1 + 2] = False
    top, bot = min(b[1] for b in row), max(b[3] for b in row)
    h = bot - top
    above = int(gold[max(0, top - h):max(0, top - 2)].sum())
    below = int(gold[bot + 2:bot + h].sum())
    return above >= SELECTED_GOLD_MIN and below >= SELECTED_GOLD_MIN
