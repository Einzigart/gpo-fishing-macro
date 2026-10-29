"""Hold/release controller that keeps the gap centre on the fish line.

The gap has momentum: holding left click accelerates it up (screen y gets
smaller), and releasing lets it fall. The controller predicts where the gap
would stop if it switched input now, and holds only while that stop point is
below the fish. Ported from the Slayers 2 macro, where the same physics moved
a ball into a zone.
"""
from __future__ import annotations

TRACK_DEFAULTS = {
    # NOT MEASURED YET: first guess from a 380 px track crossed in about 1 s.
    # Fit these from a live hold/release trace and write the date here.
    "accel_hold": 800.0,
    "accel_release": 800.0,
    # Gap height measured 92 px in a 2000x1258 window on 2026-10-24.
    "size_ref_px": 92.0,
    "latency_s": 0.10,
    "hysteresis_px": 6.0,
    "aim_offset": 0.0,
}


class Motion:
    """Alpha-beta filter for one coordinate with a known applied acceleration."""

    def __init__(self, alpha: float = 0.8, beta: float = 0.6) -> None:
        self.alpha, self.beta = alpha, beta
        self.y = self.v = self.t = 0.0

    def reset(self, y: float, t: float) -> None:
        self.y, self.v, self.t = float(y), 0.0, t

    def predict(self, t: float, a: float) -> tuple[float, float]:
        dt = max(0.0, t - self.t)
        return self.y + self.v * dt + 0.5 * a * dt * dt, self.v + a * dt

    def update(self, y_meas: float, t: float, a: float, jump: float) -> None:
        yp, vp = self.predict(t, a)
        dt = max(1e-3, t - self.t)
        r = y_meas - yp
        if abs(r) > jump:
            self.y, self.v = float(y_meas), vp
        else:
            self.y = yp + self.alpha * r
            self.v = vp + self.beta * r / dt
        self.t = t


class TrackController:
    """Decides hold or release each frame from gap and fish observations.

    Accelerations are in px/s^2 for a gap of `size_ref_px` height. They scale
    with the observed gap height, so the same values work at other window sizes.
    """

    def __init__(self) -> None:
        self.configure({})
        self.start(0.0, 0.0, self.size_ref_px, 0.0)

    def configure(self, adv: dict) -> None:
        for k, d in TRACK_DEFAULTS.items():
            setattr(self, k, float(adv.get(k, d)))
        self.size_ref_px = max(1.0, self.size_ref_px)

    def start(self, gap_y: float, fish_y: float, gap_h: float, now: float) -> None:
        self.bar = Motion()
        self.target = Motion(alpha=0.6, beta=0.3)
        self.bar.reset(gap_y, now)
        self.target.reset(fish_y, now)
        self.held = False
        self.size = float(gap_h)

    def _scale(self) -> float:
        return self.size / self.size_ref_px

    def observe(self, gap_y: float, gap_h: float, fish_y: float, now: float) -> None:
        self.size = 0.8 * self.size + 0.2 * float(gap_h)
        s = self._scale()
        a_applied = -self.accel_hold * s if self.held else self.accel_release * s
        self.bar.update(gap_y, now, a_applied, jump=self.size)
        self.target.update(fish_y, now, 0.0, jump=self.size)

    def decide(self, now: float) -> bool:
        s = self._scale()
        a_up = self.accel_hold * s
        a_dn = self.accel_release * s
        y, v = self.bar.predict(now + self.latency_s, -a_up if self.held else a_dn)
        ty, tv = self.target.predict(now + self.latency_s, 0.0)
        target = ty + self.aim_offset * self.size
        v_rel = v - tv
        if v_rel < 0:
            stop = y - v_rel * v_rel / (2 * a_dn)
        else:
            stop = y + v_rel * v_rel / (2 * a_up)
        band = self.hysteresis_px * s
        if self.held:
            self.held = stop > target - band
        else:
            self.held = stop > target + band
        return self.held
