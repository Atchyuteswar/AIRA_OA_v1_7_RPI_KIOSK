import cv2
import numpy as np
from tflite_runtime.interpreter import Interpreter

MODEL = "movenet_lightning.tflite"

interpreter = Interpreter(
    model_path=MODEL,
    num_threads=4
)

interpreter.allocate_tensors()

inp = interpreter.get_input_details()[0]
out = interpreter.get_output_details()[0]

print("Input shape:", inp["shape"])
print("Input dtype:", inp["dtype"])
print("Input quantization:", inp["quantization"])

cap = cv2.VideoCapture(0, cv2.CAP_V4L2)

cap.set(
    cv2.CAP_PROP_FOURCC,
    cv2.VideoWriter_fourcc(*"MJPG")
)

cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
cap.set(cv2.CAP_PROP_FPS, 30)

if not cap.isOpened():
    print("ERROR: Camera could not be opened")
    raise SystemExit(1)

print("Camera opened")

for i in range(10):

    ret, frame = cap.read()

    if not ret:
        print("Frame", i + 1, "FAILED")
        continue

    print(
        f"\nFrame {i + 1}"
    )

    print(
        "  Camera frame:",
        frame.shape,
        frame.dtype
    )

    print(
        "  Pixel range:",
        frame.min(),
        "to",
        frame.max()
    )

    print(
        "  Pixel mean:",
        float(frame.mean())
    )

    rgb = cv2.cvtColor(
        frame,
        cv2.COLOR_BGR2RGB
    )

    resized = cv2.resize(
        rgb,
        (192, 192)
    )

    input_tensor = np.expand_dims(
        resized,
        axis=0
    ).astype(np.uint8)

    print(
        "  Model input:",
        input_tensor.shape,
        input_tensor.dtype
    )

    print(
        "  Model input range:",
        input_tensor.min(),
        "to",
        input_tensor.max()
    )

    print(
        "  Model input mean:",
        float(input_tensor.mean())
    )

    interpreter.set_tensor(
        inp["index"],
        input_tensor
    )

    interpreter.invoke()

    result = interpreter.get_tensor(
        out["index"]
    )[0, 0]

    confidence = result[:, 2]

    print(
        "  Max confidence:",
        float(confidence.max())
    )

    print(
        "  Mean confidence:",
        float(confidence.mean())
    )

    best = int(np.argmax(confidence))

    print(
        "  Best keypoint:",
        best,
        "confidence:",
        float(confidence[best]),
        "x:",
        float(result[best, 1]),
        "y:",
        float(result[best, 0])
    )

cap.release()

print("\nDebug test complete.")
