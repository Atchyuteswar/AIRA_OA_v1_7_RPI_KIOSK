"""Flat, named feature vector used for research export and validation."""
from __future__ import annotations

FEATURE_VERSION = "1.4"

# (output name, source key, kind) per block. kind: f=float, i=int
_STS = [
    ("repetitions", "repetitions", "i"), ("valid_repetitions", "valid_repetitions", "i"),
    ("invalid_repetitions", "invalid_repetitions", "i"),
    ("left_knee_rom_deg", "left_knee_rom_deg", "f"), ("right_knee_rom_deg", "right_knee_rom_deg", "f"),
    ("knee_rom_difference_deg", "knee_rom_difference_deg", "f"),
    ("knee_rom_symmetry_ratio", "knee_rom_symmetry_ratio", "f"),
    ("average_rep_time_seconds", "average_rep_time_seconds", "f"),
    ("average_rise_time_seconds", "average_rise_time_seconds", "f"),
    ("average_descent_time_seconds", "average_descent_time_seconds", "f"),
    ("average_seated_dwell_seconds", "average_seated_dwell_seconds", "f"),
    ("rep_time_cv", "rep_time_cv", "f"),
    ("minimum_knee_angle_deg", "minimum_knee_angle_deg", "f"),
    ("depth_consistency_cv", "depth_consistency_cv", "f"),
    ("average_trunk_inclination_deg", "average_trunk_inclination_deg", "f"),
    ("peak_trunk_compensation_deg", "peak_trunk_compensation_deg", "f"),
    ("movement_smoothness", "movement_smoothness", "f"),
    ("peak_angle_velocity_deg_per_sec", "peak_angle_velocity_deg_per_sec", "f"),
    ("mean_angle_velocity_deg_per_sec", "mean_angle_velocity_deg_per_sec", "f"),
    ("mean_angle_acceleration_deg_per_sec2", "mean_angle_acceleration_deg_per_sec2", "f"),
    ("repetitions_per_minute", "repetitions_per_minute", "f"),
    ("valid_frame_ratio", "valid_frame_ratio", "f"), ("average_pose_quality", "average_pose_quality", "f"),
]
_GAIT = [
    ("total_steps", "total_steps", "i"), ("left_steps", "left_steps", "i"), ("right_steps", "right_steps", "i"),
    ("walking_bout_seconds", "walking_bout_seconds", "f"),
    ("cadence_steps_per_minute", "cadence_steps_per_minute", "f"),
    ("left_right_step_balance", "left_right_step_balance", "f"),
    ("step_length_symmetry_proxy", "step_length_symmetry_proxy", "f"),
    ("average_step_interval_seconds", "average_step_interval_seconds", "f"),
    ("step_interval_std_seconds", "step_interval_std_seconds", "f"),
    ("step_interval_cv", "step_interval_cv", "f"),
    ("average_step_length_proxy", "average_step_length_proxy", "f"), ("step_length_cv", "step_length_cv", "f"),
    ("left_knee_rom_deg", "left_knee_rom_deg", "f"), ("right_knee_rom_deg", "right_knee_rom_deg", "f"),
    ("knee_rom_symmetry_ratio", "knee_rom_symmetry_ratio", "f"),
    ("hip_vertical_oscillation", "hip_vertical_oscillation", "f"),
    ("valid_frame_ratio", "valid_frame_ratio", "f"), ("average_pose_quality", "average_pose_quality", "f"),
]
_BALANCE = [
    ("duration_seconds", "analysed_seconds", "f"),
    ("sway_range_x", "sway_range_x", "f"), ("sway_range_y", "sway_range_y", "f"),
    ("sway_rms", "sway_rms", "f"), ("max_displacement", "max_displacement", "f"),
    ("sway_path_length", "sway_path_length", "f"), ("sway_velocity", "sway_velocity", "f"),
    ("sway_acceleration", "sway_acceleration", "f"), ("normalized_drift", "normalized_drift", "f"),
    ("directional_asymmetry", "directional_asymmetry", "f"), ("sway_velocity_cv", "sway_velocity_cv", "f"),
    ("sway_ellipse_area_95", "sway_ellipse_area_95", "f"),
    ("valid_frame_ratio", "valid_frame_ratio", "f"), ("average_pose_quality", "average_pose_quality", "f"),
]


def _cast(value, kind):
    try:
        return int(value) if kind == "i" else float(value)
    except (TypeError, ValueError):
        return 0 if kind == "i" else 0.0


def _flatten(prefix, block, spec, out):
    block = block or {}
    for name, src, kind in spec:
        out[f"{prefix}_{name}"] = _cast(block.get(src, 0), kind)


def unified_vector(data: dict) -> dict:
    out: dict = {"feature_version": FEATURE_VERSION}
    _flatten("sts", data.get("sit_to_stand"), _STS, out)
    _flatten("gait", data.get("gait"), _GAIT, out)
    _flatten("balance", data.get("balance"), _BALANCE, out)
    q = data.get("questionnaire") or {}
    out["questionnaire_score"] = _cast(q.get("score", 0), "f")
    out["questionnaire_max_score"] = _cast(q.get("max_score", 0), "f")
    return out
