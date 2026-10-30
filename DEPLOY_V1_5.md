# AIRA-OA v1.5 Raspberry Pi deployment

This package is the current v1.4 analysis pipeline upgraded to the v1.5 kiosk/reliability layer.

## Important

- Do **not** copy a `.venv` from another machine.
- The updater intentionally preserves the target Pi's `data/` and `.venv/`.
- The Raspberry Pi pose backend remains MoveNet Lightning.
- The camera profile is pre-negotiated as 1280×720 MJPEG @ 30 FPS.

## Recommended update

1. Copy/extract this package onto the Pi.
2. Run the updater against the existing installation:

```bash
cd ~/aira-oa/AIRA_OA_v1_5_RPI_KIOSK
chmod +x update_existing_rpi.sh
./update_existing_rpi.sh ~/aira-oa/aira-oa-kiosk
```

3. Start the application:

```bash
cd ~/aira-oa/aira-oa-kiosk
source .venv/bin/activate
./start_rpi.sh
```

## First verification

The home screen should show:

- Camera Ready
- 1280×720
- approximately 30 FPS
- AIRA-OA v1.5 visual design

Then test this exact path:

**New Assessment → New Patient → Assessment Overview → Sit-to-Stand → Gait → Balance → Symptom Profile → Results → History**

Also test:

- Back during every screen
- Home during an assessment
- Repeat a failed-quality movement test
- Skip a test
- Disconnect/reconnect the USB camera
- Complete a questionnaire, go Back, then return to it
- Export a report
- Reopen the assessment from History

## Rollback

The updater creates a timestamped backup under:

```text
<target>/backups/v1_5_update_<timestamp>/
```

If necessary, restore the backed-up application directories while leaving `data/` and `.venv/` untouched.
