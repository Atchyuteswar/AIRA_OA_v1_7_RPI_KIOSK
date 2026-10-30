"""Camera diagnostic:  python tools/camera_check.py [--video file]"""
import argparse, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.camera import CameraManager

ap = argparse.ArgumentParser(); ap.add_argument("--video"); ap.add_argument("--seconds", type=float, default=3.0)
a = ap.parse_args()
m = CameraManager(a.video)
print("\nAIRA-OA camera diagnostic\n" + "=" * 60)
if a.video:
    info = m.open()
else:
    cams = m.discover()
    for c in cams:
        print(f"index={c.index} | {c.backend} | {c.resolution} | {c.fps:.1f} fps declared")
    info = m.open() if cams else None
if not info:
    print("No usable camera found. Close other apps using the camera and check the connection."); sys.exit(1)
end, n = time.perf_counter() + a.seconds, 0
while time.perf_counter() < end:
    if m.read(0.5) is not None:
        n += 1
h = m.health()
print(f"\nSELECTED {info.name} via {info.backend}  {info.resolution}")
print(f"measured {h['measured_fps']} fps, {n} frames in {a.seconds:.0f}s, dropped {h['dropped_frames']}")
if h["measured_fps"] and h["measured_fps"] < 15:
    print("WARNING: below 15 fps - lower the resolution or close other applications.")
m.close()
