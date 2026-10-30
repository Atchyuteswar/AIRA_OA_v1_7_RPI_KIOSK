import numpy as np
import pytest

from challenges import balance, gait, sit_to_stand as sts
from core import signals as S
from tests import synthetic as syn


# ------------------------------------------------------------------ signals
def test_zigzag_finds_alternating_extremes():
    t = np.arange(0, 10, 1 / 30)
    y = 100 + 50 * np.sin(2 * np.pi * 0.5 * t)
    kinds = [k for _, k in S.zigzag(y, 20)]
    assert all(a != b for a, b in zip(kinds, kinds[1:]))
    assert len(kinds) >= 9


def test_zigzag_ignores_noise():
    y = 100 + np.random.default_rng(0).normal(0, 2, 300)
    assert S.zigzag(y, 15) == []


def test_hampel_removes_spike():
    y = np.ones(50)
    y[20] = 90
    assert S.hampel(y)[20] == pytest.approx(1.0)


def test_resample_flags_long_gap():
    t = np.r_[np.arange(0, 2, 0.033), np.arange(4, 6, 0.033)]
    _, _, gap = S.resample_uniform(t, np.zeros(t.size), 30, 0.6)
    assert gap.any() and not gap[:30].any()


def test_sym_ratio_edge_cases():
    assert S.sym_ratio(0, 0) == 0.0
    assert S.sym_ratio(50, 100) == pytest.approx(0.5)
    assert S.cv([5]) == 0.0


# ------------------------------------------------------------ sit-to-stand
@pytest.mark.parametrize("fs", [10, 15, 20, 30])
@pytest.mark.parametrize("noise", [1.0, 3.0, 5.0])
@pytest.mark.parametrize("period", [2.0, 3.0, 5.0])
def test_sts_counts_five_reps_any_fps_noise_pace(fs, noise, period):
    for seed in range(3):
        a = sts.analyze(*syn.sts_signal(fs=fs, noise=noise, period=period, seed=seed))
        assert (a["repetitions"], a["valid_repetitions"]) == (5, 5)


def test_sts_no_movement_gives_zero_reps():
    t = np.arange(0, 10, 1 / 30)
    a = sts.analyze(t, 170 + np.random.normal(0, 1, t.size), 170 + np.random.normal(0, 1, t.size), 10 + t * 0)
    assert a["repetitions"] == 0 and a["reason"]


def test_sts_occlusion_gap_marks_repetition_invalid():
    t, kl, kr, tr = syn.sts_signal(n_reps=4)
    keep = ~((t > 4.5) & (t < 7.5))
    a = sts.analyze(t[keep], kl[keep], kr[keep], tr[keep])
    assert a["invalid_repetitions"] >= 1 and a["valid_repetitions"] >= 2


def test_sts_symmetry_reflects_asymmetric_knees():
    s_sym = sts.summarize(sts.analyze(*syn.sts_signal(asym=1.0)))
    s_asym = sts.summarize(sts.analyze(*syn.sts_signal(asym=0.75)))
    assert s_sym["knee_rom_symmetry_ratio"] > s_asym["knee_rom_symmetry_ratio"] + 0.1


def test_sts_timing_features_plausible():
    s = sts.summarize(sts.analyze(*syn.sts_signal(period=3.0)))
    assert 0.2 < s["average_rise_time_seconds"] < 1.0
    assert s["five_rep_time_seconds"] and 10 < s["five_rep_time_seconds"] < 16


# --------------------------------------------------------------------- gait
@pytest.mark.parametrize("fs", [10, 15, 30])
@pytest.mark.parametrize("step_hz", [1.2, 1.8, 2.2])
def test_gait_step_count_and_cadence(fs, step_hz):
    s = gait.summarize(gait.analyze(*syn.gait_signal(fs=fs, step_hz=step_hz)))
    assert abs(s["total_steps"] - round(step_hz * 10)) <= 2
    assert s["cadence_steps_per_minute"] == pytest.approx(step_hz * 60, rel=0.1)


def test_gait_idle_time_does_not_dilute_cadence():
    # 10 s walking + 12 s standing before and after
    fast = gait.summarize(gait.analyze(*syn.gait_signal(walk=(12.0, 22.0), tail=12.0)))
    assert fast["cadence_steps_per_minute"] == pytest.approx(108, rel=0.1)


def test_gait_detects_step_length_and_timing_asymmetry():
    base = gait.summarize(gait.analyze(*syn.gait_signal()))
    length = gait.summarize(gait.analyze(*syn.gait_signal(asym=0.7)))
    timing = gait.summarize(gait.analyze(*syn.gait_signal(timing_asym=0.35)))
    assert length["step_length_symmetry_proxy"] < base["step_length_symmetry_proxy"] - 0.15
    assert timing["left_right_step_balance"] < base["left_right_step_balance"] - 0.15


def test_gait_direction_and_marching_in_place():
    assert gait.summarize(gait.analyze(*syn.gait_signal(direction=-1)))["travel_direction"] == "negative"
    inplace = gait.summarize(gait.analyze(*syn.gait_signal(in_place=True)))
    assert inplace["total_steps"] > 10 and inplace["side_labels_reliable"] is False


def test_gait_standing_still_is_not_walking():
    t = np.arange(0, 10, 1 / 30)
    rng = np.random.default_rng(0)
    a = gait.analyze(t, rng.normal(0, .01, (t.size, 2)), rng.normal(0, .01, (t.size, 2)),
                     140 + rng.normal(0, 1, t.size), 140 + rng.normal(0, 1, t.size))
    assert not a["steps"]


# ------------------------------------------------------------------ balance
def test_balance_rms_grows_with_sway():
    r = [balance.summarize(balance.analyze(*syn.balance_signal(sway=s)))["sway_rms"] for s in (0.005, 0.02, 0.05)]
    assert r[0] < r[1] < r[2]


def test_balance_detects_drift_and_frame_rate_independence():
    a = balance.analyze(*syn.balance_signal(drift=0.8))
    assert a["drift"] > 0.5
    r30 = balance.summarize(balance.analyze(*syn.balance_signal(fs=30, noise=0.0)))["sway_rms"]
    r15 = balance.summarize(balance.analyze(*syn.balance_signal(fs=15, noise=0.0)))["sway_rms"]
    assert r30 == pytest.approx(r15, rel=0.1)
