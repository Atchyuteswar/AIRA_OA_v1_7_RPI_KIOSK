#!/usr/bin/env bash
set -u
cd "$(dirname "$0")"
export AIRA_RPI=1 AIRA_KIOSK=1 AIRA_TOUCH=1 AIRA_POSE_BACKEND=tasks
export PYTHONUNBUFFERED=1
# Keep the kiosk alive if the app ever crashes during a prototype demo.
while true; do
  .venv/bin/python app.py --kiosk || true
  sleep 2
done
