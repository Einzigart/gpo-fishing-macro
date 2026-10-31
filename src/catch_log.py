"""Saved catch history: one CSV row per caught fish or item, kept between runs.

The app only appends to the file, so a crash loses at most the row it was writing.
"""
from __future__ import annotations

import csv
import time
from collections import Counter
from pathlib import Path

import config
from fishing import Catch
from screen_text import RARITY_HUES

CATCH_LOG = config.CONFIG_PATH.parent / "catches.csv"
FIELDS = ("time", "name", "rarity")
# Display order. "Unknown" holds every catch whose rarity the app could not tell.
RARITIES = (*(r for r, _, _ in RARITY_HUES), "Legendary", "Unknown")
NO_NAME = "(name not read)"


class CatchLogError(Exception):
    """The catch history file is not in the format the app writes."""


def row(catch: Catch | None) -> dict:
    """The history row for a catch now. None is a catch whose banner was not read."""
    return {"time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "name": catch.name if catch else NO_NAME,
            "rarity": catch.rarity if catch else "Unknown"}


def append(entry: dict, path: Path = CATCH_LOG) -> None:
    new = not path.exists() or path.stat().st_size == 0
    with open(path, "a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new:
            w.writeheader()
        w.writerow(entry)


def load(path: Path = CATCH_LOG) -> list[dict]:
    """All saved rows, oldest first. Raises CatchLogError when the file is malformed."""
    if not path.exists():
        return []
    rows = []
    with open(path, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            return []
        if tuple(reader.fieldnames) != FIELDS:
            raise CatchLogError(f"{path.name} starts with {reader.fieldnames}, expected {list(FIELDS)}. "
                                "Rename or delete the file to start a new history.")
        for entry in reader:
            # DictReader puts extra fields under None and fills missing ones with None.
            if None in entry or None in entry.values():
                raise CatchLogError(f"{path.name} line {reader.line_num} does not have the 3 fields "
                                    f"{', '.join(FIELDS)}. Fix or delete that line.")
            rows.append(entry)
    return rows


def rarity_group(rarity: str) -> str:
    return rarity if rarity in RARITIES else "Unknown"


def tally(rows: list[dict]) -> Counter:
    return Counter(rarity_group(r["rarity"]) for r in rows)


def rarity_line(counts: Counter) -> str:
    """For example "12 Common · 3 Rare · 0 Epic · 1 Legendary"; Unknown shows only when there is one."""
    return " · ".join(f"{counts[r]} {r}" for r in RARITIES if r != "Unknown" or counts[r])


def by_name(rows: list[dict]) -> list[tuple[str, str, int]]:
    """(name, rarity, count) for each fish or item, most caught first."""
    counts = Counter((r["name"], rarity_group(r["rarity"])) for r in rows)
    return sorted(((n, r, c) for (n, r), c in counts.items()), key=lambda t: (-t[2], t[0]))
