"""Quiet-standing balance engine, v1.4.

The sway signal is the pelvis (mid-hip) position in *torso-length units*,
computed in pixel space (v1.3 mixed x/y with different pixel scales). The
first second is discarded while the participant settles, the recording is
resampled/smoothed offline, and the test only passes if the participant
actually stood still (no walking away, enough coverage, enough duration).
"""
from __future__ import annotations

import math

import numpy as np

from challenges.base import Challenge, FrameStats
from core import signals as S
from core.config import BALANCE as CFG, QUALITY
from core.pose import L_HIP, R_HIP, TORSO, PoseFrame, torso_length_px
from core.quality import base_gate, failed_block

CHI2_95_2DOF = 5.991464547107979


def analyze(t, xy, cfg=CFG, fs: float = QUALITY.resample_hz) -> dict:
    out: dict = {"ok": False, "reason": None}
    t = np.asarray(t, dtype=float)
    if t.size < int(fs * 2):
        out["reason"] = "not enough valid frames"
        return out
    tu, P, gap = S.resample_uniform(t, np.asarray(xy, dtype=float), fs, QUALITY.max_gap_seconds)
    x = S.smooth(S.hampel(P[:, 0]), cfg.smooth_seconds, fs)
    y = S.smooth(S.hampel(P[:, 1]), cfg.smooth_seconds, fs)
    span = float(tu[-1] - tu[0])

    # linear trend = slow drift (reported separately, removed from sway)
    tt = tu - tu[0]
    px, py = np.polyfit(tt, x, 1), np.polyfit(tt, y, 1)
    drift = math.hypot(px[0] * span, py[0] * span)
    xd, yd = x - np.polyval(px, tt), y - np.polyval(py, tt)
    xc, yc = x - x.mean(), y - y.mean()

    d = np.hypot(xc, yc)
    step = np.hypot(np.diff(x), np.diff(y))
    path = float(step.sum())
    vel = step * fs
    vel_s = S.smooth(vel, 0.3, fs) if vel.size > 6 else vel
    acc = np.abs(np.diff(vel_s)) * fs if vel_s.size > 2 else np.zeros(1)
    cov = np.cov(np.vstack([xd, yd]))
    eig = np.clip(np.linalg.eigvalsh(cov), 0.0, None)
    px_abs, py_abs = float(np.mean(np.abs(xd))), float(np.mean(np.abs(yd)))

    out.update({
        "ok": True, "span": span, "gap_fraction": float(gap.mean()),
        "range_x": float(x.max() - x.min()), "range_y": float(y.max() - y.min()),
        "rms": float(np.sqrt(np.mean(xd ** 2 + yd ** 2))),
        "max_disp": float(d.max()), "path": path,
        "vel": float(vel.mean()) if vel.size else 0.0, "acc": float(acc.mean()),
        "drift": float(drift),
        "asym": abs(px_abs - py_abs) / (px_abs + py_abs) if (px_abs + py_abs) > 1e-12 else 0.0,
        "vel_cv": S.cv(vel),
        "ellipse": float(math.pi * CHI2_95_2DOF * math.sqrt(float(eig[0] * eig[1]))),
    })
    return out


def summarize(a: dict) -> dict:
    if not a.get("ok"):
        return {"sway_range_x": 0.0, "sway_range_y": 0.0, "sway_rms": 0.0, "max_displacement": 0.0,
                "sway_path_length": 0.0, "sway_velocity": 0.0, "sway_acceleration": 0.0,
                "normalized_drift": 0.0, "directional_asymmetry": 0.0, "sway_velocity_cv": 0.0,
                "sway_ellipse_area_95": 0.0, "analysed_seconds": 0.0}
    return {
        "sway_range_x": round(a["range_x"], 6), "sway_range_y": round(a["range_y"], 6),
        "sway_rms": round(a["rms"], 6), "max_displacement": round(a["max_disp"], 6),
        "sway_path_length": round(a["path"], 6), "sway_velocity": round(a["vel"], 6),
        "sway_acceleration": round(a["acc"], 6), "normalized_drift": round(a["drift"], 6),
        "directional_asymmetry": round(a["asym"], 4), "sway_velocity_cv": round(a["vel_cv"], 4),
        "sway_ellipse_area_95": round(a["ellipse"], 6), "analysed_seconds": round(a["span"], 2),
    }


class Balance(Challenge):
    key = "balance"
    title = "Balance"
    auto_finish = True
    instructions = ("Stand upright with your feet together.",
                    "Keep your arms relaxed by your sides and look ahead.",
                    "Stay as still as is comfortable until the timer ends.")

    def __init__(self, duration: float | None = None):
        self.target = float(duration or CFG.duration_seconds)

    def start(self, t: float) -> None:
        self.started_at = t
        self.stats = FrameStats()
        self.t: list[float] = []
        self.xy: list[list[float]] = []
        self._last_t = t

    def update(self, pf: PoseFrame | None, t: float) -> None:
        self._last_t = t
        if t - self.started_at < CFG.settle_seconds:
            return                                   # settling period is not analysed
        if not self.stats.add(pf, TORSO, QUALITY.valid_landmark_visibility):
            return
        torso = torso_length_px(pf)
        if torso < 20:
            self.stats.valid -= 1
            return
        p = pf.mid_px(L_HIP, R_HIP) / torso
        self.t.append(t)
        self.xy.append([float(p[0]), float(p[1])])

    def elapsed(self, t: float) -> float:
        return max(0.0, t - self.started_at)

    def is_complete(self, t: float) -> bool:
        return self.elapsed(t) >= self.target

    def progress(self, t: float) -> float | None:
        return min(1.0, self.elapsed(t) / self.target)

    def live(self) -> dict:
        return {"elapsed": self.elapsed(self._last_t), "target": self.target,
                "valid": self.stats.valid, "quality": self.stats.pose_quality,
                "valid_ratio": self.stats.valid_ratio,
                "settling": self.elapsed(self._last_t) < CFG.settle_seconds}

    def finish(self, t: float) -> dict:
        a = analyze(self.t, self.xy)
        feats = summarize(a)
        gate = base_gate(self.stats.valid_ratio, self.stats.pose_quality)
        gate.require(feats["analysed_seconds"] >= CFG.min_analysed_seconds,
                     f"only {feats['analysed_seconds']:.1f}s analysed; need {CFG.min_analysed_seconds:.0f}s"
                     + (f" ({a['reason']})" if a.get("reason") else ""))
        if a.get("ok"):
            gate.require(a["max_disp"] <= CFG.max_displacement,
                         "participant moved too much (not standing still)")
            gate.require(a["drift"] <= CFG.max_drift, "participant drifted across the frame")
            gate.require(a["gap_fraction"] <= 0.25, "tracking dropped out repeatedly")
        block = {"status": "completed", "engine_version": self.ENGINE_VERSION, **feats,
                 "duration_seconds": round(self.elapsed(t), 2),
                 "settle_seconds_discarded": CFG.settle_seconds,
                 "valid_frame_ratio": round(self.stats.valid_ratio, 4),
                 "average_pose_quality": round(self.stats.pose_quality, 4),
                 "quality_gate": gate.build()}
        if not self.t:
            block.update(failed_block("no usable frames recorded"))
        return block
