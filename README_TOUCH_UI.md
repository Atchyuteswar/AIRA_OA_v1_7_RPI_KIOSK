# AIRA-OA Raspberry Pi Touch UI Patch

This is a **UI-only patch** for the working AIRA-OA Raspberry Pi v1.4 project.

It intentionally does **not** replace the camera, MoveNet pose backend, challenge algorithms, patient data, models, or storage files.

## Physical display target

The Raspberry Pi prototype target is a **7-inch 1024x600 landscape touchscreen**. On Raspberry Pi (`AIRA_RPI=1`), the patch automatically uses fullscreen mode at the panel resolution and compacts form spacing, fonts, navigation bars, dialogs and the on-screen keyboard for this footprint.

## What it adds

- Large touch targets sized for the 7-inch 1024x600 touchscreen.
- Touch navigation on camera-driven screens: Home / Back / Continue / Start / Pause / Restart / Finish / Repeat / Accept / Skip / New / Details / Export as appropriate.
- An on-screen keyboard for patient name/reference, age, contact and history/patient search fields.
- Numeric keyboard mode for age/contact.
- Touch-friendly camera/error/confirmation dialogs.
- Larger Treeview rows and buttons for finger-friendly patient/history selection.
- Home/Back/Cancel navigation without requiring a physical keyboard.
- Existing keyboard shortcuts remain available for development/debugging.

## Important

The patch only changes:

- `core/display.py`
- `core/screens.py`
- `core/flow.py`
- adds `core/touch.py`

Your current Raspberry Pi pose backend is preserved.

## Apply on the Raspberry Pi

From the AIRA-OA project directory:

```bash
bash /path/to/AIRA_OA_RPI_TOUCH_UI_PATCH/install_touch_ui.sh ~/aira-oa/aira-oa-kiosk
```

Or run it from the project directory after extracting the patch:

```bash
bash install_touch_ui.sh ~/aira-oa/aira-oa-kiosk
```

The installer creates a timestamped backup under:

```text
backups/touch_ui_YYYYMMDD_HHMMSS/
```

Then launch normally:

```bash
./start_rpi.sh
```

## Safety

Patient data is not modified by this patch.

The patch is designed for the current non-diagnostic AIRA-OA research prototype and does not change its movement-analysis algorithms or clinical claims.
