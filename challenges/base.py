"""Common recording machinery for the three movement challenges."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from core.config import QUALITY
from core.pose import PoseFrame


@dataclass
class FrameStats:
    """Frame-level bookkeeping shared by every challenge."""

    total: int = 0            # frames offered while recording
    detected: int = 0         # frames with a person
    valid: int = 0            # frames whose required landmarks are visible enough
    vis_sum: float = 0.0      # visibility summed over detected frames

    def add(self, pf: PoseFrame | None, required, vis_threshold: float) -> bool:
        """Register a frame; returns True when it is usable for analysis."""
        self.total += 1
        if pf is None:
            return False
        self.detected += 1
        q = pf.vis(required)
        self.vis_sum += q
        if q < vis_threshold or pf.min_vis(required) < 0.25:
            return False
        self.valid += 1
        return True

    @property
    def valid_ratio(self) -> float:
        return self.valid / self.total if self.total else 0.0

    @property
    def pose_quality(self) -> float:
        # Mean visibility over frames where a person was found. Missing frames
        # are already penalised through ``valid_ratio``; counting them twice
        # (v1.3) made the two gates fail together.
        return self.vis_sum / self.detected if self.detected else 0.0


class Challenge:
    """Interface used by the workflow runner."""

    key = "challenge"
    title = "Challenge"
    ENGINE_VERSION = "1.4"
    instructions: tuple[str, ...] = ()
    auto_finish = False

    def start(self, t: float) -> None:
        raise NotImplementedError

    def update(self, pf: PoseFrame | None, t: float) -> None:
        raise NotImplementedError

    def live(self) -> dict:
        """Cheap-to-render live values for the HUD (cards + status text)."""
        raise NotImplementedError

    def finish(self, t: float) -> dict:
        raise NotImplementedError

    def is_complete(self, t: float) -> bool:
        return False

    def progress(self, t: float) -> float | None:
        return None


def as_array(rows: list[list[float]], cols: int) -> np.ndarray:
    return np.asarray(rows, dtype=float).reshape(-1, cols) if rows else np.zeros((0, cols))
