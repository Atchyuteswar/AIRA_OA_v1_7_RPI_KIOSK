# AIRA-OA v1.6 Raspberry Pi Touch Edition

This is the complete Raspberry Pi kiosk build for the physical **7-inch
1024x600 touchscreen**. The normal workflow is keyboard-free.

The Pi pose backend is MoveNet SinglePose Lightning through TensorFlow
Lite/LiteRT. Existing v1.4 downstream analysis remains based on the shared
`PoseFrame` interface: readiness, sit-to-stand, gait, balance, quality gates,
fingerprinting, patient baselines, longitudinal observed-change comparison,
local JSON records, HTML reports and CSV export.

## Install

```bash
chmod +x install_rpi.sh start_rpi.sh tools/rpi_diagnostics.py
./install_rpi.sh
./tools/rpi_diagnostics.py
./start_rpi.sh
```

The installer uses Raspberry Pi OS OpenCV from apt and installs the official
`tflite-runtime 2.14.0` ARM64 wheel through pip. The MoveNet model is downloaded
from TensorFlow Hub when network access is available. If it cannot be
retrieved, copy `movenet_lightning.tflite` into `models/` manually.

## Touch behavior

- 1024x600 native fullscreen UI
- large touch targets on every screen
- Back / Home / Continue navigation
- touch-only camera controls
- touch repeat / skip / accept / finish controls
- built-in QWERTY and numeric keyboard
- touch patient/history paging
- touch report scrolling
- touch dialogs and confirmations

The physical keyboard/mouse remain useful for maintenance but are not required
for a normal patient assessment.

## Camera

The launcher defaults to camera index 0. Override with:

```bash
AIRA_CAMERA_INDEX=1 ./start_rpi.sh
```

Diagnostics:

```bash
./tools/rpi_diagnostics.py
python tools/camera_check.py
```

## Important research limitation

MoveNet supplies 17 2-D keypoints, not MediaPipe BlazePose's metric world
landmarks. On this Pi build, knee angles therefore use the existing image-plane
geometry fallback. Pi-derived measurements should be benchmarked for
repeatability before mixing them with desktop-derived measurements.

AIRA-OA remains a **non-diagnostic research prototype**. It does not establish
clinical diagnosis or validated OA probability.
