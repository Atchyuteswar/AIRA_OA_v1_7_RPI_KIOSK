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
output_index = output_details[0]["index"]

input_shape = input_details[0]["shape"]

MODEL_HEIGHT = int(input_shape[1])
MODEL_WIDTH = int(input_shape[2])

print("Model input:", input_shape)
print("Model output:", output_details[0]["shape"])

# Open camera
cap = cv2.VideoCapture(0, cv2.CAP_V4L2)

if not cap.isOpened():
    print("ERROR: Could not open camera")
    raise SystemExit(1)

# Request camera configuration
cap.set(
    cv2.CAP_PROP_FOURCC,
    cv2.VideoWriter_fourcc(*"MJPG")
)

cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
cap.set(cv2.CAP_PROP_FPS, 30)

width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
camera_fps = cap.get(cv2.CAP_PROP_FPS)

print(
    f"Camera: {width}x{height} @ {camera_fps:.1f} FPS"
)

print("\nStarting headless pose detection...")
print("Running 100 frames...\n")

total_inference_time = 0.0
successful_frames = 0

start_total = time.perf_counter()

last_keypoints = None

for frame_number in range(100):

    ret, frame = cap.read()

    if not ret:
        print("ERROR: Camera frame failed")
        break

    # BGR → RGB
    rgb = cv2.cvtColor(
        frame,
        cv2.COLOR_BGR2RGB
    )

    # Resize to MoveNet input
    input_image = cv2.resize(
        rgb,
        (MODEL_WIDTH, MODEL_HEIGHT)
    )

    # UINT8 model input
    input_tensor = np.expand_dims(
        input_image,
        axis=0
    ).astype(np.uint8)

    # Inference timing
    inference_start = time.perf_counter()

    interpreter.set_tensor(
        input_index,
        input_tensor
    )

    interpreter.invoke()

    keypoints = interpreter.get_tensor(
        output_index
    )[0, 0]

    inference_time = (
        time.perf_counter() - inference_start
    )

    total_inference_time += inference_time

    # Count valid detections
    confident_points = 0

    for y, x, confidence in keypoints:

        if confidence >= CONFIDENCE_THRESHOLD:
            confident_points += 1

    if confident_points > 0:
        successful_frames += 1

    last_keypoints = keypoints

    # Print progress
    if (frame_number + 1) % 10 == 0:

        print(
            f"Frame {frame_number + 1:3d}/100 | "
            f"confident keypoints: "
            f"{confident_points:2d}/17 | "
            f"inference: "
            f"{inference_time * 1000:.1f} ms"
        )

cap.release()

total_time = time.perf_counter() - start_total

if successful_frames > 0:

    average_inference_ms = (
        total_inference_time /
        successful_frames *
        1000
    )

    inference_fps = (
        1000 / average_inference_ms
    )

else:

    average_inference_ms = 0
    inference_fps = 0

print("\n" + "=" * 55)
print("AIRA-OA MoveNet Headless Test")
print("=" * 55)

print(
    f"Camera resolution : {width}x{height}"
)

print(
    f"Camera FPS         : {camera_fps:.1f}"
)

print(
    f"Frames processed   : {100}"
)

print(
    f"Valid pose frames  : {successful_frames}"
)

print(
    f"Avg inference time : "
    f"{average_inference_ms:.1f} ms"
)

print(
    f"Estimated inference: "
    f"{inference_fps:.1f} FPS"
)

if last_keypoints is not None:

    print("\nFinal detected pose:")

    for i, (y, x, confidence) in enumerate(
        last_keypoints
    ):

        if confidence >= CONFIDENCE_THRESHOLD:

            print(
                f"{KEYPOINT_NAMES[i]:15s} "
                f"x={x:.3f} "
                f"y={y:.3f} "
                f"confidence={confidence:.3f}"
            )

print("\nSUCCESS: Camera + MoveNet inference working.")
