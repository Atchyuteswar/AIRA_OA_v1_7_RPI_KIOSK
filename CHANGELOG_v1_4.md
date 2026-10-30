# v1.4.0 - robustness and correctness release

## Bugs fixed (found by reading v1.3)
| Area | v1.3 problem | v1.4 |
|---|---|---|
| Geometry | Angles/distances computed on 0-1 normalised coords -> distorted on 16:9 frames; z mixed with x/y | pixel-space geometry; metric world landmarks for knee angle |
| Left/right | Image mirrored *before* pose, so anatomical sides were unreliable | pose on raw frame; mirroring is display-only |
| STS | Fixed angle thresholds (118/92/142 deg) + state machine that could stall; median over 9 frames added lag; "valid rep" counted stand-ups that never sat | offline analysis: resample, de-spike, zero-phase smooth, adaptive peak/valley detection, timing at 20/80 % of own range, per-rep validation |
| STS | Crash-prone leftover line `coefficient_of_variATION(...) if False else ...` | removed |
| Gait | Steps from single-ankle height threshold (fails walking toward camera); cadence divided by total time incl. idle; L/R *counts* used as "symmetry" (always ~1); "hip path" measured how far the person walked | ankle-separation extrema (PCA axis), walking-bout cadence, symmetry from step time and step length, hip vertical oscillation |
| Balance | Includes settling movement; frame counts drive velocity; mixed x/y pixel scales | 1 s settle discarded, resampled, drift separated, 95 % ellipse area, walking-away detection |
| Quality | A test with 0 reps / 0 steps could PASS and become baseline | evidence gates (reps, steps, duration, movement) |
| Quality | Missing frames penalised twice (valid ratio *and* mean quality) | mean visibility over detected frames only |
| Baseline | Earliest session used even if unusable; skipped tests compared as -100 % | earliest *usable* compatible session; only modalities qualified in both sessions are compared |
| Fusion | `fusion_coverage` was the mean weight, not coverage | `fusion_quality` (mean) and `fusion_coverage` (evidence out of 3 modalities) |
| Timing | `time.time()` per frame, blocking reads with stale-frame lag | capture thread, per-frame capture timestamps |
| Camera | Reconnect rescanned all indices (could switch camera, froze UI); Windows-only backends; exited if no camera | reopens the same device, per-OS backends, app usable without camera, `--video` |
| UI | Keystrokes typed in forms leaked into camera loops; closing the window during a test did nothing; hard-coded 1080p layout; Cancel destroyed the root window | key queue only in camera mode, close = quit event, fixed 1280x720 canvas, single persistent root |
| Data | Non-atomic writes; ASCII-only names stripped accents/Indic scripts; CWD-relative paths lost history; patient-ID race; unreadable file hid data silently | atomic writes, Unicode names, project-anchored paths, exclusive ID allocation, logged skips |
| Validation | Consent/age validated only in the UI | validated in the data layer |
| Perf | ~12 full-frame copies per HUD frame | panels blend only their rectangle; pose on a downscaled copy |

## Added
Review/repeat screen after each test - back navigation without losing tests - questionnaire undo (Backspace) -
HTML report + CSV export - patient search - PARTIAL quality state - per-repetition details in the JSON -
new features (descent time, seated dwell, 5-rep time, step-length symmetry, 95 % sway ellipse) -
rotating log file - 74 unit tests + end-to-end/UI smoke tests.

## Compatibility
`algorithm_version` and `schema_version` are stored in every session. v1.3 records load but are not mixed into baselines.

### Raspberry Pi deployment variant

- Added `requirements-rpi.txt`.
- Added `install_rpi.sh`, `start_rpi.sh`, `setup_autostart.sh` and `tools/rpi_diagnostics.py`.
- Added a Raspberry Pi MediaPipe Tasks Pose Landmarker backend in `core/pose_rpi.py`.
- Kept the existing v1.4 `PoseFrame` contract so STS, gait, balance, quality, fingerprint and personalization logic can be reused.
- Added optional Raspberry Pi fullscreen startup.
- Added Raspberry Pi deployment documentation in `README_RPI.md`.

## Raspberry Pi Touch Kiosk build
- Native 1024x600 fullscreen layout for the physical 7-inch touchscreen.
- Touch navigation and action controls across forms, camera flow, questionnaire,
  review, results, history and detail views.
- Built-in QWERTY/numeric keyboard for patient data entry.
- Touch paging for patient/history/report views; no mouse wheel required.
- Raspberry Pi pose backend switched to MoveNet SinglePose Lightning + TFLite
  to avoid the Pi 4 native MediaPipe Tasks illegal-instruction failure.
- Existing downstream v1.4 analysis and persistence contracts retained.
