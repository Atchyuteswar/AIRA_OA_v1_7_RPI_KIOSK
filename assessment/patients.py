"""Patient records and session history (local JSON)."""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime

from assessment.store import read_json, write_json_atomic
from core import log as _log
from core.paths import patients_dir, sessions_dir

_LOG = _log.get("patients")

SEX_CHOICES = ("Male", "Female", "Other", "Prefer not to say")
MAX_NAME = 80


class PatientValidationError(ValueError):
    """Raised with a message that is safe to show to the operator."""


def clean_text(value, limit: int = MAX_NAME) -> str:
    """Normalise free text but keep every script (v1.3 stripped all non-ASCII,
    turning names such as 'José' or Devanagari/Telugu names into fragments)."""
    text = unicodedata.normalize("NFC", str(value or ""))
    text = "".join(ch for ch in text if unicodedata.category(ch)[0] != "C")
    return re.sub(r"\s+", " ", text).strip()[:limit]


def _validate_age(age) -> int:
    try:
        n = int(str(age).strip())
    except (TypeError, ValueError):
        raise PatientValidationError("Enter age as a whole number.") from None
    if not 1 <= n <= 120:
        raise PatientValidationError("Age must be between 1 and 120.")
    return n


def _reserve_patient_id() -> str:
    """Allocate the next ID using exclusive file creation (no race, no reuse)."""
    root = patients_dir()
    numbers = []
    for path in root.glob("PT-*.json"):
        try:
            numbers.append(int(path.stem.split("-")[-1]))
        except ValueError:
            continue
    n = max(numbers, default=0) + 1
    while True:
        pid = f"PT-{datetime.now():%Y%m%d}-{n:03d}"
        try:
            with open(root / f"{pid}.json", "x", encoding="utf-8") as fh:
                fh.write("{}")
            return pid
        except FileExistsError:
            n += 1


def save_patient(profile: dict) -> dict:
    name = clean_text(profile.get("name"))
    if not name:
        raise PatientValidationError("Enter the participant name.")
    age = _validate_age(profile.get("age"))
    if not profile.get("consent"):
        raise PatientValidationError("Consent / screening-purpose confirmation is required.")
    patient_id = profile.get("patient_id") or _reserve_patient_id()
    now = datetime.now().isoformat(timespec="seconds")
    existing = read_json(patients_dir() / f"{patient_id}.json", {}) or {}
    payload = {
        "patient_id": patient_id,
        "name": name,
        "age": age,
        "sex": profile.get("sex") if profile.get("sex") in SEX_CHOICES else "Prefer not to say",
        "dominant_side": profile.get("dominant_side", "Unknown"),
        "contact": clean_text(profile.get("contact"), 120),
        "oa_history": profile.get("oa_history", "Unknown"),
        "symptomatic_area": profile.get("symptomatic_area", "Unknown"),
        "consent": True,
        "created_at": profile.get("created_at") or existing.get("created_at") or now,
        "updated_at": now,
    }
    write_json_atomic(patients_dir() / f"{patient_id}.json", payload)
    return payload


def load_patient(patient_id: str) -> dict | None:
    data = read_json(patients_dir() / f"{patient_id}.json")
    return data if data and data.get("patient_id") else None


def list_sessions(patient_id: str | None = None) -> list[dict]:
    """All readable sessions, newest first. Unreadable files are logged, not fatal."""
    items = []
    for path in sessions_dir().glob("AIRA-*.json"):
        item = read_json(path)
        if not isinstance(item, dict):
            continue
        rec_pid = item.get("patient_id") or (item.get("patient_snapshot") or {}).get("patient_id")
        if rec_pid and not item.get("patient_id"):
            item["patient_id"] = rec_pid
        if patient_id and rec_pid != patient_id:
            continue
        items.append(item)
    return sorted(items, key=lambda x: x.get("started_at_epoch", 0), reverse=True)


def list_patients() -> list[dict]:
    by_id: dict[str, dict] = {}
    for path in patients_dir().glob("PT-*.json"):
        item = read_json(path)
        if isinstance(item, dict) and item.get("patient_id"):
            by_id[item["patient_id"]] = item
    # recover patients whose profile file went missing from session snapshots
    for session in list_sessions():
        snap = session.get("patient_snapshot") or {}
        pid = session.get("patient_id") or snap.get("patient_id")
        if pid and pid not in by_id:
            rec = dict(snap)
            rec.setdefault("patient_id", pid)
            rec.setdefault("created_at", "")
            rec["updated_at"] = str(rec.get("updated_at") or "")
            by_id[pid] = rec
    return sorted(by_id.values(), key=lambda x: str(x.get("updated_at", "")), reverse=True)
