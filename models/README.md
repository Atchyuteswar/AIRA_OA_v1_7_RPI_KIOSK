# MoveNet model

The Raspberry Pi build uses **MoveNet SinglePose Lightning** with a 192x192
input and TensorFlow Lite/LiteRT runtime.

Expected filename:

`movenet_lightning.tflite`

The installer attempts to download the model from TensorFlow Hub. If the Pi is
offline, copy the model into this directory or set `AIRA_POSE_MODEL` to its
absolute path.

The pose backend converts MoveNet's 17 keypoints into the existing AIRA-OA
`PoseFrame` contract. It does not provide metric world landmarks, so knee-angle
features use the image-plane geometry fallback on the Pi.
