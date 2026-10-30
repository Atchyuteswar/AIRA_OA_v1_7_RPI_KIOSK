# AIRA-OA v1.4

Camera-based, patient-linked movement screening (sit-to-stand, gait, balance + symptom profile) with
quality-aware fusion and longitudinal comparison.
**Non-diagnostic research prototype** - it produces movement features, never a diagnosis or OA probability.

## Quick start

Windows: double-click `run.bat`  |  macOS/Linux: `./run.sh`
(both create a virtual environment and install `requirements.txt` on first run)

Manual:
```bash
python -m venv .venv && . .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt                    # Python 3.9-3.12 (MediaPipe 0.10.21)
python app.py
```
Options: `--camera 1` (force index) · `--video clip.mp4` (analyse a recording) · `--data-dir D:\aira_data` · `--debug`

Camera problems: `python tools/camera_check.py`

## Setting up a recording
Camera 2-3 m away at about waist height, whole body **including feet** in frame, even lighting, plain background,
chair side-on or front-on. The readiness screen checks this and tells you what to fix.

Keys: ENTER continue/finish · ESC back · S skip test · R restart · P pause · D debug overlay · Q quit.
After every test a **review screen** shows the quality verdict and reasons; press R to repeat.

## Project layout
```
app.py                   entry point, assessment workflow
core/    config.py       every threshold in one place
         signals.py      resampling, spike removal, zero-phase smoothing, peak/valley detector
         pose.py         MediaPipe wrapper + pixel-space geometry (no MediaPipe import elsewhere)
         camera.py       threaded latest-frame capture with real timestamps, safe reconnect
         readiness.py    pre-test checklist and stable-hold gate
         quality.py      per-test gates and session roll-up
         fingerprint.py  quality-weighted modality fusion      personalization.py  baseline / change
         features.py     flat feature vector for export        flow.py hud.py display.py screens.py  UI
challenges/  sit_to_stand.py gait.py balance.py                (pure analyse() functions + recorder classes)
assessment/  session.py patients.py store.py report.py questionnaire.py
tests/  74 unit tests   tools/  e2e_smoke.py ui_smoke.py camera_check.py inspect_session.py
```
Data lives in `data/` **inside the project** (or `AIRA_DATA_DIR`): `patients/`, `sessions/`, `reports/`, `logs/`.

## Tests
```bash
pip install -r requirements-dev.txt && pytest -q          # algorithms + data layer
xvfb-run -a python tools/e2e_smoke.py                     # full flow, synthetic pose (Linux; on Windows just run it)
xvfb-run -a python tools/ui_smoke.py                      # Tk screens
```

## Upgrading from v1.3
Old sessions stay readable in History (shown as `legacy`) but are **not** used as baselines because the
features changed meaning (see `docs/ALGORITHMS.md`). Copy old `data/patients/*.json` to keep patient records.

## Limitations (please keep in your presentation)
Not clinically validated; single RGB camera gives 2-D/estimated-3-D proxies, not lab-grade kinematics;
thresholds in `core/config.py` were tuned on synthetic signals and must be checked against real recordings and a
reference system; the 33-point symptom index is custom, not WOMAC/KOOS.

## Raspberry Pi v1.4 deployment

See `README_RPI.md`. The Raspberry Pi edition uses the MediaPipe Tasks Pose
Landmarker backend and keeps the v1.4 movement-analysis and data contracts.
