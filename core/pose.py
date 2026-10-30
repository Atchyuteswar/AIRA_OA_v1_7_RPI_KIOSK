"""Pose estimation wrapper and geometry helpers.

Design notes (fixes over v1.3)
------------------------------
* MediaPipe returns landmarks normalised to the *image* (x by width, y by
  height). Distances/angles computed directly on those numbers are distorted
  whenever the image is not square (v1.3 did this on 16:9 frames). Everything
  here is converted to **pixel space** first.
* Knee angles use MediaPipe's metric *world* landmarks when available; the
  image-plane fallback uses corrected pixel coordinates. v1.3 mixed normalised
  x/y with the unrelated-scale z coordinate.
* Pose is run on the un-mirrored frame. Mirroring is a display concern only.
* Downstream code sees a plain NumPy ``PoseFrame`` and never imports MediaPipe,
  so it can be unit-tested with synthetic data.
"""
from __future__ import annotations

import math
import os
import platform
from dataclasses import dataclass

import numpy as np

from core.config import POSE

# MediaPipe BlazePose landmark indices
NOSE = 0
L_SHOULDER, R_SHOULDER = 11, 12
L_HIP, R_HIP = 23, 24
L_KNEE, R_KNEE = 25, 26
L_ANKLE, R_ANKLE = 27, 28
L_HEEL, R_HEEL = 29, 30
L_FOOT, R_FOOT = 31, 32

TORSO = (L_SHOULDER, R_SHOULDER, L_HIP, R_HIP)
LEGS = (L_HIP, R_HIP, L_KNEE, R_KNEE, L_ANKLE, R_ANKLE)
BODY = TORSO + (L_KNEE, R_KNEE, L_ANKLE, R_ANKLE)

REQUIRED = {
    "sit_to_stand": BODY,
    "gait": BODY,
    "balance": TORSO,
}

SKELETON = (
    (11, 12), (11, 23), (12, 24), (23, 24),
    (23, 25), (25, 27), (24, 26), (26, 28),
    (27, 29), (29, 31), (28, 30), (30, 32),
    (11, 13), (13, 15), (12, 14), (14, 16),
)


@dataclass
class PoseFrame:
    """One pose observation. ``lm`` is (33, 4): x, y (0-1), z, visibility."""

    t: float
    lm: np.ndarray
    width: int
    height: int
    world: np.ndarray | None = None      # (33, 3) metres, hip-centred

    def px(self, index: int) -> np.ndarray:
        return np.array([self.lm[index, 0] * self.width, self.lm[index, 1] * self.height])

    def vis(self, indices) -> float:
        idx = list(indices)
        return float(np.mean(self.lm[idx, 3])) if idx else 0.0

    def min_vis(self, indices) -> float:
        idx = list(indices)
        return float(np.min(self.lm[idx, 3])) if idx else 0.0

    def mid_px(self, a: int, b: int) -> np.ndarray:
        return 0.5 * (self.px(a) + self.px(b))


# ---------------------------------------------------------------- geometry
def angle_deg(a, b, c) -> float | None:
    """Interior angle at ``b`` in degrees (180 = straight); None if degenerate."""
    a, b, c = (np.asarray(v, dtype=float) for v in (a, b, c))
    ba, bc = a - b, c - b
    denom = float(np.linalg.norm(ba) * np.linalg.norm(bc))
    if denom < 1e-9:
        return None
    cosine = float(np.clip(np.dot(ba, bc) / denom, -1.0, 1.0))
    return math.degrees(math.acos(cosine))


def knee_angle(pf: PoseFrame, side: str, use_world: bool | None = None) -> float | None:
    hip, knee, ankle = (L_HIP, L_KNEE, L_ANKLE) if side == "L" else (R_HIP, R_KNEE, R_ANKLE)
    if use_world is None:
        use_world = POSE.use_world_landmarks
    if use_world and pf.world is not None:
        return angle_deg(pf.world[hip], pf.world[knee], pf.world[ankle])
    return angle_deg(pf.px(hip), pf.px(knee), pf.px(ankle))


def torso_length_px(pf: PoseFrame) -> float:
    """Shoulder-midpoint to hip-midpoint distance in pixels (body scale)."""
    return float(np.linalg.norm(pf.mid_px(L_SHOULDER, R_SHOULDER) - pf.mid_px(L_HIP, R_HIP)))


def trunk_inclination_deg(pf: PoseFrame) -> float | None:
    """Trunk angle from vertical in the image plane (0 = upright), pixel space."""
    d = pf.mid_px(L_SHOULDER, R_SHOULDER) - pf.mid_px(L_HIP, R_HIP)
    if float(np.hypot(d[0], d[1])) < 1e-6:
        return None
    return abs(math.degrees(math.atan2(d[0], -d[1])))


# ------------------------------------------------------------- MediaPipe glue
class PoseBackendError(RuntimeError):
    pass


class PoseEstimator:
    """Context manager selecting the appropriate pose backend.

    Normal desktop environments keep the exact v1.4 ``mp.solutions.pose``
    backend. Raspberry Pi ARM64 deployments can opt into the MediaPipe Tasks
    Pose Landmarker backend with ``AIRA_POSE_BACKEND=tasks``.
    """

    def __init__(self, model_complexity: int = POSE.model_complexity, min_detection: float = 0.55,
                 min_tracking: float = 0.60, inference_width: int = 960):
        self._params = dict(model_complexity=model_complexity,
                            min_detection_confidence=min_detection,
                            min_tracking_confidence=min_tracking)
        self.inference_width = inference_width
        self._pose = None
        self._backend = None

    @staticmethod
    def _use_tasks_backend() -> bool:
        forced = os.environ.get("AIRA_POSE_BACKEND", "").strip().lower()
        if forced in {"movenet", "lite", "tflite", "rpi"}:
            return True
        if forced in {"tasks", "mediapipe_tasks"}:
            return False
        if forced in {"legacy", "solutions", "desktop"}:
            return False
        return platform.machine().lower() in {"aarch64", "arm64"} and os.environ.get("AIRA_RPI", "0") == "1"

    def __enter__(self) -> "PoseEstimator":
        if self._use_tasks_backend():
            from core.pose_movenet import MoveNetPoseEstimator
            self._backend = MoveNetPoseEstimator(
                model_path=os.environ.get("AIRA_POSE_MODEL"),
                input_size=int(os.environ.get("AIRA_MOVENET_INPUT", "192")),
                num_threads=int(os.environ.get("AIRA_MOVENET_THREADS", "2")),
                min_score=float(os.environ.get("AIRA_MOVENET_MIN_SCORE", "0.20")),
            )
            try:
                self._backend.__enter__()
            except Exception as exc:
                raise PoseBackendError(str(exc)) from exc
            return self

        try:
            import mediapipe as mp
            solutions = mp.solutions.pose
        except (ImportError, AttributeError) as exc:
            raise PoseBackendError(
                "MediaPipe's legacy 'solutions' API is not available. "
                "On Raspberry Pi use AIRA_POSE_BACKEND=tasks and run ./install_rpi.sh. "
                "On desktop install mediapipe==0.10.21 (Python 3.9-3.12)."
            ) from exc
        self._pose = solutions.Pose(static_image_mode=False, enable_segmentation=False,
                                    smooth_landmarks=True, **self._params)
        return self

    def __exit__(self, *exc):
        if self._backend is not None:
            self._backend.__exit__(*exc)
            self._backend = None
        if self._pose is not None:
            self._pose.close()
            self._pose = None

    def process(self, bgr: np.ndarray, t: float) -> PoseFrame | None:
        if self._backend is not None:
            return self._backend.process(bgr, t)
        import cv2
        h, w = bgr.shape[:2]
        small = bgr
        if w > self.inference_width:
            scale = self.inference_width / float(w)
            small = cv2.resize(bgr, (self.inference_width, max(1, int(h * scale))),
                               interpolation=cv2.INTER_AREA)
        rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
        rgb.flags.writeable = False
        result = self._pose.process(rgb)
        if not result.pose_landmarks:
            return None
        return pose_frame_from_result(result, t, w, h)


def pose_frame_from_result(result, t: float, width: int, height: int) -> PoseFrame:
    lm = np.array([[p.x, p.y, p.z, p.visibility] for p in result.pose_landmarks.landmark],
                  dtype=float)
    world = None
    wl = getattr(result, "pose_world_landmarks", None)
    if wl is not None:
        world = np.array([[p.x, p.y, p.z] for p in wl.landmark], dtype=float)
    return PoseFrame(t=t, lm=lm, width=width, height=height, world=world)
