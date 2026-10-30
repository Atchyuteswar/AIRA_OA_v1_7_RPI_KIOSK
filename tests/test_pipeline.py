import os
import tempfile

import numpy as np
import pytest

from challenges.base import FrameStats
from core.pose import PoseFrame, angle_deg, knee_angle
from core.quality import overall_quality, skipped_block
from tests import synthetic as syn


@pytest.fixture()
def data_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("AIRA_DATA_DIR", str(tmp_path))
    return tmp_path


def _block(status="PASS", **kw):
    return {"status": "completed", "average_pose_quality": 0.9, "valid_frame_ratio": 0.9,
            "quality_gate": {"passed": status == "PASS", "status": status, "reasons": []}, **kw}


def _session(patient, history=None, blocks=None):
    from assessment.session import AssessmentSession
    s = AssessmentSession({}, patient=patient, history=history)
    for k, v in (blocks or {"sit_to_stand": _block(knee_rom_symmetry_ratio=0.9),
                            "gait": _block(left_right_step_balance=0.95, step_interval_cv=0.1,
                                           cadence_steps_per_minute=100, knee_rom_symmetry_ratio=.9),
                            "balance": _block(sway_rms=0.01)}).items():
        s.add_test(k, v)
    return s


# ---------------------------------------------------------------- geometry
def test_knee_angle_is_correct_on_non_square_images():
    lm = np.zeros((33, 4)); lm[:, 3] = 1
    lm[23, :2], lm[25, :2] = [0.5, 0.4], [0.5, 0.6]
    lm[27, :2] = [0.5 + 0.2 * 1080 / 1920, 0.6]
    assert knee_angle(PoseFrame(0, lm, 1920, 1080), "L", use_world=False) == pytest.approx(90.0, abs=0.01)
    assert angle_deg([0, 1, 0], [0, 0, 0], [1, 0, 0]) == pytest.approx(90)
    assert angle_deg([0, 0, 0], [0, 0, 0], [1, 0, 0]) is None


def test_frame_stats_do_not_double_count_missing_frames():
    fs = FrameStats()
    lm = np.zeros((33, 4)); lm[:, 3] = 0.9
    pf = PoseFrame(0, lm, 640, 480)
    for _ in range(8):
        fs.add(pf, (11, 12), 0.6)
    for _ in range(2):
        fs.add(None, (11, 12), 0.6)
    assert fs.valid_ratio == pytest.approx(0.8) and fs.pose_quality == pytest.approx(0.9)


# ----------------------------------------------------------------- quality
def test_overall_quality_rollup():
    p, r, sk = _block("PASS"), _block("REVIEW"), skipped_block("x")
    assert overall_quality({"a": p, "b": p, "c": p})["overall_status"] == "PASS"
    assert overall_quality({"a": p, "b": sk, "c": p})["overall_status"] == "PARTIAL"
    assert overall_quality({"a": p, "b": r, "c": p})["overall_status"] == "REVIEW"
    assert overall_quality({"a": sk, "b": sk, "c": sk})["overall_status"] == "REVIEW"


def test_empty_tests_never_pass_their_gate():
    from challenges.gait import Gait
    from challenges.sit_to_stand import SitToStand
    from challenges.balance import Balance
    for cls in (SitToStand, Gait, Balance):
        ch = cls(); ch.start(0.0)
        assert ch.finish(10.0)["quality_gate"]["passed"] is False


# ----------------------------------------------------- fingerprint / baseline
def test_fusion_excludes_failed_and_skipped_modalities(data_dir):
    s = _session({"patient_id": "PT-1"}, blocks={
        "sit_to_stand": _block(knee_rom_symmetry_ratio=0.9), "gait": _block("REVIEW"), "balance": skipped_block("b")})
    fp = s.finalize()["movement_fingerprint"]
    assert fp["modality_fusion"]["qualified_modalities"] == ["sit_to_stand"]
    assert set(fp["modality_fusion"]["excluded_modalities"]) == {"gait", "balance"}
    assert fp["quality"]["fusion_coverage"] == pytest.approx(fp["quality"]["sit_to_stand"] / 3, abs=1e-3)


def test_baseline_skips_unusable_first_session_and_metrics_of_missing_modalities(data_dir):
    bad = _session({"patient_id": "PT-1"}, blocks={k: _block("REVIEW") for k in ("sit_to_stand", "gait", "balance")})
    bad.finalize(); bad.data["started_at_epoch"] = 1
    good = _session({"patient_id": "PT-1"}, blocks={
        "sit_to_stand": _block(knee_rom_symmetry_ratio=0.9), "gait": skipped_block("g"), "balance": _block(sway_rms=0.01)})
    good.finalize(); good.data["started_at_epoch"] = 2
    cur = _session({"patient_id": "PT-1"}, history=[bad.data, good.data]).finalize()
    base = cur["personalized_baseline"]
    assert base["baseline_assessment_id"] == good.assessment_id      # not the unusable first one
    assert not any(k.startswith("gait") for k in base["changes"])    # skipped in baseline -> not compared
    assert any(k.startswith("gait") for k in base["skipped_metrics"])


def test_legacy_sessions_are_not_used_as_baseline(data_dir):
    legacy = {"assessment_id": "AIRA-OLD", "started_at_epoch": 1,
              "movement_fingerprint": {"modality_fusion": {"qualified_modalities": ["gait"]}}}
    cur = _session({"patient_id": "PT-1"}, history=[legacy]).finalize()
    assert cur["personalized_baseline"]["status"] == "BASELINE"
    assert "older algorithm" in cur["personalized_baseline"]["message"]


def test_percent_change_and_review_flag(data_dir):
    a = _session({"patient_id": "P"}); a.finalize(); a.data["started_at_epoch"] = 1
    b = _session({"patient_id": "P"}, history=[a.data], blocks={
        "sit_to_stand": _block(knee_rom_symmetry_ratio=0.6), "gait": _block(left_right_step_balance=.95, step_interval_cv=.1,
        cadence_steps_per_minute=100, knee_rom_symmetry_ratio=.9), "balance": _block(sway_rms=0.01)})
    ch = b.finalize()["personalized_baseline"]["changes"]["sts_symmetry"]
    assert ch["delta"] == pytest.approx(-0.3, abs=1e-3) and ch["exceeds_review_threshold"]


def test_finalize_is_idempotent(data_dir):
    s = _session({"patient_id": "P"})
    a = s.finalize()["duration_seconds"]
    assert s.finalize()["duration_seconds"] == a


# ------------------------------------------------------------- persistence
def test_atomic_save_roundtrip_and_numpy_types(data_dir):
    from assessment.store import read_json, write_json_atomic
    p = data_dir / "x.json"
    write_json_atomic(p, {"a": np.float64(1.5), "b": np.arange(3), "c": "José"})
    assert read_json(p) == {"a": 1.5, "b": [0, 1, 2], "c": "José"}
    assert not list(data_dir.glob("*.tmp"))


def test_corrupt_session_file_does_not_break_history(data_dir):
    from assessment.patients import list_sessions
    s = _session({"patient_id": "PT-9"}); s.save()
    (data_dir / "sessions" / "AIRA-BROKEN.json").write_text("{ truncated", encoding="utf-8")
    assert [x["assessment_id"] for x in list_sessions("PT-9")] == [s.assessment_id]


def test_patient_validation_and_unicode_names(data_dir):
    from assessment.patients import PatientValidationError, list_patients, save_patient
    p = save_patient({"name": "  José   Ramírez ", "age": "54", "consent": True})
    assert p["name"] == "José Ramírez"
    for bad in ({"name": "", "age": 30, "consent": True}, {"name": "A", "age": "x", "consent": True},
                {"name": "A", "age": 150, "consent": True}, {"name": "A", "age": 30, "consent": False}):
        with pytest.raises(PatientValidationError):
            save_patient(bad)
    ids = {save_patient({"name": "N", "age": 30, "consent": True})["patient_id"] for _ in range(5)}
    assert len(ids) == 5 and len(list_patients()) == 6


def test_report_and_csv_export(data_dir):
    from assessment.report import export_features_csv, export_report, render_html
    s = _session({"patient_id": "PT-1", "name": "<b>X</b>"}); d = s.finalize()
    assert "&lt;b&gt;X&lt;/b&gt;" in render_html(d)           # HTML-escaped
    assert export_report(d).exists() and export_features_csv([d]).read_text().count("\n") == 2


def test_detail_sections_handle_legacy_records():
    from core.screens import detail_sections
    secs = detail_sections({"assessment_id": "AIRA-OLD", "patient_snapshot": {"name": "A"}})
    assert secs[0][0] == "ASSESSMENT" and any("older algorithm" in str(v) for _, v in secs[0][1])
