# AIRA-OA v1.6.0 — Raspberry Pi Kiosk Refinement

## UI and workflow
- Separated Camera & System from Quick Status.
- Camera & System now reports capture readiness, pose engine, Pi runtime and storage; raw camera telemetry remains in Camera Diagnostics.
- Quick Status now reports patient/assessment workflow state instead of repeating camera metrics.
- Reworked Patient History into a touch-first patient hub with patient profile, assessment timeline, quality summary, details and Start Assessment.
- History can launch a new assessment directly for the selected patient.

## Assessment reliability
- Runtime pose inference now has bounded retry handling for transient native/TFLite failures.
- Assessment recovery dialogs now show the exception class/message and local log path instead of hiding the technical cause.
- Partial-session preservation remains enabled.

## Compatibility
- Analysis algorithm remains ALGORITHM_VERSION 1.4.
- Stored schema remains 1.4.0.
- MoveNet Lightning and the 1280x720 @ 30 FPS Raspberry Pi camera profile are preserved.
