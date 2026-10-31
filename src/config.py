"""Settings file (config.json next to Launch.command): defaults, load, save.

Points are fractions of the Roblox window, so they survive window moves and
resizes.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

from track_control import TRACK_DEFAULTS

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.json"

# The game holds at most 300 of each bait type (user report, 2026-10-24).
BAIT_MAX = 300

# Every bait type in GPO, from the wiki pages Fishing/Rods and Baits and
# Blacksmith Sen (read 2026-10-24). Odds are the wiki's estimates.
BAIT_TYPES = {
    "Common Fish Bait": "10 Peli at the Fish Buyer. Legendary fish 5-10.5%.",
    "Rare Fish Bait": "Craft from 2 rare fish at Blacksmith Sen. Rare fish 45-60%.",
    "Legendary Fish Bait": "Craft from 1 legendary fish at Blacksmith Sen. Legendary fish 65-95%.",
}

# Run-loop timings. Values without a measurement note carry over from the
# Slayers 2 macro and still need a live GPO check.
TIMING_DEFAULTS = {
    "task_fps": 60.0,
    "start_confirm_frames": 3.0,
    # Bites came 9-11 s after the cast in 5 casts (2026-10-24). The user asked
    # for a recast after 15 s with no bite.
    "wait_bite_sec": 15.0,
    # NOT MEASURED YET: generous cap on one minigame; stubborn fish take long.
    "minigame_max_sec": 120.0,
    "lost_timeout_s": 1.5,
    "cast_settle_sec": 0.08,
    "cast_after_sec": 0.25,
    "after_catch_sec": 1.0,
    "key_hold_sec": 0.1,
    # The user asked for Buso Haki once a minute (2026-10-24).
    "buso_every_sec": 60.0,
    # Anti-AFK cast and reel-in after the bait runs low; Roblox kicks after
    # 20 minutes idle, so once a minute is far inside that.
    "idle_every_sec": 60.0,
}
ADVANCED_DEFAULTS = {**TRACK_DEFAULTS, **TIMING_DEFAULTS}

ADVANCED_LABELS = {
    "accel_hold": "Hold accel (px/s²)",
    "accel_release": "Release accel (px/s²)",
    "size_ref_px": "Reference gap height (px)",
    "latency_s": "Input latency (s)",
    "hysteresis_px": "Hysteresis (px)",
    "aim_offset": "Aim offset (× gap)",
    "task_fps": "Scan rate (fps)",
    "start_confirm_frames": "Frames to confirm start",
    "wait_bite_sec": "Wait for bite (s)",
    "minigame_max_sec": "Minigame max (s)",
    "lost_timeout_s": "End after bars gone (s)",
    "cast_settle_sec": "Cast settle (s)",
    "cast_after_sec": "After cast (s)",
    "after_catch_sec": "After catch (s)",
    "key_hold_sec": "Key hold (s)",
    "buso_every_sec": "Buso Haki every (s)",
    "idle_every_sec": "Anti-AFK every (s)",
}

DEFAULTS = {
    # Open water above the character in the 2026-10-24 screenshots.
    "cast_point": {"x": 0.5, "y": 0.3},
    # In use order. "count" is None until it is read from the game panel.
    "baits": [{"name": n, "use": n == "Common Fish Bait", "count": None} for n in BAIT_TYPES],
    "bait_index": 0,
    "rod_key": "",
    "use_buso": False,
    "auto_buy_common": False,
    "always_on_top": False,
    "advanced": dict(ADVANCED_DEFAULTS),
}


class ConfigError(ValueError):
    """config.json holds a value the app cannot use."""


def _baits(saved: list) -> list[dict]:
    """Each bait type once, in the saved order; types the save lacks go last, unused."""
    by_name = {b["name"]: b for b in saved if b.get("name") in BAIT_TYPES}
    order = list(by_name) + [n for n in BAIT_TYPES if n not in by_name]
    out = []
    for name in order:
        b = by_name.get(name, {})
        n = b.get("count")
        if n is not None and (not isinstance(n, int) or not 0 <= n <= BAIT_MAX):
            raise ConfigError(f"{name} count is {n!r}, must be empty or a whole number 0-{BAIT_MAX}")
        out.append({"name": name, "use": bool(b.get("use")), "count": n})
    return out


def _check(cfg: dict) -> dict:
    cfg["baits"] = _baits(cfg["baits"])
    if not 0 <= cfg["bait_index"] < len(cfg["baits"]):
        cfg["bait_index"] = 0
    for k, v in cfg["advanced"].items():
        if not isinstance(v, (int, float)):
            raise ConfigError(f"advanced.{k} is {v!r}, must be a number")
    return cfg


def load() -> dict:
    """Read config.json merged over the defaults. Raises ConfigError on bad values."""
    cfg = copy.deepcopy(DEFAULTS)
    if not CONFIG_PATH.exists():
        return cfg
    try:
        raw = json.loads(CONFIG_PATH.read_text())
    except json.JSONDecodeError as exc:
        raise ConfigError(f"{CONFIG_PATH} is not valid JSON ({exc}). Fix or delete it.") from exc
    for k in DEFAULTS:
        if k in raw and k != "advanced":
            cfg[k] = raw[k]
    cfg["advanced"].update({k: v for k, v in (raw.get("advanced") or {}).items() if k in ADVANCED_DEFAULTS})
    return _check(cfg)


def save(cfg: dict) -> None:
    tmp = CONFIG_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(cfg, indent=2))
    tmp.replace(CONFIG_PATH)
