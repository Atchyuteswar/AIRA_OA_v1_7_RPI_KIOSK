import cv2
import numpy as np
import time
from tflite_runtime.interpreter import Interpreter

MODEL = "movenet_lightning.tflite"

KEYPOINT_NAMES = [
    "nose",
    "left_eye",
    "right_eye",
    "left_ear",
    "right_ear",
    "left_shoulder",
    "right_shoulder",
    "left_elbow",
    "right_elbow",
    "left_wrist",
    "right_wrist",
    "left_hip",
    "right_hip",
    "left_knee",
    "right_knee",
    "left_ankle",
    "right_ankle",
]

print("Loading MoveNet...")

interpreter = Interpreter(
    model_path=MODEL,
    num_threads=4
)

interpreter.allocate_tensors()

input_details = interpreter.get_input_details()
output_details = interpreter.get_output_details()

input_shape = input_details[0]["shape"]

print("Input:", input_shape)
print("Output:", output_details[0]["shape"])

cap = cv2.VideoCapture(0, cv2.CAP_V4L2)

cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
cap.set(cv2.CAP_PROP_FPS, 30)

if not cap.isOpened():
    print("ERROR: Camera failed")
    raise SystemExit(1)

print()
print("Stand directly in front of the camera.")
print("Capturing 30 frames...")
print()

for i in range(30):

    ret, frame = cap.read()

    if not ret:
        print("Camera read failed")
        continue

    # OpenCV = BGR
    # MoveNet expects RGB
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

    # Resize to model input
    input_image = cv2.resize(rgb, (192, 192))

    input_tensor = np.expand_dims(input_image, axis=0)
    input_tensor = input_tensor.astype(np.uint8)

    interpreter.set_tensor(
        input_details[0]["index"],
        input_tensor
    )

    start = time.perf_counter()

    interpreter.invoke()

    elapsed = (time.perf_counter() - start) * 1000

    output = interpreter.get_tensor(
        output_details[0]["index"]
    )

    keypoints = output[0, 0, :, :]

    scores = keypoints[:, 2]

    max_idx = np.argmax(scores)
    max_score = scores[max_idx]

    if i % 5 == 0:

        print(
            f"Frame {i+1:02d} | "
            f"max={max_score:.3f} | "
            f"mean={scores.mean():.3f} | "
            f"time={elapsed:.1f} ms"
        )

        print(
            f"  Best: {KEYPOINT_NAMES[max_idx]} "
            f"score={scores[max_idx]:.3f} "
            f"x={keypoints[max_idx][1]:.3f} "
            f"y={keypoints[max_idx][0]:.3f}"
        )

cap.release()

print()
print("Diagnostic complete.")
