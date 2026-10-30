"""Gait engine, v1.4.

Steps are detected from the *separation of the two ankles* along its dominant
axis (PCA of the 2-D ankle-difference vector, in torso-length units). Each
extremum of that oscillating signal is a step (the moment the feet are
farthest apart, i.e. the leading foot lands). This works for walking across
the frame, walking towards the camera and marching in place, and it is
independent of frame rate because it runs offline on timestamped data.

Fixes over v1.3
* cadence uses the walking bout, not idle time before/after walking or paused time;
* left/right *counts* of an alternating gait are always ~equal, so symmetry is
  now measured from left-vs-right step *time* and step *length proxy*;
* the "hip path" (which just measured how far the person walked across the
  frame) is replaced by vertical hip oscillation;
* knee ROM uses a percentile range instead of max-min over the whole recording.
"""
from __future__ import annotations

import numpy as np

from challenges.base import Challenge, FrameStats
from core import signals as S
from core.config import GAIT as CFG, QUALITY
from core.pose import (BODY, L_ANKLE, L_HIP, R_ANKLE, R_HIP, PoseFrame, knee_angle,
                       torso_length_px)
from core.quality import base_gate, failed_block


def _principal_axis(sep: np.ndarray) -> np.ndarray:
    c = sep - sep.mean(axis=0)
    w, v = np.linalg.eigh(np.cov(c.T))
    u = v[:, int(np.argmax(w))]
    if abs(u[0]) >= abs(u[1]):
        u = u if u[0] >= 0 else -u
    else:
        u = u if u[1] >= 0 else -u
    return u


def analyze(t, sep, hip, knee_l, knee_r, cfg=CFG, fs: float = QUALITY.resample_hz) -> dict:
    out: dict = {"steps": [], "reason": None}
    t = np.asarray(t, dtype=float)
    if t.size < int(fs * 1.5):
        out["reason"] = "not enough valid frames"
        return out

    X = np.column_stack([np.asarray(sep), np.asarray(hip), knee_l, knee_r])
    tu, Y, gap = S.resample_uniform(t, X, fs, QUALITY.max_gap_seconds)
    Y = np.column_stack([S.smooth(S.hampel(Y[:, k]), cfg.smooth_seconds, fs) for k in range(Y.shape[1])])
    sep_u, hip_u, kl, kr = Y[:, 0:2], Y[:, 2:4], Y[:, 4], Y[:, 5]

    u = _principal_axis(sep_u)
    s1 = sep_u @ u
    rng = S.robust_range(s1)
    out["separation_range"] = round(rng, 3)
    if rng < cfg.min_separation_range:
        out["reason"] = "little leg movement detected"
        return out

    delta = max(cfg.min_swing_abs, cfg.min_swing_fraction * rng)
    piv = [(i, k) for i, k in S.zigzag(s1, delta) if i > 1]
    if len(piv) < 3:
        out["reason"] = "fewer than 3 steps detected"
        return out

    idx = np.array([i for i, _ in piv])
    kinds = np.array([k for _, k in piv])
    times = tu[idx]
    dts = np.diff(times)
    ok = (dts >= cfg.min_step_seconds) & (dts <= cfg.max_step_seconds)

    # longest run of plausible consecutive steps = the walking bout
    best = (0, 0)
    run_start = 0
    for j in range(len(ok) + 1):
        if j == len(ok) or not ok[j]:
            if j - run_start > best[1] - best[0]:
                best = (run_start, j)
            run_start = j + 1
    a, b = best[0], best[1] + 1                 # step indices a..b-1
    if b - a < 3:
        out["reason"] = "no sustained walking detected"
        return out
    idx, kinds, times = idx[a:b], kinds[a:b], times[a:b]
    dts = np.diff(times)

    # direction of travel along the analysis axis decides which extremum is LEFT
    hp = hip_u @ u
    travel = float(hp[idx[-1]] - hp[idx[0]])
    if travel >= cfg.travel_threshold:
        left_kind, reliable, direction = +1, True, "positive"
    elif travel <= -cfg.travel_threshold:
        left_kind, reliable, direction = -1, True, "negative"
    else:
        left_kind, reliable, direction = +1, False, "in_place"
    is_left = kinds == left_kind

    # ankle_L - ankle_R is antisymmetric under a left/right swap, so |s1| at each
    # step is directly that step's length proxy (no centring, otherwise a real
    # left/right difference would be subtracted away).
    amps = np.abs(s1[idx])
    interval_after = dts                                       # time to the *next* step
    left_iv = interval_after[is_left[:-1]]
    right_iv = interval_after[~is_left[:-1]]

    bout = slice(int(idx[0]), int(idx[-1]) + 1)
    hy = hip_u[:, 1]
    hy_hp = hy - S.moving_average(hy, int(fs))                # remove drift / approach
    bout_sec = float(times[-1] - times[0])
    out.update({
        "times": times, "is_left": is_left, "amps": amps, "intervals": dts,
        "left_iv": left_iv, "right_iv": right_iv,
        "reliable": reliable, "direction": direction, "travel": travel,
        "bout_seconds": bout_sec,
        "knee_l_rom": S.robust_range(kl[bout]), "knee_r_rom": S.robust_range(kr[bout]),
        "hip_osc": float(np.std(hy_hp[bout])),
        "gap_in_bout": bool(gap[bout].any()),
    })
    out["steps"] = list(times)
    return out


def summarize(a: dict) -> dict:
    if not a.get("steps"):
        return {"total_steps": 0, "left_steps": 0, "right_steps": 0, "walking_bout_seconds": 0.0,
                "cadence_steps_per_minute": 0.0, "left_right_step_balance": 0.0,
                "step_length_symmetry_proxy": 0.0, "average_step_interval_seconds": 0.0,
                "step_interval_std_seconds": 0.0, "step_interval_cv": 0.0,
                "average_step_length_proxy": 0.0, "step_length_cv": 0.0,
                "left_knee_rom_deg": 0.0, "right_knee_rom_deg": 0.0,
                "knee_rom_symmetry_ratio": 0.0, "hip_vertical_oscillation": 0.0,
                "side_labels_reliable": False, "travel_direction": "unknown"}
    is_left, amps, iv = a["is_left"], a["amps"], a["intervals"]
    n = len(a["steps"])
    mean_iv = float(np.mean(iv))
    l_iv, r_iv = a["left_iv"], a["right_iv"]
    time_sym = S.sym_ratio(np.mean(l_iv), np.mean(r_iv)) if len(l_iv) and len(r_iv) else 0.0
    len_sym = (S.sym_ratio(np.mean(amps[is_left]), np.mean(amps[~is_left]))
               if is_left.any() and (~is_left).any() else 0.0)
    return {
        "total_steps": n,
        "left_steps": int(is_left.sum()),
        "right_steps": int((~is_left).sum()),
        "walking_bout_seconds": round(a["bout_seconds"], 2),
        "cadence_steps_per_minute": round(60.0 * (n - 1) / a["bout_seconds"], 2) if a["bout_seconds"] > 0 else 0.0,
        "left_right_step_balance": round(time_sym, 4),
        "step_length_symmetry_proxy": round(len_sym, 4),
        "average_step_interval_seconds": round(mean_iv, 4),
        "step_interval_std_seconds": round(float(np.std(iv)), 4),
        "step_interval_cv": round(S.cv(iv), 4),
        "average_step_length_proxy": round(float(np.mean(amps)), 4),
        "step_length_cv": round(S.cv(amps), 4),
        "left_knee_rom_deg": round(a["knee_l_rom"], 2),
        "right_knee_rom_deg": round(a["knee_r_rom"], 2),
        "knee_rom_symmetry_ratio": round(S.sym_ratio(a["knee_l_rom"], a["knee_r_rom"]), 4),
        "hip_vertical_oscillation": round(a["hip_osc"], 4),
        "side_labels_reliable": bool(a["reliable"]),
        "travel_direction": a["direction"],
    }


class Gait(Challenge):
    key = "gait"
    title = "Gait"
    instructions = ("Walk naturally in view of the camera.",
                    "Keep your whole body visible, including feet.",
                    "Continue for about 10-15 seconds, then press ENTER.")
    LIVE_INTERVAL = 0.5

    def start(self, t: float) -> None:
        self.started_at = t
        self.stats = FrameStats()
        self.t: list[float] = []
        self.sep: list[list[float]] = []
        self.hip: list[list[float]] = []
        self.kl: list[float] = []
        self.kr: list[float] = []
        self._live_at = -1e9
        self._live = {"steps": 0, "cadence": 0.0, "left": 0, "right": 0, "last": "WAITING"}

    def update(self, pf: PoseFrame | None, t: float) -> None:
        if not self.stats.add(pf, BODY, QUALITY.valid_landmark_visibility):
            return
        torso = torso_length_px(pf)
        kl, kr = knee_angle(pf, "L"), knee_angle(pf, "R")
        if torso < 20 or kl is None or kr is None:          # degenerate skeleton
            self.stats.valid -= 1
            return
        sep = (pf.px(L_ANKLE) - pf.px(R_ANKLE)) / torso
        hip = pf.mid_px(L_HIP, R_HIP) / torso
        self.t.append(t)
        self.sep.append([float(sep[0]), float(sep[1])])
        self.hip.append([float(hip[0]), float(hip[1])])
        self.kl.append(kl)
        self.kr.append(kr)

    def _analyse(self) -> dict:
        return analyze(self.t, self.sep, self.hip, self.kl, self.kr)

    def live(self) -> dict:
        now = self.t[-1] if self.t else 0.0
        if now - self._live_at >= self.LIVE_INTERVAL and len(self.t) > 45:
            self._live_at = now
            s = summarize(self._analyse())
            self._live.update(steps=s["total_steps"], cadence=s["cadence_steps_per_minute"],
                              left=s["left_steps"], right=s["right_steps"],
                              last="WALKING" if s["total_steps"] else "WAITING")
        self._live["quality"] = self.stats.pose_quality
        self._live["valid_ratio"] = self.stats.valid_ratio
        return self._live

    def finish(self, t: float) -> dict:
        a = self._analyse()
        feats = summarize(a)
        gate = base_gate(self.stats.valid_ratio, self.stats.pose_quality)
        gate.require(feats["total_steps"] >= CFG.min_steps,
                     f"{feats['total_steps']} steps detected; need {CFG.min_steps}"
                     + (f" ({a['reason']})" if a.get("reason") else ""))
        gate.require(feats["walking_bout_seconds"] >= CFG.min_bout_seconds,
                     f"walking bout {feats['walking_bout_seconds']:.1f}s shorter than {CFG.min_bout_seconds:.0f}s")
        block = {"status": "completed", "engine_version": self.ENGINE_VERSION, **feats,
                 "duration_seconds": round(t - self.started_at, 2),
                 "valid_frame_ratio": round(self.stats.valid_ratio, 4),
                 "average_pose_quality": round(self.stats.pose_quality, 4),
                 "quality_gate": gate.build()}
        if not self.t:
            block.update(failed_block("no usable frames recorded"))
        return block
