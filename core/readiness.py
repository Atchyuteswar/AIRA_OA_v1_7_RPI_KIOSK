"""Pre-test readiness: person visible, body framed, lit and sharp, held stable.

Fixes over v1.3: framing/size checks are done in pixel space, the hold timer is
frame-count independent (seconds), the *same* gate object is used for the
on-screen checklist and the go/no-go decision (v1.3 evaluated two different
visibility thresholds), and the participant must be far enough from the
camera for the *whole* body (feet included) to be tracked for gait/STS.
"""
from __future__ import annotations

import cv2
import numpy as np

from core.config import QUALITY
from core.pose import BODY, REQUIRED, PoseFrame

MIN_HEIGHT = {"sit_to_stand": 0.40, "gait": 0.50, "balance": 0.22}
MARGIN = 0.02


def _bbox(pf: PoseFrame | None, challenge: str):
    if pf is None:
        return None
    pts = [(pf.lm[i, 0], pf.lm[i, 1]) for i in REQUIRED[challenge] if pf.lm[i, 3] >= 0.4]
    if len(pts) < 2:
        return None
    xs, ys = zip(*pts)
    return (max(0.0, min(xs)), max(0.0, min(ys)), min(1.0, max(xs)), min(1.0, max(ys)))


def lighting_score(gray: np.ndarray) -> float:
    m = float(gray.mean()) / 255.0
    return float(np.clip(1.0 - abs(m - 0.5) / 0.5, 0.0, 1.0))


def sharpness_score(gray: np.ndarray) -> float:
    small = cv2.resize(gray, (320, int(320 * gray.shape[0] / gray.shape[1])), interpolation=cv2.INTER_AREA)
    return float(np.clip(cv2.Laplacian(small, cv2.CV_64F).var() / 120.0, 0.0, 1.0))


def evaluate(pf: PoseFrame | None, challenge: str, frame: np.ndarray | None) -> dict:
    vis = pf.vis(REQUIRED[challenge]) if pf is not None else 0.0
    weakest = pf.min_vis(REQUIRED[challenge]) if pf is not None else 0.0
    box = _bbox(pf, challenge)
    framing_ok, height = False, 0.0
    if box:
        x1, y1, x2, y2 = box
        height = y2 - y1
        framing_ok = (x1 >= MARGIN and y1 >= MARGIN and x2 <= 1 - MARGIN and y2 <= 1 - MARGIN
                      and height >= MIN_HEIGHT[challenge])
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY) if frame is not None and frame.size else None
    light = lighting_score(gray) if gray is not None else 0.0
    sharp = sharpness_score(gray) if gray is not None else 0.0

    checks = {
        "person": pf is not None and vis >= 0.55,
        "landmarks": vis >= QUALITY.readiness_visibility and weakest >= 0.35,
        "framing": framing_ok,
        "lighting": light >= 0.30,
        "sharpness": sharp >= 0.10,
    }
    if not checks["person"]:
        msg = "Step into view so the whole body is visible."
    elif not checks["landmarks"]:
        msg = "Some joints are hidden - face the camera and remove obstructions."
    elif not checks["framing"]:
        if box and box[3] - box[1] < MIN_HEIGHT[challenge]:
            msg = "Move further from the camera."
        else:
            msg = "Move so your whole body is inside the frame."
    elif not checks["lighting"]:
        msg = "Improve the lighting on the participant."
    elif not checks["sharpness"]:
        msg = "Image looks blurry - steady the camera or improve focus."
    else:
        msg = "Hold still."
    return {"ok": all(checks.values()), "checks": checks, "visibility": vis, "lighting": light,
            "sharpness": sharp, "bbox": box, "message": msg}


class ReadinessGate:
    """Requires ``hold_seconds`` of uninterrupted good conditions."""

    def __init__(self, challenge: str, hold_seconds: float = QUALITY.readiness_hold_seconds):
        self.challenge = challenge
        self.hold = hold_seconds
        self.since: float | None = None
        self.status: dict = {}

    def update(self, pf, frame, t: float) -> dict:
        s = evaluate(pf, self.challenge, frame)
        if s["ok"]:
            if self.since is None:
                self.since = t
        else:
            self.since = None
        s["held"] = 0.0 if self.since is None else t - self.since
        s["ready"] = s["held"] >= self.hold
        s["hold_seconds"] = self.hold
        self.status = s
        return s
