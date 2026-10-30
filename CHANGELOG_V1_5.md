# AIRA-OA v1.5.0 — Kiosk Experience Release

## What changed

### Camera reliability
- Preserves the working Raspberry Pi USB webcam profile: 1280×720, MJPEG, 30 FPS.
- `start_rpi.sh` pre-negotiates the V4L2 format/FPS before Python starts.
- OpenCV keeps the same MJPEG profile and performs a second FPS request after resolution negotiation.
- Camera health now reports target profile and whether the negotiated profile is acceptable.
- Stale frames are discarded when a live camera is declared lost.
- Camera reconnect remains pinned to the same device instead of silently switching cameras.

### Workflow reliability
- Pose-processing exceptions no longer crash the kiosk on a single bad frame.
- Unexpected workflow exceptions are caught at the assessment boundary.
- Completed/partial assessment data is attempted to be saved before recovery.
- Technical details remain in the local log while the operator receives a friendly recovery message.
- Questionnaire answers are persisted as a draft so Back/Home no longer silently destroys progress.

### UI / navigation
- Refreshed Raspberry Pi home screen with a clearer primary New Assessment action.
- Camera/system status is visible on the landing screen.
- Added a dedicated status action.
- Assessment introduction now uses a structured kiosk overview.
- Camera HUD uses the same dark/navy + cyan visual language as the touch UI.
- Consistent live READY indicator, progress bar and footer treatment.
- Large touch-first controls remain compatible with the 7-inch 1024×600 panel.

## Compatibility

- Stored feature/algorithm meaning remains **ALGORITHM_VERSION 1.4**.
- Stored JSON schema remains **1.4.0**.
- This is therefore a UI/reliability release over the existing v1.4 analysis pipeline.
- MoveNet Lightning remains the Raspberry Pi pose backend.

## Validation

- Python compile check: passed.
- Existing algorithm/pipeline tests: **74 passed**.

## Deployment

Do not copy `.venv` from another machine.

For an existing Pi installation, back up the current project/data first, replace the application source, then run:

```bash
cd ~/aira-oa/aira-oa-kiosk
source .venv/bin/activate
./start_rpi.sh
```

The first launch should show the new AIRA-OA v1.5 home screen and the camera status should remain around 1280×720 @ 30 FPS.
