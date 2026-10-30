"""Quality gates.

A gate answers one question: *is this modality trustworthy enough to be fused
into the fingerprint?* v1.3 only checked pose visibility and frame coverage,
so a test in which the participant never moved (0 repetitions / 0 steps)
"passed" and could even become the patient's baseline. v1.4 also requires
enough *evidence* (events, duration) and makes the reasons explicit.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from core.config import QUALITY

PASS = "PASS"
REVIEW = "REVIEW"
SKIPPED = "SKIPPED"


@dataclass
class GateBuilder:
    valid_frame_ratio: float
    average_pose_quality: float
    reasons: list[str] = field(default_factory=list)

    def require(self, ok: bool, reason: str) -> "GateBuilder":
        if not ok:
            self.reasons.append(reason)
        return self

    def build(self) -> dict:
        passed = not self.reasons
        return {
            "passed": passed,
            "status": PASS if passed else REVIEW,
            "valid_frame_ratio": round(float(self.valid_frame_ratio), 4),
            "average_pose_quality": round(float(self.average_pose_quality), 4),
            "reasons": list(self.reasons),
        }


def base_gate(valid_ratio: float, pose_quality: float) -> GateBuilder:
    g = GateBuilder(valid_ratio, pose_quality)
    g.require(valid_ratio >= QUALITY.minimum_valid_frame_ratio,
              f"valid frames {valid_ratio:.0%} below {QUALITY.minimum_valid_frame_ratio:.0%}")
    g.require(pose_quality >= QUALITY.minimum_pose_quality,
              f"pose confidence {pose_quality:.0%} below {QUALITY.minimum_pose_quality:.0%}")
    return g


def skipped_block(key: str, reason: str = "participant_skipped") -> dict:
    return {
        "status": "skipped",
        "reason": reason,
        "quality_gate": {"passed": False, "status": SKIPPED, "reasons": [reason],
                         "valid_frame_ratio": 0.0, "average_pose_quality": 0.0},
    }


def failed_block(reason: str) -> dict:
    """A block for a test that produced no usable recording at all."""
    return {
        "status": "completed",
        "quality_gate": {"passed": False, "status": REVIEW, "reasons": [reason],
                         "valid_frame_ratio": 0.0, "average_pose_quality": 0.0},
    }


def overall_quality(blocks: dict[str, dict]) -> dict:
    """Roll the per-test gates into one session-level status.

    PASS     - every test completed and passed
    PARTIAL  - some tests were skipped by the operator, the rest passed
    REVIEW   - at least one completed test failed its gate
    """
    by_test, statuses = {}, []
    for name, block in blocks.items():
        gate = (block or {}).get("quality_gate") or {
            "passed": False, "status": REVIEW, "reasons": ["test not completed"]}
        by_test[name] = gate
        statuses.append(gate.get("status", REVIEW))
    passed = sum(s == PASS for s in statuses)
    skipped = sum(s == SKIPPED for s in statuses)
    if any(s == REVIEW for s in statuses):
        overall = REVIEW
    elif passed == 0:
        overall = REVIEW
    elif skipped:
        overall = "PARTIAL"
    else:
        overall = PASS
    return {
        "overall_status": overall,
        "tests_passed": passed,
        "tests_skipped": skipped,
        "tests_evaluated": len(statuses),
        "by_test": by_test,
    }
