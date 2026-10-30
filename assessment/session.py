"""Assessment lifecycle: collect blocks, fuse, compare, persist."""
from __future__ import annotations

import platform
import time
import uuid

from assessment.store import write_json_atomic
from core.features import unified_vector
from core.fingerprint import build_fingerprint
from core.paths import data_dir, sessions_dir
from core.personalization import compare, is_compatible, select_baseline, select_previous
from core.quality import overall_quality
from core.version import ALGORITHM_VERSION, SCHEMA_VERSION, __version__

TESTS = ("sit_to_stand", "gait", "balance")


class AssessmentSession:
    VERSION = __version__

    def __init__(self, camera_health=None, patient=None, history=None):
        """``history`` = every earlier session of this patient (any order)."""
        self.assessment_id = "AIRA-" + uuid.uuid4().hex[:8].upper()
        self.patient = patient or {}
        self.history = list(history or [])
        self.started_at = time.time()
        self.ended_at: float | None = None
        self.saved_path = None
        self.data: dict = {
            "prototype": "AIRA-OA",
            "version": self.VERSION,
            "algorithm_version": ALGORITHM_VERSION,
            "schema_version": SCHEMA_VERSION,
            "assessment_id": self.assessment_id,
            "patient_id": self.patient.get("patient_id"),
            "patient_snapshot": self.patient,
            "medical_diagnosis": False,
            "started_at_epoch": self.started_at,
            "environment": {"platform": platform.platform(), "python": platform.python_version()},
            "camera": camera_health or {},
            "sit_to_stand": {}, "gait": {}, "balance": {}, "questionnaire": {},
        }

    @property
    def id(self):
        return self.assessment_id

    def add_test(self, name: str, block: dict) -> None:
        self.data[name] = block

    def has(self, name: str) -> bool:
        return bool(self.data.get(name))

    def clear(self, name: str) -> None:
        self.data[name] = {}

    def finalize(self) -> dict:
        """Derive fingerprint/comparisons. Idempotent - safe to call repeatedly."""
        if self.ended_at is None:
            self.ended_at = time.time()
        d = self.data
        d["ended_at_epoch"] = self.ended_at
        d["duration_seconds"] = round(self.ended_at - self.started_at, 3)
        d["unified_feature_vector"] = unified_vector(d)
        fp = build_fingerprint(d)

        baseline = select_baseline(self.history)
        previous = select_previous(self.history)
        incompatible = sum(1 for s in self.history if not is_compatible(s))
        d["personalized_baseline"] = compare(baseline, fp, kind="baseline",
                                             incompatible_sessions=incompatible)
        d["longitudinal_comparison"] = compare(previous, fp, kind="previous",
                                               incompatible_sessions=incompatible)
        fp["personalization"] = {
            "baseline_status": d["personalized_baseline"]["status"],
            "baseline_assessment_id": d["personalized_baseline"]["baseline_assessment_id"],
        }
        d["movement_fingerprint"] = fp
        d["assessment_quality"] = overall_quality({n: d.get(n) or {} for n in TESTS})
        return d

    def save(self):
        payload = self.finalize()
        path = sessions_dir() / f"{self.assessment_id}.json"
        write_json_atomic(path, payload)
        write_json_atomic(data_dir() / "latest_assessment.json", payload)
        self.saved_path = path
        return path
