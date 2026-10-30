#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 is required." >&2; exit 1
fi

sudo apt-get update
sudo apt-get install -y python3-venv python3-tk python3-opencv v4l-utils curl ca-certificates

PYBIN="$(command -v python3)"
"$PYBIN" -m venv --system-site-packages .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-rpi.txt

mkdir -p models data/patients data/sessions reports
MODEL="models/movenet_lightning.tflite"
MODEL_URL="${AIRA_MOVENET_MODEL_URL:-https://tfhub.dev/google/lite-model/movenet/singlepose/lightning/tflite/float16/4?lite-format=tflite}"
if [[ ! -s "$MODEL" ]]; then
  echo "Downloading MoveNet Lightning model..."
  if ! curl -L --fail --retry 3 --connect-timeout 15 "$MODEL_URL" -o "$MODEL"; then
    rm -f "$MODEL"
    echo
    echo "Automatic model download failed. The application is otherwise installed."
    echo "Copy movenet_lightning.tflite into: $(pwd)/$MODEL"
    echo "Then run ./start_rpi.sh again."
  fi
fi

chmod +x start_rpi.sh tools/*.py 2>/dev/null || true
python - <<'PY'
import platform, sys
print("Python:", sys.version.split()[0])
print("Architecture:", platform.machine())
try:
    import tflite_runtime
    print("TFLite runtime:", getattr(tflite_runtime, "__version__", "installed"))
except Exception as exc:
    print("TFLite runtime import failed:", exc)
PY

echo
if [[ -s "$MODEL" ]]; then
  echo "AIRA-OA Raspberry Pi installation is ready."
else
  echo "AIRA-OA is installed, but the MoveNet model still needs to be copied into models/."
fi
