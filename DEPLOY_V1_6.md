# AIRA-OA v1.6 Raspberry Pi deployment

AIRA-OA v1.6 keeps the v1.4 analysis semantics and the working v1.5 Raspberry Pi camera/MoveNet layer, while refining the kiosk workflow and assessment recovery.

## Changes in this release

- Camera & System is now a system-readiness dashboard rather than a duplicate of Camera Diagnostics.
- Quick Status reports patient/assessment workflow state rather than camera telemetry.
- Patient History is a touch-first patient hub with patient profile, assessment timeline, quality summary, details and direct Start Assessment.
- Transient MoveNet/TFLite pose inference failures are retried before stopping an assessment.
- Assessment recovery now displays the technical exception and local log path.
- A Tk global Return-binding leak in patient registration is cleaned up when the screen closes.
- 1280×720 MJPEG @ 30 FPS camera negotiation and MoveNet Lightning remain unchanged.

## Safe update on the existing Pi

Do not copy `.venv` or overwrite `data/`. The updater creates a timestamped application backup and intentionally preserves patient/session data.

```bash
cd ~/aira-oa/AIRA_OA_v1_6_RPI_KIOSK
chmod +x update_existing_rpi.sh
./update_existing_rpi.sh ~/aira-oa/aira-oa-kiosk

cd ~/aira-oa/aira-oa-kiosk
source .venv/bin/activate
./start_rpi.sh
```

## Verification checklist

1. Home shows **CAMERA READY — 1280×720 • 30 FPS**.
2. **Camera & System** shows system readiness, pose engine and storage.
3. **Quick Status** shows patient/assessment state, not duplicate camera diagnostics.
4. **Patient History** opens patient profile and assessment timeline.
5. Selecting **Start Assessment** launches the workflow for that patient.
6. Run the assessment through STS, gait, balance and questionnaire.
7. If a pose/TFLite failure occurs, the recovery dialog now exposes the technical error.
8. Open assessment details and export a report from History.

## Data compatibility

- Analysis algorithm: `1.4`
- Stored schema: `1.4.0`
- Application/UI release: `1.6.0`

Existing patient/session JSON files remain compatible and are not migrated by this UI release.
