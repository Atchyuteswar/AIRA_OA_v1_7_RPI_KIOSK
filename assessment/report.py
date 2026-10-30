"""Self-contained HTML report + CSV export for one assessment."""
from __future__ import annotations

import csv
import datetime as dt
import html
from pathlib import Path

from core.paths import reports_dir
from core.version import DISCLAIMER, __version__


def _e(v) -> str:
    return html.escape(str(v))


def _fmt(v) -> str:
    if isinstance(v, bool):
        return "Yes" if v else "No"
    if isinstance(v, float):
        return f"{v:.4f}" if abs(v) < 1 else f"{v:.2f}"
    return _e(v)


def _table(rows, head=None) -> str:
    h = "".join(f"<th>{_e(c)}</th>" for c in head) if head else ""
    body = "".join("<tr>" + "".join(f"<td>{_fmt(c)}</td>" for c in r) + "</tr>" for r in rows)
    return f"<table>{('<tr>' + h + '</tr>') if h else ''}{body}</table>"


def render_html(d: dict) -> str:
    pat = d.get("patient_snapshot", {})
    q = d.get("assessment_quality", {})
    sts, gait, bal = d.get("sit_to_stand", {}), d.get("gait", {}), d.get("balance", {})
    qn = d.get("questionnaire", {})
    when = dt.datetime.fromtimestamp(d.get("started_at_epoch", 0)).strftime("%d %b %Y %H:%M") if d.get("started_at_epoch") else "-"

    def block(title, b, keys):
        gate = b.get("quality_gate", {})
        rows = [(label, b.get(k, "-")) for label, k in keys]
        note = "" if gate.get("passed") else f"<p class='warn'>{_e(gate.get('status', 'REVIEW'))}: {_e('; '.join(gate.get('reasons', [])))}</p>"
        return f"<h2>{_e(title)} <span class='tag'>{_e(gate.get('status', '-'))}</span></h2>{note}{_table(rows)}"

    sections = [
        block("Sit-to-Stand", sts, [("Valid repetitions", "valid_repetitions"), ("Invalid repetitions", "invalid_repetitions"),
              ("Left knee ROM (deg)", "left_knee_rom_deg"), ("Right knee ROM (deg)", "right_knee_rom_deg"),
              ("ROM symmetry", "knee_rom_symmetry_ratio"), ("Mean repetition time (s)", "average_rep_time_seconds"),
              ("Mean rise time (s)", "average_rise_time_seconds"), ("Mean descent time (s)", "average_descent_time_seconds"),
              ("Repetition-time CV", "rep_time_cv"), ("Peak trunk compensation (deg)", "peak_trunk_compensation_deg"),
              ("Smoothness (1 = single-peak)", "movement_smoothness"), ("5-repetition time (s)", "five_rep_time_seconds")]),
        block("Gait", gait, [("Steps", "total_steps"), ("Walking bout (s)", "walking_bout_seconds"),
              ("Cadence (steps/min)", "cadence_steps_per_minute"), ("Step-time symmetry", "left_right_step_balance"),
              ("Step-length symmetry (proxy)", "step_length_symmetry_proxy"), ("Step interval CV", "step_interval_cv"),
              ("Knee ROM symmetry", "knee_rom_symmetry_ratio"), ("Side labels reliable", "side_labels_reliable")]),
        block("Balance", bal, [("Analysed (s)", "analysed_seconds"), ("Sway RMS (torso lengths)", "sway_rms"),
              ("Sway path length", "sway_path_length"), ("Mean sway velocity", "sway_velocity"),
              ("95% ellipse area", "sway_ellipse_area_95"), ("Max displacement", "max_displacement"),
              ("Drift", "normalized_drift")]),
    ]
    base = d.get("personalized_baseline", {})
    ch = [(k, v["baseline"], v["current"], v["delta"], v["percent_change"], "REVIEW" if v.get("exceeds_review_threshold") else "")
          for k, v in base.get("changes", {}).items()]
    longi = (_table(ch, ["Metric", "Baseline", "Current", "Delta", "% change", "Flag"]) if ch else "") \
        or "<p>No comparison available yet.</p>"
    dom = [(v.get("label", k), f"{v.get('score', 0)} / {v.get('max_score', 0)}") for k, v in qn.get("domains", {}).items()]
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>AIRA-OA report {_e(d.get('assessment_id'))}</title>
<style>body{{font:14px/1.5 system-ui,Segoe UI,Arial;max-width:860px;margin:32px auto;color:#14202e;padding:0 16px}}
h1{{margin-bottom:0}}h2{{border-bottom:2px solid #e3e9f0;padding-bottom:4px;margin-top:28px}}
table{{border-collapse:collapse;width:100%}}td,th{{border-bottom:1px solid #eef2f6;padding:5px 8px;text-align:left}}
td:first-child{{color:#4a5b6c}}.tag{{font-size:12px;background:#e8f1ff;border-radius:8px;padding:2px 8px;margin-left:8px}}
.warn{{background:#fff4e0;padding:6px 10px;border-radius:6px}}.note{{color:#5b6b7b;font-size:12px;margin-top:28px}}</style></head><body>
<h1>AIRA-OA assessment report</h1><p>{_e(d.get('assessment_id'))} &middot; {when} &middot; app v{__version__} &middot; overall quality <b>{_e(q.get('overall_status', '-'))}</b></p>
<h2>Patient</h2>{_table([("Patient ID", pat.get('patient_id', '-')), ("Name", pat.get('name', '-')), ("Age", pat.get('age', '-')), ("Sex", pat.get('sex', '-')), ("Symptomatic area", pat.get('symptomatic_area', '-'))])}
{''.join(sections)}
<h2>Symptom profile (custom, non-validated)</h2>{_table([("Index", f"{qn.get('score', 0)} / {qn.get('max_score', 0)}")] + dom)}
<h2>Change versus baseline</h2><p>{_e(base.get('message', ''))}</p>{longi}
<p class="note">{_e(DISCLAIMER)}</p></body></html>"""


def export_report(d: dict) -> Path:
    path = reports_dir() / f"{d.get('assessment_id', 'assessment')}.html"
    path.write_text(render_html(d), encoding="utf-8")
    return path


def export_features_csv(sessions: list[dict], path: Path | None = None) -> Path:
    """One row per assessment with the unified feature vector (for analysis)."""
    path = Path(path) if path else reports_dir() / "features_all_assessments.csv"
    rows = []
    for s in sessions:
        vec = s.get("unified_feature_vector") or {}
        rows.append({"assessment_id": s.get("assessment_id"), "patient_id": s.get("patient_id"),
                     "started_at_epoch": s.get("started_at_epoch"),
                     "algorithm_version": s.get("algorithm_version", "legacy"),
                     "overall_quality": (s.get("assessment_quality") or {}).get("overall_status"), **vec})
    cols = list(dict.fromkeys(k for r in rows for k in r))
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)
    return path
