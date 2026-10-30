import cv2
import numpy as np
import time
from tflite_runtime.interpreter import Interpreter

MODEL = "movenet_lightning.tflite"

# MoveNet keypoint connections
EDGES = [
    (0, 1), (0, 2),
    (1, 3), (2, 4),
    (0, 5), (0, 6),
    (5, 7), (7, 9),
    (6, 8), (8, 10),
    (5, 6),
    (5, 11), (6, 12),
    (11, 12),
    (11, 13), (13, 15),
    (12, 14), (14, 16),
]

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

CONFIDENCE_THRESHOLD = 0.30

print("Loading MoveNet...")

interpreter = Interpreter(
    model_path=MODEL,
    num_threads=4
)

interpreter.allocate_tensors()

input_details = interpreter.get_input_details()
output_details = interpreter.get_output_details()

input_index = input_details[0]["index"]
input_shape = input_details[0]["shape"]

MODEL_HEIGHT = int(input_shape[1])
MODEL_WIDTH = int(input_shape[2])

print("Model input:", input_shape)
print("Model output:", output_details[0]["shape"])

# Camera
cap = cv2.VideoCapture(0, cv2.CAP_V4L2)

if not cap.isOpened():
    print("ERROR: Could not open camera")
    raise SystemExit(1)

# Request 1280x720 MJPEG
cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
cap.set(cv2.CAP_PROP_FPS, 30)

actual_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
actual_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
actual_fps = cap.get(cv2.CAP_PROP_FPS)

print(
    f"Camera: {actual_width}x{actual_height} @ {actual_fps:.1f} FPS"
)

previous_time = time.time()
fps = 0.0

print("\nStarting camera...")
print("Press Q to quit.\n")

while True:

    ret, frame = cap.read()

    if not ret:
        print("Camera frame failed")
        break

    # BGR → RGB
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

    # Resize to MoveNet input
    input_image = cv2.resize(
        rgb,
        (MODEL_WIDTH, MODEL_HEIGHT)
    )

    # MoveNet UINT8 input
    input_tensor = np.expand_dims(
        input_image,
        axis=0
    ).astype(np.uint8)

    # Inference
    interpreter.set_tensor(
        input_index,
        input_tensor
    )

    interpreter.invoke()

    # Output:
    # [1, 1, 17, 3]
    # y, x, confidence
    keypoints = interpreter.get_tensor(
        output_details[0]["index"]
    )[0, 0]

    # Draw keypoints
    points = []

    for i, (y, x, confidence) in enumerate(keypoints):

        px = int(x * frame.shape[1])
        py = int(y * frame.shape[0])

        points.append((px, py))

        if confidence >= CONFIDENCE_THRESHOLD:

            cv2.circle(
                frame,
                (px, py),
                6,
                (0, 255, 0),
                -1
            )

            cv2.putText(
                frame,
                str(i),
                (px + 7, py - 7),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (0, 255, 0),
                1,
                cv2.LINE_AA
            )

    # Draw skeleton
    for a, b in EDGES:

        if (
            keypoints[a][2] >= CONFIDENCE_THRESHOLD
            and keypoints[b][2] >= CONFIDENCE_THRESHOLD
        ):

            cv2.line(
                frame,
                points[a],
                points[b],
                (255, 0, 0),
                2
            )

    # FPS
    current_time = time.time()
    dt = current_time - previous_time

    if dt > 0:
        instant_fps = 1.0 / dt
        fps = 0.9 * fps + 0.1 * instant_fps

    previous_time = current_time

    cv2.putText(
        frame,
        f"MoveNet FPS: {fps:.1f}",
        (20, 40),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.9,
        (0, 255, 0),
        2
    )

    cv2.putText(
        frame,
        f"Camera: {actual_width}x{actual_height}",
        (20, 75),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (255, 255, 255),
        2
    )

    cv2.imshow(
        "AIRA-OA - MoveNet Test",
        frame
    )

    key = cv2.waitKey(1) & 0xFF

    if key == ord("q"):
        break

cap.release()
cv2.destroyAllWindows()
