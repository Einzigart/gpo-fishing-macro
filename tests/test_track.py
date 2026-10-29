import math
import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from track_control import TrackController  # noqa: E402

FPS = 60
TRACK = 380.0   # track length in px, from the gap_middle fixture
GAP = 92.0      # gap height in px, from the gap_middle fixture
ACCEL = 800.0   # px/s^2 both ways, the controller default
LAG_FRAMES = 3  # 50 ms between a decision and the game reacting


def simulate(seconds: float, fish_period: float, seed: int) -> float:
    """Share of frames with the fish inside the gap, under momentum physics and input lag."""
    rng = random.Random(seed)
    ctl = TrackController()
    ctl.configure({"accel_hold": ACCEL, "accel_release": ACCEL, "size_ref_px": GAP,
                   "latency_s": LAG_FRAMES / FPS})
    dt = 1.0 / FPS
    y, v = TRACK - GAP / 2, 0.0
    drift = 0.0
    pending = [False] * LAG_FRAMES
    ctl.start(y, TRACK / 2, GAP, 0.0)
    inside = 0
    frames = int(seconds * FPS)
    for i in range(frames):
        t = i * dt
        drift = max(-40.0, min(40.0, drift + rng.uniform(-3, 3)))
        fish = TRACK / 2 + 0.35 * TRACK * math.sin(2 * math.pi * t / fish_period) + drift
        ctl.observe(y + rng.uniform(-1, 1), GAP, fish + rng.uniform(-1, 1), t)
        pending.append(ctl.decide(t))
        held = pending.pop(0)
        v += (-ACCEL if held else ACCEL) * dt
        y += v * dt
        lo, hi = GAP / 2, TRACK - GAP / 2
        if y < lo or y > hi:
            y, v = min(hi, max(lo, y)), 0.0
        if abs(fish - y) <= GAP / 2:
            inside += 1
    return inside / frames


class TrackTests(unittest.TestCase):
    def test_keeps_fish_in_gap(self):
        for period in (4.0, 2.5):
            for seed in range(3):
                with self.subTest(period=period, seed=seed):
                    self.assertGreaterEqual(simulate(30, period, seed), 0.9)


if __name__ == "__main__":
    unittest.main()
