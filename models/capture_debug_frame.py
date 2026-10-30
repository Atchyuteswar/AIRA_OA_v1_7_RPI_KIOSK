import cv2
import os

OUTPUT = "/home/aira-oa/aira-oa-kiosk/models/debug_camera.jpg"

cap = cv2.VideoCapture(0, cv2.CAP_V4L2)

cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
cap.set(cv2.CAP_PROP_FPS, 30)

if not cap.isOpened():
    print("ERROR: Camera could not be opened")
    raise SystemExit(1)

# Let camera stabilize
for _ in range(30):
    ret, frame = cap.read()

if not ret:
    print("ERROR: Could not read frame")
    cap.release()
    raise SystemExit(1)

cv2.imwrite(OUTPUT, frame)

print("Camera frame saved:")
print(OUTPUT)
print("Frame shape:", frame.shape)
print("Pixel mean:", frame.mean())

cap.release()
