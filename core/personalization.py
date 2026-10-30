"""Patient-specific baseline and longitudinal comparison.

Fixes over v1.3
* the baseline was taken from the *earliest session regardless of quality*; if
  that session was unusable, no later session could ever become the baseline;
* metrics from a modality that was skipped/failed in either session were
  compared as if they were real (a skipped balance test looked like a -100 %
  change);
* sessions recorded with a different algorithm version are not comparable.
"""
from __future__ import annotations

from typing import Iterable

from core.version import ALGORITHM_VERSION

VERSION = "1.4"
NOTABLE_PERCENT = 20.0        # heuristic review threshold - NOT a validated MDC

# metric -> (path inside the fingerprint, modality that must be qualified)
METRICS: dict[str, tuple[tuple[str, ...], str]] = {
    "sts_symmetry": (("symmetry", "sts"), "sit_to_stand"),
    "sts_smoothness": (("challenge_response", "sit_to_stand", "movement_smoothness"), "sit_to_stand"),
    "sts_rom_difference_deg": (("challenge_response", "sit_to_stand", "knee_rom_difference_deg"), "sit_to_stand"),
    "sts_rep_time_seconds": (("challenge_response", "sit_to_stand", "rep_time_seconds"), "sit_to_stand"),
    "gait_step_balance": (("symmetry", "gait"), "gait"),
    "gait_regularity": (("challenge_response", "gait", "step_regularness"), "gait"),
    "gait_cadence": (("challenge_response", "gait", "cadence_steps_per_minute"), "gait"),
    "gait_knee_symmetry": (("challenge_response", "gait", "knee_rom_symmetry"), "gait"),
    "balance_sway_rms": (("challenge_response", "balance", "sway_rms"), "balance"),
    "balance_max_displacement": (("challenge_response", "balance", "max_displacement"), "balance"),
    "balance_sway_velocity": (("challenge_response", "balance", "sway_velocity"), "balance"),
}


def _get(data, path, default=None):
    try:
        for key in path:
            data = data[key]
        return data
    except (KeyError, TypeError):
        return default


def qualified_modalities(fingerprint: dict | None) -> list[str]:
    return list(_get(fingerprint or {}, ("modality_fusion", "qualified_modalities"), []) or [])


def is_compatible(session: dict) -> bool:
    return session.get("algorithm_version") == ALGORITHM_VERSION


def usable(session: dict) -> bool:
    return bool(session.get("movement_fingerprint")) and is_compatible(session) \
        and bool(qualified_modalities(session["movement_fingerprint"]))


def snapshot(session: dict) -> dict:
    fp = session.get("movement_fingerprint", {})
    features = {}
    for name, (path, _) in METRICS.items():
        v = _get(fp, path)
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            features[name] = float(v)
    return {"assessment_id": session.get("assessment_id"),
            "started_at_epoch": session.get("started_at_epoch"),
            "algorithm_version": session.get("algorithm_version"),
            "qualified_modalities": qualified_modalities(fp), "features": features}


def select_baseline(sessions: Iterable[dict]) -> dict | None:
    """Earliest *usable* (compatible, ≥1 qualified modality) session."""
    candidates = sorted((s for s in sessions if usable(s)), key=lambda s: s.get("started_at_epoch", 0))
    return snapshot(candidates[0]) if candidates else None


def select_previous(sessions: Iterable[dict]) -> dict | None:
    candidates = sorted((s for s in sessions if usable(s)), key=lambda s: s.get("started_at_epoch", 0))
    return snapshot(candidates[-1]) if candidates else None


def compare(reference: dict | None, current_fp: dict, *, kind: str, incompatible_sessions: int = 0) -> dict:
    """Compare ``current_fp`` with a reference snapshot (baseline or previous)."""
    label = "baseline" if kind == "baseline" else "previous"
    if not reference:
        msg = ("This assessment establishes the patient's first usable movement baseline."
               if not incompatible_sessions else
               f"{incompatible_sessions} earlier assessment(s) used an older algorithm version and are "
               "not comparable; this assessment starts a new baseline.")
        return {"status": "BASELINE", "message": msg, "baseline_assessment_id": None,
                "reference_assessment_id": None, "changes": {}, "skipped_metrics": {}}

    cur_mods = set(qualified_modalities(current_fp))
    ref_mods = set(reference.get("qualified_modalities", []))
    changes, skipped = {}, {}
    for name, (path, modality) in METRICS.items():
        cur = _get(current_fp, path)
        ref = reference.get("features", {}).get(name)
        if modality not in cur_mods or modality not in ref_mods:
            skipped[name] = f"{modality} not qualified in both assessments"
            continue
        if not isinstance(cur, (int, float)) or not isinstance(ref, (int, float)):
            continue
        delta = float(cur) - float(ref)
        pct = None if abs(ref) < 1e-9 else delta / abs(ref) * 100.0
        changes[name] = {
            "baseline": round(float(ref), 6), "current": round(float(cur), 6),
            "delta": round(delta, 6),
            "percent_change": None if pct is None else round(pct, 3),
            "direction": "higher" if delta > 0 else "lower" if delta < 0 else "unchanged",
            "exceeds_review_threshold": bool(pct is not None and abs(pct) >= NOTABLE_PERCENT),
        }
    status = "COMPARED" if changes else "NO_COMPARABLE_METRICS"
    message = (f"Observed feature changes relative to the patient's {label} assessment. "
               f"Changes of {NOTABLE_PERCENT:.0f}% or more are flagged for review using a heuristic "
               "threshold only; interpretation is non-diagnostic.") if changes else \
        "No modality was qualified in both assessments, so nothing could be compared."
    return {"status": status, "message": message,
            "baseline_assessment_id": reference.get("assessment_id"),
            "reference_assessment_id": reference.get("assessment_id"),
            "changes": changes, "skipped_metrics": skipped}
