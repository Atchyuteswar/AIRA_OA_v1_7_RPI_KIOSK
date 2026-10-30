# AIRA-OA v1.6 — Raspberry Pi Touch Kiosk

## Hardware target

- Raspberry Pi 4, 64-bit Linux
- 7-inch touchscreen
- **1024x600 landscape native display resolution**
- USB RGB webcam
- No keyboard or mouse required during normal operation

## Touch-first changes

Every operator-facing path is designed for touch:

- home, patient registration and patient selection
- on-screen QWERTY/numeric keyboard
- visible Back/Home/Continue/Cancel actions
- camera readiness, countdown, recording, repeat/skip/accept
- questionnaire answer buttons plus Back/Home
- results, details, export and New Assessment
- history patient/assessment paging
- touch paging in long report/raw JSON views
- touch dialogs instead of native message boxes

The physical keyboard remains useful only for maintenance/debugging.

## Raspberry Pi pose backend

The Pi build defaults to **MoveNet SinglePose Lightning + TFLite**. This avoids
the ARM native dependency that caused the MediaPipe Tasks backend to terminate
with `Illegal instruction` on the Pi 4.

The downstream AIRA-OA algorithms still receive the same `PoseFrame` interface,
so STS, gait, balance, quality, fingerprinting, personalization and local JSON
persistence remain in the v1.4 architecture.

## Install

```bash
chmod +x install_rpi.sh start_rpi.sh
./install_rpi.sh
./start_rpi.sh
```

If the model could not be downloaded automatically, place
`movenet_lightning.tflite` in `models/` and start again.

## Display

The Pi UI is rendered at 1024x600 and launched fullscreen. Set:

```text
AIRA_RPI=1
AIRA_RPI_TOUCH=1
AIRA_RPI_FULLSCREEN=1
AIRA_POSE_BACKEND=movenet
```

## Data

Patient and assessment records remain local under `data/`. Do not overwrite the
existing `data/patients/` or `data/sessions/` folders when updating the code if
they already contain research records.
