#!/usr/bin/env python3
"""Pre-flight diagnostics for the AIRA-OA v1.4 Raspberry Pi touch kiosk."""
from __future__ import annotations
import platform, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent; sys.path.insert(0,str(ROOT))
print("AIRA-OA v1.4 Raspberry Pi Touch diagnostics"); print("="*64)
print(f"Architecture : {platform.machine()}"); print(f"Python       : {sys.version.split()[0]}")
if platform.machine().lower() not in {"aarch64","arm64"}: print("WARNING: expected aarch64/arm64.")
for name, fn in [("Tkinter", lambda: __import__('tkinter')), ("OpenCV", lambda: __import__('cv2'))]:
    try:
        mod=fn(); print(f"{name:<13}: {getattr(mod,'__version__','OK')}")
    except Exception as exc: print(f"{name:<13}: FAIL ({exc})")
try:
    import tflite_runtime
    print(f"TFLite runtime: {getattr(tflite_runtime,'__version__','OK')}")
except Exception as exc:
    try:
        import tensorflow as tf
        print(f"TensorFlow Lite: {tf.__version__}")
    except Exception:
        print(f"TFLite runtime: FAIL ({exc})")
model=ROOT/"models"/"movenet_lightning.tflite"
print(f"MoveNet model : {'OK' if model.exists() and model.stat().st_size>0 else 'MISSING'}")
try:
    from core.config import DISPLAY
    print(f"Touch display : {DISPLAY.canvas_width}x{DISPLAY.canvas_height}")
except Exception as exc: print(f"Touch display : FAIL ({exc})")
try:
    from core.camera import CameraManager
    cams=CameraManager().discover()
    if cams:
        for c in cams: print(f"Camera       : index={c.index} {c.backend} {c.resolution} {c.fps:.1f}fps")
    else: print("Camera       : NONE FOUND")
except Exception as exc: print(f"Camera       : FAIL ({exc})")
