"""Quality-aware movement fingerprint (fusion of qualified modalities)."""
from __future__ import annotations

from core import signals as S
from core.quality import PASS

VERSION = "1.4"
MODALITIES = ("sit_to_stand", "gait", "balance")


def quality_weight(block: dict) -> float:
    """0.5 x pose quality + 0.5 x valid-frame ratio, only for a passed gate."""
    gate = (block or {}).get("quality_gate") or {}
    if not block or block.get("status") == "skipped" or gate.get("status") != PASS:
        return 0.0
    pose = S.clamp(block.get("average_pose_quality", 0.0))
    valid = S.clamp(block.get("valid_frame_ratio", 0.0))
    return S.clamp(0.5 * pose + 0.5 * valid)


def _f(block, key, digits=4):
    try:
        return round(float((block or {}).get(key, 0.0)), digits)
    except (TypeError, ValueError):
        return 0.0


def build_fingerprint(data: dict) -> dict:
    blocks = {m: data.get(m) or {} for m in MODALITIES}
    sts, gait, bal = blocks["sit_to_stand"], blocks["gait"], blocks["balance"]
    q = data.get("questionnaire") or {}

    weights = {m: quality_weight(b) for m, b in blocks.items()}
    qualified = [m for m in MODALITIES if weights[m] > 0]
    excluded = [m for m in MODALITIES if m not in qualified]
    total = sum(weights[m] for m in qualified)

    sym_sources = {"sit_to_stand": _f(sts, "knee_rom_symmetry_ratio"),
                   "gait": _f(gait, "left_right_step_balance")}
    sym_w = sum(weights[m] for m in sym_sources if m in qualified)
    weighted_sym = (sum(weights[m] * sym_sources[m] for m in sym_sources if m in qualified) / sym_w
                    if sym_w else 0.0)

    step_var = _f(gait, "step_interval_cv")
    return {
        "version": VERSION,
        "method": "quality_weighted_personalized_challenge_response_fingerprint",
        "personalization": {"baseline_status": "PENDING_BASELINE", "baseline_assessment_id": None},
        "challenge_response": {
            "sit_to_stand": {
                "knee_rom_symmetry": _f(sts, "knee_rom_symmetry_ratio"),
                "knee_rom_difference_deg": _f(sts, "knee_rom_difference_deg", 3),
                "rep_time_seconds": _f(sts, "average_rep_time_seconds", 3),
                "rep_time_cv": _f(sts, "rep_time_cv"),
                "rise_time_seconds": _f(sts, "average_rise_time_seconds", 3),
                "movement_smoothness": _f(sts, "movement_smoothness"),
                "trunk_inclination_deg": _f(sts, "average_trunk_inclination_deg", 3),
            },
            "gait": {
                "step_balance": _f(gait, "left_right_step_balance"),
                "step_length_symmetry": _f(gait, "step_length_symmetry_proxy"),
                "cadence_steps_per_minute": _f(gait, "cadence_steps_per_minute", 3),
                "step_interval_cv": step_var,
                "step_regularness": round(S.clamp(1.0 / (1.0 + max(0.0, step_var))), 4),
                "knee_rom_symmetry": _f(gait, "knee_rom_symmetry_ratio"),
            },
            "balance": {
                "sway_rms": _f(bal, "sway_rms", 6),
                "max_displacement": _f(bal, "max_displacement", 6),
                "sway_velocity": _f(bal, "sway_velocity", 6),
                "sway_acceleration": _f(bal, "sway_acceleration", 6),
                "sway_ellipse_area_95": _f(bal, "sway_ellipse_area_95", 6),
            },
        },
        "symmetry": {"sts": sym_sources["sit_to_stand"], "gait": sym_sources["gait"],
                     "combined_quality_weighted": round(weighted_sym, 4)},
        "quality": {**{m: round(weights[m], 4) for m in MODALITIES},
                    # mean confidence of the modalities that were fused
                    "fusion_quality": round(total / len(qualified), 4) if qualified else 0.0,
                    # how much of the full 3-modality evidence base was available
                    "fusion_coverage": round(total / len(MODALITIES), 4),
                    "modality_coverage": round(len(qualified) / len(MODALITIES), 4)},
        "symptom_profile": {"score": q.get("score", 0), "max_score": q.get("max_score", 0)},
        "modality_fusion": {"qualified_modalities": qualified, "excluded_modalities": excluded,
                            "quality_weights": {m: round(weights[m], 4) for m in MODALITIES},
                            "fusion_quality": round(total / len(qualified), 4) if qualified else 0.0},
    }
