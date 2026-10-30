from __future__ import annotations

import os
import time
from pathlib import Path

import cv2
import numpy as np

from core.pose import PoseFrame, PoseBackendError


MODEL_ENV = "AIRA_POSE_MODEL"

DEFAULT_MODEL = (
    Path(__file__).resolve().parent.parent
    / "models"
    / "movenet_lightning.tflite"
)


# MoveNet Lightning keypoint order:
#
# 0  nose
# 1  left_eye
# 2  right_eye
# 3  left_ear
# 4  right_ear
# 5  left_shoulder
# 6  right_shoulder
# 7  left_elbow
# 8  right_elbow
# 9  left_wrist
# 10 right_wrist
# 11 left_hip
# 12 right_hip
# 13 left_knee
# 14 right_knee
# 15 left_ankle
# 16 right_ankle
#
# AIRA-OA uses the MediaPipe-style 33 landmark indexing.


MOVENET_TO_MEDIAPIPE = {
    0: 0,    # nose

    1: 2,    # left eye
    2: 5,    # right eye
    3: 7,    # left ear
    4: 8,    # right ear

    5: 11,   # left shoulder
    6: 12,   # right shoulder

    7: 13,   # left elbow
    8: 14,   # right elbow

    9: 15,   # left wrist
    10: 16,  # right wrist

    11: 23,  # left hip
    12: 24,  # right hip

    13: 25,  # left knee
    14: 26,  # right knee

    15: 27,  # left ankle
    16: 28,  # right ankle
}


class PoseEstimator:
    """
    Raspberry Pi pose backend using MoveNet Lightning + TFLite Runtime.

    Produces the same PoseFrame abstraction used by the existing
    AIRA-OA STS / Gait / Balance algorithms.

    This backend deliberately does NOT import MediaPipe.
    """

    def __init__(
        self,
        model_path: str | None = None,
        min_detection: float = 0.25,
        min_tracking: float = 0.25,
        inference_width: int = 192,
    ):
        self.model_path = Path(
            model_path
            or os.environ.get(MODEL_ENV)
            or DEFAULT_MODEL
        )

        self.min_detection = float(min_detection)
        self.min_tracking = float(min_tracking)
        self.inference_width = int(inference_width)

        self._interpreter = None
        self._input_details = None
        self._output_details = None

        self._input_height = 192
        self._input_width = 192

        self._last_t = -1.0

    def __enter__(self):
        try:
            import tflite_runtime.interpreter as tflite
        except Exception as exc:
            raise PoseBackendError(
                f"TFLite Runtime unavailable: {exc}"
            ) from exc

        if not self.model_path.exists():
            raise PoseBackendError(
                f"MoveNet model not found: {self.model_path}"
            )

        try:
            self._interpreter = tflite.Interpreter(
                model_path=str(self.model_path)
            )

            self._interpreter.allocate_tensors()

            self._input_details = (
                self._interpreter.get_input_details()
            )

            self._output_details = (
                self._interpreter.get_output_details()
            )

            shape = self._input_details[0]["shape"]

            self._input_height = int(shape[1])
            self._input_width = int(shape[2])

            print(
                f"MoveNet Lightning loaded: "
                f"{self._input_width}x{self._input_height}"
            )

        except Exception as exc:
            raise PoseBackendError(
                f"Could not initialize MoveNet TFLite: {exc}"
            ) from exc

        return self

    def __exit__(self, *exc):
        self._interpreter = None
        self._input_details = None
        self._output_details = None

    def process(
        self,
        bgr: np.ndarray,
        t: float,
    ) -> PoseFrame | None:

        if self._interpreter is None:
            return None

        if bgr is None or bgr.size == 0:
            return None

        height, width = bgr.shape[:2]

        # Convert camera frame to RGB.
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)

        # MoveNet expects 192x192.
        resized = cv2.resize(
            rgb,
            (self._input_width, self._input_height),
            interpolation=cv2.INTER_AREA,
        )

        # Model is uint8.
        input_data = np.expand_dims(resized, axis=0)

        input_dtype = self._input_details[0]["dtype"]

        if input_data.dtype != input_dtype:
            input_data = input_data.astype(input_dtype)

        self._interpreter.set_tensor(
            self._input_details[0]["index"],
            input_data,
        )

        self._interpreter.invoke()

        output = self._interpreter.get_tensor(
            self._output_details[0]["index"]
        )

        # Expected:
        # [1, 1, 17, 3]
        #
        # Each landmark:
        # [y, x, confidence]

        keypoints = np.asarray(output)

        if keypoints.ndim == 4:
            keypoints = keypoints[0, 0]
        elif keypoints.ndim == 3:
            keypoints = keypoints[0]

        if keypoints.shape[0] != 17:
            raise PoseBackendError(
                f"Unexpected MoveNet output shape: {keypoints.shape}"
            )

        # Create MediaPipe-compatible 33x4 array.
        #
        # x, y are normalized 0..1.
        # z is unavailable from MoveNet Lightning.
        # visibility is represented using confidence.

        lm = np.zeros((33, 4), dtype=np.float32)

        for movenet_index, mediapipe_index in MOVENET_TO_MEDIAPIPE.items():

            y = float(keypoints[movenet_index, 0])
            x = float(keypoints[movenet_index, 1])
            confidence = float(keypoints[movenet_index, 2])

            lm[mediapipe_index] = [
                x,
                y,
                0.0,
                confidence,
            ]

        # Require enough confidence in the core body landmarks.
        core_indices = [
            11, 12,       # shoulders
            23, 24,       # hips
            25, 26,       # knees
            27, 28,       # ankles
        ]

        core_confidence = lm[core_indices, 3]

        if float(np.mean(core_confidence)) < self.min_detection:
            return None

        return PoseFrame(
            t=float(t),
            lm=lm,
            width=int(width),
            height=int(height),
            world=None,
        )
