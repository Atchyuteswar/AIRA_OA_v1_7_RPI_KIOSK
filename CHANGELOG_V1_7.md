# AIRA-OA v1.7.0 — Raspberry Pi Kiosk UI & Assessment Reliability

## Fixed
- Fixed the assessment-screen OpenCV crash caused by an invalid `cv2.circle()` center argument in the live HUD header.
- Made pose landmark circle rendering explicitly integer-safe for Raspberry Pi OpenCV builds.
- Kept MoveNet Lightning as the Raspberry Pi pose backend; no MediaPipe Tasks native dependency is required.

## Patient History
- Reworked Patient History into a clearer touch-first profile workspace.
- Added patient count/search row, selected-patient highlighting and compact profile metrics.
- Improved assessment timeline readability with status, test counts and Details actions.
- Added clearer empty-state messaging and touch-sized pagination controls.
- Kept Start Assessment and CSV export directly inside the selected patient workspace.

## Touch keyboard
- Enlarged and regularised the on-screen keyboard layout for 1024x600.
- Added a centred numeric keypad layout instead of leaving a large empty numeric row.
- Improved backspace/clear focus behaviour.
- Last patient-registration field now uses NEXT to trigger Save & Continue.
- Improved combobox styling to match the kiosk dark UI.

## Compatibility
- Analysis algorithm remains ALGORITHM_VERSION 1.4.
- Stored schema remains 1.4.0.
