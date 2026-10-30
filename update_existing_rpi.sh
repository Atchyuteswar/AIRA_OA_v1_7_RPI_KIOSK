#!/usr/bin/env bash
set -euo pipefail

SOURCE="$(cd "$(dirname "$0")" && pwd)"
TARGET="${1:-$PWD}"

if [[ ! -f "$SOURCE/app.py" || ! -d "$SOURCE/core" ]]; then
  echo "ERROR: source package is incomplete: $SOURCE" >&2
  exit 1
fi
if [[ ! -f "$TARGET/app.py" || ! -d "$TARGET/core" ]]; then
  echo "ERROR: target '$TARGET' does not look like an AIRA-OA installation." >&2
  echo "Usage: $SOURCE/update_existing_rpi.sh /home/aira-oa/aira-oa-kiosk" >&2
  exit 1
fi

STAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP="$TARGET/backups/v1_6_update_$STAMP"
mkdir -p "$BACKUP"

echo "AIRA-OA v1.6 updater"
echo "Source: $SOURCE"
echo "Target: $TARGET"
echo

# Preserve the existing runtime and all patient/session records.
for item in app.py core assessment challenges models requirements-rpi.txt requirements.txt \
            start_rpi.sh install_rpi.sh install_touch_ui.sh setup_autostart.sh run.sh \
            README.md CHANGELOG_TOUCH_UI.md CHANGELOG_V1_5.md CHANGELOG_V1_6.md; do
  [[ -e "$TARGET/$item" ]] && cp -a "$TARGET/$item" "$BACKUP/"
done
echo "Backup: $BACKUP"

# Copy application code while intentionally leaving data/ and .venv/ untouched.
cp -a "$SOURCE/app.py" "$TARGET/"
cp -a "$SOURCE/core" "$TARGET/"
cp -a "$SOURCE/assessment" "$TARGET/"
cp -a "$SOURCE/challenges" "$TARGET/"
cp -a "$SOURCE/models/movenet_lightning.tflite" "$TARGET/models/" 2>/dev/null || true
cp -a "$SOURCE/models/"*.py "$TARGET/models/" 2>/dev/null || true

for item in requirements-rpi.txt requirements.txt start_rpi.sh install_rpi.sh \
            install_touch_ui.sh setup_autostart.sh run.sh README.md \
            CHANGELOG_TOUCH_UI.md CHANGELOG_V1_5.md CHANGELOG_V1_6.md; do
  [[ -e "$SOURCE/$item" ]] && cp -a "$SOURCE/$item" "$TARGET/"
done

find "$TARGET/core" "$TARGET/assessment" "$TARGET/challenges" "$TARGET/models" \
  -type d -name "__pycache__" -prune -exec rm -rf {} + 2>/dev/null || true

chmod +x "$TARGET"/*.sh "$TARGET"/tools/*.py 2>/dev/null || true

cd "$TARGET"
python -m compileall -q core assessment challenges

echo
echo "=============================================="
echo " AIRA-OA v1.6 update installed"
echo "=============================================="
echo "Patient/session data was preserved."
echo "Existing .venv was preserved."
echo
echo "Start with:"
echo "  cd $TARGET"
echo "  source .venv/bin/activate"
echo "  ./start_rpi.sh"
