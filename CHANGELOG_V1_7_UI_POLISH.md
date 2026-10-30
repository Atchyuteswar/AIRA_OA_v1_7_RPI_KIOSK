# AIRA-OA v1.7 - UI polish (interface only)

No change to pose, camera, algorithms, quality gates, saved data or reports.
Changed files: core/config.py (kiosk canvas height only), core/display.py, core/hud.py,
core/flow.py (drawing and layout only), core/screens.py, core/touch.py.

## Live camera screens (1024x600 kiosk)
- The drawn interface now sits above the touch bar; before, the bar covered the footer and the bottom of the results screen.
- Header: removed the static "READY" label; step progress, capture size/fps shown at readable size.
- Rounded cards with auto-fitting values, readable label sizes, pills for REC / warnings.
- Exercise instructions show for 8 s, then collapse to a small label so they no longer cover the participant.
- Touch bar: equal-width buttons, no outline borders; "Restart" is no longer highlighted as the primary action (matched "START").
- Symptom profile: uniform option rows with number badges; results: aligned tiles, fitted text, file names instead of long paths.
- Keyboard-shortcut hints are hidden in kiosk mode (the touch bar replaces them); desktop mode keeps them.

## Tk screens
- One theme: flat borderless buttons with hover/pressed states, subtle card borders, consistent sizes (minimum text 9 pt).
- Nav bars list actions in the order given (Previous, Next ... were reversed); Cancel/Exit use a muted danger style.
- Home: accent hero card, live metrics on each card (patients, camera FPS, latest quality).
- Patient entry, registration form (larger fields, themed dropdowns, tappable consent toggle), select patient.
- Keyboard: aligned 20-column grid with full-width rows, larger keys, clear special keys, tidy numeric keypad.
- Patient history: tappable patient cards, larger text, themed search box.
- Assessment details: structured sections with coloured PASS/REVIEW values and drag-to-scroll (Raw JSON view kept).
- Dialogs: centred cards with an accent bar, larger text, consistent buttons.
