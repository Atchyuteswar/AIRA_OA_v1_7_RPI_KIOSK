"""Raspberry Pi MoveNet SinglePose Lightning backend.

MoveNet Lightning is used on the Pi because it is lightweight and avoids the
ARM crypto/AES dependency that made the MediaPipe Tasks native binary crash on
Raspberry Pi 4.  The backend converts MoveNet's 17 COCO keypoints into the
33-landmark PoseFrame contract consumed by the existing AIRA-OA algorithms.
"""
from __future__ import annotations

import os
from pathlib import Path

import numpy as np

from core.pose import PoseFrame


class MoveNetBackendError(RuntimeError):
    pass


# MoveNet SinglePose COCO order -> BlazePose-compatible indices used by AIRA-OA.
# AIRA-OA only requires nose, shoulders, hips, knees and ankles for the current
# STS/gait/balance algorithms; unsupported BlazePose points remain zero.
_MOVENET_TO_BLAZE = {
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


class MoveNetPoseEstimator:
    """Single-person MoveNet Lightning inference using TFLite/LiteRT."""

    def __init__(self, model_path: str | None = None, input_size: int = 192,
                 num_threads: int = 2, min_score: float = 0.20):
        root = Path(__file__).resolve().parent.parent
        self.model_path = Path(model_path or os.environ.get(
            "AIRA_POSE_MODEL", root / "models" / "movenet_lightning.tflite"
        )).expanduser().resolve()
        self.input_size = int(input_size)
        self.num_threads = int(num_threads)
        self.min_score = float(min_score)
        self._interpreter = None
        self._input = None
        self._output = None
        self._input_dtype = None
        self._output_dtype = None

    @staticmethod
    def _load_interpreter():
        try:
            from tflite_runtime.interpreter import Interpreter
            return Interpreter
        except ImportError:
            try:
                from tensorflow.lite.python.interpreter import Interpreter
                return Interpreter
            except ImportError as exc:
                raise MoveNetBackendError(
                    "TensorFlow Lite runtime is not installed. Run ./install_rpi.sh "
                    "or install tflite-runtime for the Pi Python environment."
                ) from exc

    def __enter__(self):
        if not self.model_path.exists():
            raise MoveNetBackendError(
                f"MoveNet model not found: {self.model_path}\n\n"
                "Place movenet_lightning.tflite in models/ or set AIRA_POSE_MODEL."
            )
        Interpreter = self._load_interpreter()
        try:
            self._interpreter = Interpreter(
                model_path=str(self.model_path),
                num_threads=max(1, self.num_threads),
            )
            self._interpreter.allocate_tensors()
            inputs = self._interpreter.get_input_details()
            outputs = self._interpreter.get_output_details()
            if not inputs or not outputs:
                raise RuntimeError("MoveNet model exposes no input/output tensors")
            self._input = inputs[0]
            self._output = outputs[0]
            shape = tuple(int(x) for x in self._input["shape"])
            if len(shape) != 4 or shape[1] != self.input_size or shape[2] != self.input_size:
                raise RuntimeError(f"Expected {self.input_size}x{self.input_size} input, got {shape}")
            self._input_dtype = self._input["dtype"]
            self._output_dtype = self._output["dtype"]
            print(f"MoveNet Lightning loaded: {self.input_size}x{self.input_size}", flush=True)
        except Exception as exc:
            self._interpreter = None
            raise MoveNetBackendError(f"Could not initialize MoveNet: {exc}") from exc
        return self

    def __exit__(self, *exc):
        self._interpreter = None
        self._input = None
        self._output = None

    def _prepare(self, bgr: np.ndarray):
        import cv2
        h, w = bgr.shape[:2]
        scale = min(self.input_size / float(w), self.input_size / float(h))
        rw, rh = max(1, int(round(w * scale))), max(1, int(round(h * scale)))
        resized = cv2.resize(bgr, (rw, rh), interpolation=cv2.INTER_AREA)
        canvas = np.zeros((self.input_size, self.input_size, 3), dtype=np.uint8)
        ox = (self.input_size - rw) // 2
        oy = (self.input_size - rh) // 2
        canvas[oy:oy + rh, ox:ox + rw] = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        return canvas, scale, ox, oy, w, h

    def _input_tensor(self, rgb: np.ndarray) -> np.ndarray:
        x = rgb[None, ...]
        if self._input_dtype == np.float32:
            return (x.astype(np.float32) / 127.5) - 1.0
        if self._input_dtype == np.int8:
            scale, zero = self._input.get("quantization", (0.0, 0))
            if scale:
                return np.clip(np.round((x.astype(np.float32) / 255.0) / scale + zero), -128, 127).astype(np.int8)
        return x.astype(self._input_dtype)

    def _output_array(self) -> np.ndarray:
        out = self._interpreter.get_tensor(self._output["index"])
        if np.issubdtype(out.dtype, np.integer):
            scale, zero = self._output.get("quantization", (0.0, 0))
            if scale:
                out = (out.astype(np.float32) - zero) * scale
        return np.asarray(out, dtype=np.float32)

    def process(self, bgr: np.ndarray, t: float) -> PoseFrame | None:
        if self._interpreter is None:
            raise MoveNetBackendError("MoveNet estimator is not initialized")
        rgb, scale, ox, oy, w, h = self._prepare(bgr)
        self._interpreter.set_tensor(self._input["index"], self._input_tensor(rgb))
        self._interpreter.invoke()
        out = self._output_array()
        # Standard MoveNet SinglePose output: [1, 1, 17, 3], (y, x, score).
        keypoints = out.reshape(-1, 3)[:17]
        lm = np.zeros((33, 4), dtype=float)
        for idx, (y, x, score) in enumerate(keypoints):
            blaze = _MOVENET_TO_BLAZE[idx]
            # Undo letterboxing, then normalize against the original frame.
            px = (float(x) * self.input_size - ox) / max(scale, 1e-9)
            py = (float(y) * self.input_size - oy) / max(scale, 1e-9)
            nx = float(np.clip(px / max(w, 1), 0.0, 1.0))
            ny = float(np.clip(py / max(h, 1), 0.0, 1.0))
            vis = float(np.clip(score, 0.0, 1.0))
            lm[blaze] = (nx, ny, 0.0, vis)
        # MoveNet does not provide BlazePose metric world landmarks.
        return PoseFrame(t=t, lm=lm, width=w, height=h, world=None)
