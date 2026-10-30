"""Sit-to-Stand (STS) engine, v1.4.

Recording is separated from analysis. While the participant moves we only
store (timestamp, left/right knee angle, trunk angle). Repetitions and all
features are then derived from the *whole* series:

1. resample to a uniform rate, remove single-frame spikes, zero-phase smooth;
2. find alternating standing peaks / seated valleys with a reversal detector
   (no fragile fixed angle thresholds, no state machine that can get stuck);
3. a repetition is a completed sit -> stand transition; each is validated for
   range of motion, plausible duration and tracking gaps;
4. timing is measured at fixed fractions (20 % / 80 %) of the participant's
   own knee-angle range, so it does not depend on chair height or camera view.
"""
from __future__ import annotations

import numpy as np

from challenges.base import Challenge, FrameStats
from core import signals as S
from core.config import QUALITY, STS as CFG
from core.pose import BODY, PoseFrame, knee_angle, trunk_inclination_deg
from core.quality import base_gate, failed_block


def analyze(t, knee_l, knee_r, trunk, cfg=CFG, fs: float = QUALITY.resample_hz) -> dict:
    """Pure function: raw recorded series -> repetition list + features."""
    out: dict = {"repetitions": 0, "valid_repetitions": 0, "invalid_repetitions": 0,
                 "reps": [], "reason": None}
    t = np.asarray(t, dtype=float)
    if t.size < int(fs):                       # < ~1 s of valid data
        out["reason"] = "not enough valid frames"
        return out

    tu, X, gap = S.resample_uniform(t, np.column_stack([knee_l, knee_r, trunk]), fs,
                                    QUALITY.max_gap_seconds)
    kl = S.smooth(S.hampel(X[:, 0]), cfg.smooth_seconds, fs)
    kr = S.smooth(S.hampel(X[:, 1]), cfg.smooth_seconds, fs)
    tr = S.smooth(S.hampel(X[:, 2]), cfg.smooth_seconds, fs)
    theta = 0.5 * (kl + kr)

    amplitude = S.robust_range(theta)
    out["knee_angle_range_deg"] = round(amplitude, 2)
    out["_series"] = {"t": tu, "theta": theta}
    if amplitude < cfg.min_amplitude_deg:
        out["reason"] = f"knee-angle swing {amplitude:.0f} deg below {cfg.min_amplitude_deg:.0f} deg"
        return out

    delta = max(cfg.min_swing_deg, cfg.min_swing_fraction * amplitude)
    piv = S.zigzag(theta, delta)
    peaks = [i for i, k in piv if k > 0]
    valleys = [i for i, k in piv if k < 0]
    if not peaks or not valleys:
        out["reason"] = "no complete sit/stand cycle"
        return out

    stand_ref = float(np.median(theta[peaks]))
    sit_ref = float(np.median(theta[valleys]))
    span = stand_ref - sit_ref
    if span < cfg.min_amplitude_deg:
        out["reason"] = "standing and seated levels are not distinct"
        return out
    up = sit_ref + cfg.upper_level * span
    lo = sit_ref + cfg.lower_level * span
    out["stand_reference_deg"] = round(stand_ref, 2)
    out["seated_reference_deg"] = round(sit_ref, 2)

    omega = S.smooth(S.gradient(theta, fs), 0.15, fs)          # deg/s
    alpha = S.gradient(omega, fs)                              # deg/s^2
    speed = np.abs(omega)
    stand_mask = theta >= (stand_ref - 0.1 * span)
    trunk_base = float(np.median(tr[stand_mask])) if stand_mask.any() else float(np.median(tr))

    reps = []
    for n, (i, kind) in enumerate(piv):
        if kind > 0 or n + 1 >= len(piv) or piv[n + 1][1] < 0:
            continue                                           # need valley followed by peak
        v_i, p_i = i, piv[n + 1][0]
        prev_peak = piv[n - 1][0] if n > 0 and piv[n - 1][1] > 0 else None

        t20 = S.first_crossing(tu, theta, v_i, p_i, lo, rising=True)
        t80 = S.first_crossing(tu, theta, v_i, p_i, up, rising=True)
        rep = {"valley_time": float(tu[v_i]), "depth_deg": float(theta[v_i]), "valid": False,
               "issues": []}
        if t20 is None or t80 is None:
            rep["issues"].append("stand-up did not reach 80% of range")
            reps.append(rep)
            continue

        start_i = v_i
        descent = dwell = None
        if prev_peak is not None:
            t_leave = S.first_crossing(tu, theta, prev_peak, v_i, up, rising=False)
            t_seat = S.first_crossing(tu, theta, prev_peak, v_i, lo, rising=False)
            if t_leave is not None and t_seat is not None:
                descent = t_seat - t_leave
                dwell = t20 - t_seat
                start_i = S.index_at_or_after(tu, t_leave)
        rise = t80 - t20
        end_i = S.index_at_or_after(tu, t80)
        t_begin = float(tu[start_i]) if descent is not None else t20

        rise_swing = float(theta[p_i] - theta[v_i])
        if rise_swing < cfg.complete_fraction * span:
            rep["issues"].append("incomplete stand-up")
        if prev_peak is not None and float(theta[prev_peak] - theta[v_i]) < cfg.complete_fraction * span:
            rep["issues"].append("incomplete sit-down")
        if not (cfg.min_rise_seconds <= rise <= cfg.max_rise_seconds):
            rep["issues"].append(f"implausible rise time {rise:.2f}s")
        if gap[start_i:end_i + 1].any():
            rep["issues"].append("tracking gap during repetition")

        w = slice(start_i, max(end_i, start_i + 1) + 1)
        rom_w = slice(prev_peak if prev_peak is not None else v_i, p_i + 1)   # full excursion
        rise_w = slice(S.index_at_or_after(tu, t20), max(end_i, S.index_at_or_after(tu, t20) + 1) + 1)
        sp = speed[rise_w]
        n_speed_peaks = max(1, sum(1 for _, k in S.zigzag(sp, 0.25 * float(sp.max())) if k > 0)) if sp.size > 3 and sp.max() > 0 else 1
        rep.update({
            "start_time": t_begin, "end_time": float(t80), "rise_time": float(rise),
            "descent_time": None if descent is None else float(descent),
            "seated_dwell": None if dwell is None else float(dwell),
            "left_rom_deg": S.robust_range(kl[rom_w], 0, 100),
            "right_rom_deg": S.robust_range(kr[rom_w], 0, 100),
            "peak_velocity": float(np.max(speed[w])),
            "mean_velocity": float(np.mean(speed[w])),
            "mean_acceleration": float(np.mean(np.abs(alpha[w]))),
            "smoothness": 1.0 / n_speed_peaks,
            "trunk_mean": float(np.mean(tr[w])),
            "trunk_peak": float(np.max(tr[w])),
            "valid": not rep["issues"],
        })
        reps.append(rep)

    out["reps"] = reps
    good = [r for r in reps if r["valid"]]
    out["repetitions"] = len(reps)
    out["valid_repetitions"] = len(good)
    out["invalid_repetitions"] = len(reps) - len(good)
    out["trunk_baseline_deg"] = trunk_base
    out["state"] = _state(theta, sit_ref, span)
    return out


def _state(theta, sit_ref, span) -> str:
    if theta.size == 0 or span <= 0:
        return "WAITING"
    frac = (float(theta[-1]) - sit_ref) / span
    return "STANDING" if frac >= 0.7 else "SITTING" if frac <= 0.3 else "MOVING"


def summarize(a: dict) -> dict:
    """Turn the analysis into the feature dictionary stored in the session."""
    good = [r for r in a.get("reps", []) if r["valid"]]

    def col(key, only_not_none=True):
        vals = [r[key] for r in good if r.get(key) is not None]
        return vals

    lrom, rrom = S.median(col("left_rom_deg")), S.median(col("right_rom_deg"))
    depths = [r["depth_deg"] for r in good]
    trunk_peaks = [r["trunk_peak"] - a.get("trunk_baseline_deg", 0.0) for r in good]
    start = min((r["start_time"] for r in good), default=None)
    end = max((r["end_time"] for r in good), default=None)
    active = (end - start) if start is not None and end is not None else 0.0
    five = None
    if len(good) >= 5:
        five = good[4]["end_time"] - good[0]["start_time"]
    return {
        "repetitions": a.get("repetitions", 0),
        "valid_repetitions": a.get("valid_repetitions", 0),
        "invalid_repetitions": a.get("invalid_repetitions", 0),
        "left_knee_rom_deg": round(lrom, 2),
        "right_knee_rom_deg": round(rrom, 2),
        "knee_rom_difference_deg": round(abs(lrom - rrom), 2),
        "knee_rom_symmetry_ratio": round(S.sym_ratio(lrom, rrom), 4),
        "average_rep_time_seconds": round(S.mean([r["end_time"] - r["start_time"] for r in good]), 3),
        "average_rise_time_seconds": round(S.mean(col("rise_time")), 3),
        "average_descent_time_seconds": round(S.mean(col("descent_time")), 3),
        "average_seated_dwell_seconds": round(S.mean(col("seated_dwell")), 3),
        "rep_time_cv": round(S.cv([r["end_time"] - r["start_time"] for r in good]), 4),
        "minimum_knee_angle_deg": round(min(depths), 2) if depths else 0.0,
        "average_seated_knee_angle_deg": round(S.mean(depths), 2),
        "depth_consistency_cv": round(S.cv(depths), 4),
        "average_trunk_inclination_deg": round(S.mean(col("trunk_mean")), 2),
        "peak_trunk_inclination_deg": round(max(col("trunk_peak"), default=0.0), 2),
        "peak_trunk_compensation_deg": round(max([0.0] + trunk_peaks), 2),
        "peak_angle_velocity_deg_per_sec": round(S.mean(col("peak_velocity")), 2),
        "mean_angle_velocity_deg_per_sec": round(S.mean(col("mean_velocity")), 2),
        "mean_angle_acceleration_deg_per_sec2": round(S.mean(col("mean_acceleration")), 2),
        "movement_smoothness": round(S.mean(col("smoothness")), 4),
        "total_active_time_seconds": round(active, 3),
        "five_rep_time_seconds": None if five is None else round(five, 3),
        "repetitions_per_minute": round(60.0 * len(good) / active, 2) if active > 1 else 0.0,
        "knee_angle_range_deg": a.get("knee_angle_range_deg", 0.0),
        "standing_reference_angle_deg": a.get("stand_reference_deg", 0.0),
        "seated_reference_angle_deg": a.get("seated_reference_deg", 0.0),
    }


class SitToStand(Challenge):
    key = "sit_to_stand"
    title = "Sit-to-Stand"
    instructions = ("Stand in front of the chair.",
                    "Sit down and stand up at a comfortable pace.",
                    "Repeat until told to stop (5 repetitions is ideal).")
    LIVE_INTERVAL = 0.5

    def start(self, t: float) -> None:
        self.started_at = t
        self.stats = FrameStats()
        self.t: list[float] = []
        self.knee_l: list[float] = []
        self.knee_r: list[float] = []
        self.trunk: list[float] = []
        self._live_at = -1e9
        self._live: dict = {"repetitions": 0, "valid_repetitions": 0, "state": "WAITING",
                            "left_rom": 0.0, "right_rom": 0.0}

    def update(self, pf: PoseFrame | None, t: float) -> None:
        if not self.stats.add(pf, BODY, QUALITY.valid_landmark_visibility):
            return
        kl, kr = knee_angle(pf, "L"), knee_angle(pf, "R")
        tr = trunk_inclination_deg(pf)
        if kl is None or kr is None or tr is None:
            self.stats.valid -= 1
            return
        self.t.append(t)
        self.knee_l.append(kl)
        self.knee_r.append(kr)
        self.trunk.append(tr)

    def live(self) -> dict:
        now = self.t[-1] if self.t else 0.0
        if now - self._live_at >= self.LIVE_INTERVAL and len(self.t) > 30:
            self._live_at = now
            a = analyze(self.t, self.knee_l, self.knee_r, self.trunk)
            s = summarize(a)
            self._live = {"repetitions": s["valid_repetitions"], "valid_repetitions": s["valid_repetitions"],
                          "state": a.get("state", "WAITING"), "left_rom": s["left_knee_rom_deg"],
                          "right_rom": s["right_knee_rom_deg"], "hint": a.get("reason")}
        self._live["quality"] = self.stats.pose_quality
        self._live["valid_ratio"] = self.stats.valid_ratio
        return self._live

    def finish(self, t: float) -> dict:
        a = analyze(self.t, self.knee_l, self.knee_r, self.trunk)
        feats = summarize(a)
        duration = (self.t[-1] - self.t[0]) if len(self.t) > 1 else 0.0
        gate = base_gate(self.stats.valid_ratio, self.stats.pose_quality)
        gate.require(duration >= CFG.min_duration_seconds,
                     f"recording {duration:.1f}s shorter than {CFG.min_duration_seconds:.0f}s")
        gate.require(feats["valid_repetitions"] >= CFG.min_valid_reps,
                     f"{feats['valid_repetitions']} valid repetition(s); need {CFG.min_valid_reps}"
                     + (f" ({a['reason']})" if a.get("reason") else ""))
        block = {
            "status": "completed", "engine_version": self.ENGINE_VERSION, **feats,
            "duration_seconds": round(t - self.started_at, 2),
            "valid_frame_ratio": round(self.stats.valid_ratio, 4),
            "average_pose_quality": round(self.stats.pose_quality, 4),
            "quality_gate": gate.build(),
            "repetition_details": [
                {k: (round(v, 3) if isinstance(v, float) else v) for k, v in r.items()}
                for r in a.get("reps", [])],
        }
        if not self.t:
            block.update(failed_block("no usable frames recorded"))
        return block
