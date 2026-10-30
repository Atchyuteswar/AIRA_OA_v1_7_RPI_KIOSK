from __future__ import annotations

import time
from pathlib import Path

import cv2
import numpy as np

from core.config import POSE
from core.pose import PoseFrame, PoseBackendError, pose_frame_from_result

MODEL_ENV = "AIRA_POSE_MODEL"
DEFAULT_MODEL = Path(__file__).resolve().parent.parent / "models" / "pose_landmarker_lite.task"

class PoseEstimator:
    """MediaPipe Tasks Pose Landmarker backend for Raspberry Pi.

    It converts the Tasks API result into the same PoseFrame used by the
    existing AIRA-OA algorithms, so STS/Gait/Balance remain unchanged.
    """
    def __init__(self, model_path: str | None = None, min_detection: float = 0.55,
                 min_tracking: float = 0.60, inference_width: int = 640):
        self.model_path = Path(model_path or __import__('os').environ.get(MODEL_ENV, DEFAULT_MODEL))
        self.min_detection = min_detection
        self.min_tracking = min_tracking
        self.inference_width = inference_width
        self._landmarker = None
        self._last_ts_ms = -1

    def __enter__(self):
        try:
            from mediapipe.tasks import python
            from mediapipe.tasks.python import vision
        except Exception as exc:
            raise PoseBackendError(f"MediaPipe Tasks API unavailable: {exc}") from exc
        if not self.model_path.exists():
            raise PoseBackendError(
                f"Pose model not found: {self.model_path}. Run ./install_rpi.sh to download it.")
        try:
            base = python.BaseOptions(model_asset_path=str(self.model_path))
            opts = vision.PoseLandmarkerOptions(
                base_options=base,
                running_mode=vision.RunningMode.VIDEO,
                num_poses=1,
                min_pose_detection_confidence=self.min_detection,
                min_pose_presence_confidence=self.min_detection,
                min_tracking_confidence=self.min_tracking,
                output_segmentation_masks=False,
            )
            self._landmarker = vision.PoseLandmarker.create_from_options(opts)
        except Exception as exc:
            raise PoseBackendError(f"Could not create MediaPipe Pose Landmarker: {exc}") from exc
        return self

    def __exit__(self, *exc):
        if self._landmarker is not None:
            self._landmarker.close()
            self._landmarker = None

    def process(self, bgr: np.ndarray, t: float) -> PoseFrame | None:
        if self._landmarker is None:
            return None
        h, w = bgr.shape[:2]
        small = bgr
        if w > self.inference_width:
            scale = self.inference_width / float(w)
            small = cv2.resize(bgr, (self.inference_width, max(1, int(h * scale))), interpolation=cv2.INTER_AREA)
        rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
        import mediapipe as mp
        image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        ts = max(self._last_ts_ms + 1, int(t * 1000))
        self._last_ts_ms = ts
        result = self._landmarker.detect_for_video(image, ts)
        if not result.pose_landmarks:
            return None
        pts = result.pose_landmarks[0]
        lm = np.array([[p.x, p.y, p.z, float(getattr(p, 'visibility', getattr(p, 'presence', 1.0)))] for p in pts], dtype=float)
        world = None
        if getattr(result, 'pose_world_landmarks', None):
            world_pts = result.pose_world_landmarks[0]
            world = np.array([[p.x, p.y, p.z] for p in world_pts], dtype=float)
        return PoseFrame(t=t, lm=lm, width=w, height=h, world=world)
