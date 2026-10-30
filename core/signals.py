"""Numerical building blocks (NumPy only).

All movement analysis in v1.4 is done *offline on the recorded time series*
(with real capture timestamps) rather than frame-by-frame state machines.
That makes results independent of the frame rate, lets us use zero-phase
smoothing, and guarantees that the live counters shown on screen are exactly
what ends up in the saved record.
"""
from __future__ import annotations

import math
from typing import Iterable, Sequence

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view


# ----------------------------------------------------------------- basic stats
def finite(values: Iterable[float]) -> list[float]:
    return [float(v) for v in values if v is not None and math.isfinite(float(v))]


def mean(values: Iterable[float], default: float = 0.0) -> float:
    v = finite(values)
    return float(sum(v) / len(v)) if v else default


def median(values: Iterable[float], default: float = 0.0) -> float:
    v = finite(values)
    return float(np.median(v)) if v else default


def cv(values: Iterable[float]) -> float:
    """Coefficient of variation (population std / |mean|); 0 when undefined."""
    v = np.asarray(finite(values), dtype=float)
    if v.size < 2:
        return 0.0
    m = float(np.mean(v))
    if abs(m) < 1e-9:
        return 0.0
    return float(np.std(v) / abs(m))


def sym_ratio(a: float, b: float) -> float:
    """min/max symmetry ratio in [0, 1]; 0 when both are ~0 (undefined)."""
    a, b = abs(float(a)), abs(float(b))
    hi = max(a, b)
    if hi <= 1e-9:
        return 0.0
    return min(a, b) / hi


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def robust_range(y: Sequence[float], lo: float = 5.0, hi: float = 95.0) -> float:
    """Percentile range: immune to single-frame pose glitches."""
    a = np.asarray(finite(y), dtype=float)
    if a.size == 0:
        return 0.0
    return float(np.percentile(a, hi) - np.percentile(a, lo))


# --------------------------------------------------------------- conditioning
def hampel(y: np.ndarray, half_window: int = 2, n_sigmas: float = 3.5,
           min_sigma: float = 1e-6) -> np.ndarray:
    """Replace isolated spikes by the local median (pose landmark glitches)."""
    y = np.asarray(y, dtype=float)
    n = y.size
    if n < 2 * half_window + 1:
        return y.copy()
    padded = np.pad(y, half_window, mode="edge")
    win = sliding_window_view(padded, 2 * half_window + 1)
    med = np.median(win, axis=1)
    mad = np.median(np.abs(win - med[:, None]), axis=1) * 1.4826
    bad = np.abs(y - med) > n_sigmas * np.maximum(mad, min_sigma)
    out = y.copy()
    out[bad] = med[bad]
    return out


def moving_average(y: np.ndarray, window: int) -> np.ndarray:
    y = np.asarray(y, dtype=float)
    window = int(max(1, window))
    if window <= 1 or y.size <= window:
        return y.copy()
    left = window // 2
    right = window - 1 - left
    padded = np.pad(y, (left, right), mode="reflect")
    return np.convolve(padded, np.ones(window) / window, mode="valid")


def smooth(y: np.ndarray, seconds: float, fs: float) -> np.ndarray:
    """Zero-phase (no lag) triangular smoothing of roughly ``seconds`` width."""
    w = max(1, int(round(seconds * fs / 2.0)) + 1)
    return moving_average(moving_average(y, w), w)


def resample_uniform(t: Sequence[float], y: np.ndarray, fs: float,
                     max_gap: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Linear resample onto a uniform grid.

    Returns ``(t_uniform, y_uniform, gap_mask)``. ``gap_mask`` is True where the
    grid point lies inside a hole longer than ``max_gap`` seconds; values there
    are interpolated only so arrays stay contiguous and must not be trusted.
    """
    t = np.asarray(t, dtype=float)
    y = np.asarray(y, dtype=float)
    if t.size < 2:
        return t.copy(), y.copy(), np.zeros(t.size, dtype=bool)
    grid = np.arange(t[0], t[-1], 1.0 / fs)
    if grid.size == 0:
        grid = t[:1].copy()
    if y.ndim == 1:
        yu = np.interp(grid, t, y)
    else:
        yu = np.column_stack([np.interp(grid, t, y[:, k]) for k in range(y.shape[1])])
    idx = np.clip(np.searchsorted(t, grid, side="right"), 1, t.size - 1)
    gap = (t[idx] - t[idx - 1]) > max_gap
    return grid, yu, gap


def gradient(y: np.ndarray, fs: float) -> np.ndarray:
    if y.size < 2:
        return np.zeros_like(y)
    return np.gradient(y, 1.0 / fs)


# ------------------------------------------------------------ event detection
def zigzag(y: np.ndarray, delta: float) -> list[tuple[int, int]]:
    """Alternating peaks/valleys separated by reversals of at least ``delta``.

    Returns ``[(index, kind)]`` with ``kind=+1`` for a peak and ``-1`` for a
    valley. The last, still-developing extreme is included (it is a real
    extreme as long as the trend that produced it was confirmed).
    """
    y = np.asarray(y, dtype=float)
    n = y.size
    if n < 3 or delta <= 0:
        return []
    pivots: list[tuple[int, int]] = []
    hi_i = lo_i = 0
    hi_v = lo_v = float(y[0])
    trend = 0            # +1 climbing toward a peak, -1 falling toward a valley
    cand_i, cand_v = 0, float(y[0])
    for i in range(1, n):
        v = float(y[i])
        if trend == 0:
            if v > hi_v:
                hi_i, hi_v = i, v
            if v < lo_v:
                lo_i, lo_v = i, v
            if v - lo_v >= delta:            # first confirmed move is upward
                pivots.append((lo_i, -1))
                trend, cand_i, cand_v = 1, i, v
            elif hi_v - v >= delta:          # first confirmed move is downward
                pivots.append((hi_i, +1))
                trend, cand_i, cand_v = -1, i, v
            continue
        if trend == 1:
            if v > cand_v:
                cand_i, cand_v = i, v
            elif cand_v - v >= delta:
                pivots.append((cand_i, +1))
                trend, cand_i, cand_v = -1, i, v
        else:
            if v < cand_v:
                cand_i, cand_v = i, v
            elif v - cand_v >= delta:
                pivots.append((cand_i, -1))
                trend, cand_i, cand_v = 1, i, v
    if trend == 1:
        pivots.append((cand_i, +1))
    elif trend == -1:
        pivots.append((cand_i, -1))
    return pivots


def first_crossing(t: np.ndarray, y: np.ndarray, start: int, stop: int,
                   level: float, rising: bool) -> float | None:
    """Time (linearly interpolated) at which ``y`` first crosses ``level``."""
    stop = min(stop, y.size - 1)
    for i in range(max(start, 1), stop + 1):
        a, b = y[i - 1], y[i]
        hit = (a < level <= b) if rising else (a > level >= b)
        if hit:
            if b == a:
                return float(t[i])
            frac = (level - a) / (b - a)
            return float(t[i - 1] + frac * (t[i] - t[i - 1]))
    return None


def index_at_or_after(t: np.ndarray, value: float) -> int:
    return int(min(np.searchsorted(t, value, side="left"), t.size - 1))
