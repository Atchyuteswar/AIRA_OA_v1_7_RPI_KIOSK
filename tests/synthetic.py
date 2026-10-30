"""Synthetic signal generators shared by the tests."""
from __future__ import annotations

import numpy as np


def sts_signal(n_reps=5, period=3.0, fs=30, noise=1.5, seed=1, amp=75, sit=95, spikes=True, asym=0.97):
    rng = np.random.default_rng(seed)
    t = np.arange(0, n_reps * period + 2, 1 / fs)
    ph = np.mod((t - 1.0) / period, 1.0)
    prof = np.where(ph < 0.3, sit + amp - amp * 0.5 * (1 - np.cos(np.pi * ph / 0.3)),
           np.where(ph < 0.5, sit,
           np.where(ph < 0.8, sit + amp * 0.5 * (1 - np.cos(np.pi * (ph - 0.5) / 0.3)), sit + amp)))
    th = np.where(t < 1.0, sit + amp, prof)
    kl = th + rng.normal(0, noise, t.size)
    kr = th * asym + rng.normal(0, noise, t.size)
    tr = 10 + (170 - th) * 0.3 + rng.normal(0, 0.5, t.size)
    if spikes:
        idx = rng.choice(t.size, 6, replace=False)
        kl[idx] += rng.choice([-60, 60], 6)
    return t, kl, kr, tr


def gait_signal(fs=30, step_hz=1.8, walk=(2.0, 12.0), speed=0.9, noise=0.02, seed=0, asym=1.0,
                direction=1, in_place=False, tail=2.0, timing_asym=0.0):
    rng = np.random.default_rng(seed)
    t = np.sort(np.arange(0, walk[1] + tail, 1 / fs) + rng.normal(0, 0.003, int((walk[1] + tail) * fs)))
    dur = walk[1] - walk[0]
    ramp = np.clip((t - walk[0]) / 0.8, 0, 1) * np.clip((walk[1] - t) / 0.8, 0, 1)
    ph = 2 * np.pi * (step_hz / 2) * (t - walk[0])
    if timing_asym:
        ph = ph + timing_asym * np.sin(ph)
    sepx = 0.35 * ramp * np.sin(ph) * np.where(np.sin(ph) > 0, 1.0, asym) * direction + rng.normal(0, noise, t.size)
    sepy = 0.05 * ramp * np.cos(2 * ph) + rng.normal(0, noise, t.size)
    hipx = direction * speed * np.clip(t - walk[0], 0, dur) * (0 if in_place else 1)
    hipy = 1.2 + 0.03 * ramp * np.sin(2 * ph) + rng.normal(0, 0.005, t.size)
    kl = 140 + 20 * ramp * np.sin(ph) + rng.normal(0, 1, t.size)
    kr = 140 + 20 * ramp * np.sin(ph + np.pi) + rng.normal(0, 1, t.size)
    return t, np.column_stack([sepx, sepy]), np.column_stack([hipx, hipy]), kl, kr


def balance_signal(fs=30, dur=9, sway=0.01, noise=0.004, drift=0.0, seed=0):
    rng = np.random.default_rng(seed)
    t = np.arange(0, dur, 1 / fs)
    x = 1.0 + sway * np.sin(2 * np.pi * 0.3 * t) + drift * t / dur + rng.normal(0, noise, t.size)
    y = 2.0 + 0.5 * sway * np.sin(2 * np.pi * 0.5 * t + 1) + rng.normal(0, noise, t.size)
    return t, np.column_stack([x, y])
