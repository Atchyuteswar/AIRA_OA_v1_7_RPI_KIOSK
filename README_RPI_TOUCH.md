# AIRA-OA v1.6 — Raspberry Pi Touch Kiosk

This edition is designed for the Vision Guard prototype: Raspberry Pi 4 + USB RGB webcam + 7-inch touchscreen, with **no keyboard or mouse required for normal operation**.

## Install
1. Copy this folder to `~/AIRA_OA_v1_4`.
2. `cd ~/AIRA_OA_v1_4`
3. `chmod +x install_rpi.sh start_rpi.sh start_kiosk.sh setup_autostart.sh`
4. `./install_rpi.sh`
5. `./start_rpi.sh`
6. If the complete assessment works, run `./setup_autostart.sh`.
7. Reboot. AIRA-OA launches automatically in fullscreen kiosk mode.

## Touch operation
- Large touch buttons replace camera-screen keyboard shortcuts.
- Patient text fields use the Raspberry Pi Onboard touch keyboard.
- Combo boxes, checkboxes, history and report screens are standard Tk touch controls.
- The Raspberry Pi build uses MoveNet SinglePose Lightning + TFLite for CPU inference and converts results to the existing AIRA-OA PoseFrame.

## Maintenance
SSH into the Pi if you need a shell. The kiosk auto-restarts after a crash.
To disable desktop autostart:
`rm ~/.config/autostart/aira-oa.desktop ~/.config/autostart/aira-oa-unclutter.desktop`

## Safety
AIRA-OA is a non-diagnostic research prototype. Its movement features and custom symptom index are not a clinical diagnosis.


## v1.6 upgrade

See `CHANGELOG_V1_5.md` and `DEPLOY_V1_5.md`. The v1.6 layer preserves the v1.4 analysis semantics while hardening camera negotiation/reconnect, assessment recovery, questionnaire drafts, and the touch-first kiosk UI.

## v1.6 refinement
The kiosk UI now separates system readiness, workflow status and detailed camera diagnostics. Patient History is a touch-first patient hub and can launch a new assessment for the selected patient. Transient pose inference failures are retried and assessment recovery surfaces the technical exception and log path.
