"""Central, typed configuration. Every tunable threshold lives here."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CameraConfig:
    requested_width: int = 1280
    requested_height: int = 720
    requested_fps: int = 30
    minimum_acceptable_fps: float = 24.0
    minimum_acceptable_width: int = 1280
    minimum_acceptable_height: int = 720
    max_scan_index: int = 6
    warmup_frames: int = 6
    max_read_failures: int = 45          # consecutive failed reads before "lost"
    reconnect_attempts: int = 4
    # Set True only if the camera driver/app already mirrors the image
    # (some phone-webcam apps do). Pose is always analysed on the un-mirrored
    # image so that LEFT/RIGHT refer to the participant's anatomy.
    source_is_mirrored: bool = False
    inference_width: int = 960           # pose runs on a downscaled copy


@dataclass(frozen=True)
class PoseConfig:
    # Knee angles from MediaPipe's metric 3-D "world" landmarks are robust to
    # camera angle but their depth axis is estimated. Set False to use the
    # 2-D image-plane angle instead (best for a strict side-on camera).
    use_world_landmarks: bool = True
    model_complexity: int = 1


@dataclass(frozen=True)
class DisplayConfig:
    # The physical Raspberry Pi kiosk is a 7-inch 1024x600 touchscreen.
    # Desktop remains 1280x720; Pi mode renders natively at the panel resolution.
    canvas_width: int = 1024 if __import__("os").environ.get("AIRA_RPI", "0") == "1" else 1280
    # 600 px panel minus the 64 px touch action bar (core.display.TOUCH_BAR_H), so the
    # drawn interface never sits underneath the bar.
    canvas_height: int = 536 if __import__("os").environ.get("AIRA_RPI", "0") == "1" else 720
    mirror_preview: bool = True          # display-only, never used for analysis


@dataclass(frozen=True)
class QualityConfig:
    valid_landmark_visibility: float = 0.60   # a frame counts as valid above this
    minimum_pose_quality: float = 0.60        # mean visibility over detected frames
    minimum_valid_frame_ratio: float = 0.60
    readiness_visibility: float = 0.65
    readiness_hold_seconds: float = 1.5
    resample_hz: float = 30.0
    max_gap_seconds: float = 0.6              # longer gaps are never interpolated over


@dataclass(frozen=True)
class StsConfig:
    min_amplitude_deg: float = 25.0           # p95-p5 knee-angle swing to count as movement
    min_swing_fraction: float = 0.40          # reversal size, fraction of amplitude
    min_swing_deg: float = 15.0
    complete_fraction: float = 0.60           # each flank must reach this fraction of range
    upper_level: float = 0.80
    lower_level: float = 0.20
    min_rise_seconds: float = 0.15
    max_rise_seconds: float = 6.0
    smooth_seconds: float = 0.20
    min_valid_reps: int = 2
    min_duration_seconds: float = 5.0


@dataclass(frozen=True)
class GaitConfig:
    smooth_seconds: float = 0.12
    min_separation_range: float = 0.22        # ankle separation swing, torso lengths
    min_swing_fraction: float = 0.30
    min_swing_abs: float = 0.10
    min_step_seconds: float = 0.25
    max_step_seconds: float = 2.0
    min_steps: int = 6
    min_bout_seconds: float = 4.0
    travel_threshold: float = 0.6             # torso lengths of net travel => direction known


@dataclass(frozen=True)
class BalanceConfig:
    duration_seconds: float = 10.0
    settle_seconds: float = 1.0               # discarded while the participant settles
    smooth_seconds: float = 0.25
    min_analysed_seconds: float = 7.0
    max_displacement: float = 0.75            # torso lengths; larger => not standing still
    max_drift: float = 0.50


CAMERA = CameraConfig()
POSE = PoseConfig()
DISPLAY = DisplayConfig()
QUALITY = QualityConfig()
STS = StsConfig()
GAIT = GaitConfig()
BALANCE = BalanceConfig()
