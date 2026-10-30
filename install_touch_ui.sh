#!/usr/bin/env bash
set -euo pipefail

PATCH_ROOT="$(cd "$(dirname "$0")" && pwd)"
TARGET="${1:-$PWD}"

if [[ ! -f "$TARGET/app.py" || ! -d "$TARGET/core" ]]; then
  echo "ERROR: '$TARGET' does not look like the AIRA-OA project directory."
  echo "Usage: bash install_touch_ui.sh /home/aira-oa/aira-oa-kiosk"
  exit 1
fi

STAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP="$TARGET/backups/touch_ui_$STAMP"
mkdir -p "$BACKUP/core"

for f in display.py screens.py flow.py; do
  cp "$TARGET/core/$f" "$BACKUP/core/$f"
done
if [[ -f "$TARGET/core/touch.py" ]]; then
  cp "$TARGET/core/touch.py" "$BACKUP/core/touch.py"
fi

cp "$PATCH_ROOT/core/display.py" "$TARGET/core/display.py"
cp "$PATCH_ROOT/core/screens.py" "$TARGET/core/screens.py"
cp "$PATCH_ROOT/core/flow.py" "$TARGET/core/flow.py"
cp "$PATCH_ROOT/core/touch.py" "$TARGET/core/touch.py"

cd "$TARGET"
python -m compileall -q core

echo
echo "=============================================="
echo " AIRA-OA Touch UI patch installed successfully"
echo "=============================================="
echo "Backup: $BACKUP"
echo
echo "Your existing pose backend and patient data were not replaced."
echo "Launch with: ./start_rpi.sh"
