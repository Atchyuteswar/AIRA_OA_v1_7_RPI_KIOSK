#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
source .venv/bin/activate
export AIRA_RPI=1
export AIRA_RPI_TOUCH=1
export AIRA_RPI_FULLSCREEN=1
export AIRA_POSE_BACKEND=movenet
export AIRA_MOVENET_INPUT=192
export AIRA_MOVENET_THREADS="${AIRA_MOVENET_THREADS:-2}"
export AIRA_CAMERA_INDEX="${AIRA_CAMERA_INDEX:-0}"
export OPENCV_VIDEOIO_PRIORITY_V4L2=1

# Pre-negotiate the known-good USB webcam profile before OpenCV opens it.
# Failure is non-fatal: camera.py performs the same negotiation itself.
if command -v v4l2-ctl >/dev/null 2>&1 && [[ -e "/dev/video${AIRA_CAMERA_INDEX}" ]]; then
  v4l2-ctl -d "/dev/video${AIRA_CAMERA_INDEX}" --set-fmt-video=width=1280,height=720,pixelformat=MJPG >/dev/null 2>&1 || true
  v4l2-ctl -d "/dev/video${AIRA_CAMERA_INDEX}" --set-parm=30 >/dev/null 2>&1 || true
fi
exec python app.py --camera "${AIRA_CAMERA_INDEX}" "$@"
