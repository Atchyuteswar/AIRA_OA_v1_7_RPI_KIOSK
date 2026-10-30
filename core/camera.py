"""Camera access with a background capture thread.

Why a thread: OpenCV's ``read()`` blocks and many drivers (DroidCam, MSMF)
queue stale frames, so a UI that spends 30 ms per frame on pose + drawing
falls further and further behind real time. The reader keeps only the *latest*
frame and stamps it at capture time, so every analysis sample carries a true
timestamp and latency never accumulates.

Other fixes over v1.3
* reconnect reopens the *same* device (v1.3 rescanned every index and could
  silently switch cameras mid-assessment; the scan could freeze the UI for
  20 s);
* backends are chosen per operating system;
* frames are returned un-mirrored (mirroring is display-only);
* an optional video file can replace the camera (demo / offline testing).
"""
from __future__ import annotations

import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from core import log as _log
from core.config import CAMERA

_LOG = _log.get("camera")


def _backends() -> list[tuple[str, int]]:
    def cap(name, default=cv2.CAP_ANY):
        return getattr(cv2, name, default)
    if sys.platform.startswith("win"):
        return [("DSHOW", cap("CAP_DSHOW")), ("MSMF", cap("CAP_MSMF")), ("ANY", cv2.CAP_ANY)]
    if sys.platform == "darwin":
        return [("AVFOUNDATION", cap("CAP_AVFOUNDATION")), ("ANY", cv2.CAP_ANY)]
    return [("V4L2", cap("CAP_V4L2")), ("ANY", cv2.CAP_ANY)]


@dataclass
class CameraInfo:
    index: int | str
    name: str
    backend: str
    width: int = 0
    height: int = 0
    fps: float = 0.0
    readable: bool = False
    stable_frames: int = 0
    error: str = ""

    @property
    def resolution(self) -> str:
        return f"{self.width}x{self.height}" if self.width and self.height else "Unknown"


@dataclass
class Packet:
    image: np.ndarray        # BGR, NOT mirrored
    t: float                 # time.perf_counter() at capture
    seq: int


class CameraManager:
    def __init__(self, source: int | str | None = None):
        self.source = source
        self.cap: cv2.VideoCapture | None = None
        self.info: CameraInfo | None = None
        self._backend_flag = cv2.CAP_ANY
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._cond = threading.Condition()
        self._packet: Packet | None = None
        self._seq_seen = 0
        self.frames = 0
        self.dropped = 0
        self.consecutive_failures = 0
        self.lost = False
        self.ended = False               # video file finished
        self._fps_window: list[float] = []

    # ------------------------------------------------------------- opening
    @property
    def is_file(self) -> bool:
        return isinstance(self.source, (str, Path))

    def _probe(self, index, name: str, flag: int) -> tuple[cv2.VideoCapture, CameraInfo] | None:
        cap = cv2.VideoCapture(index, flag) if not self.is_file else cv2.VideoCapture(str(index))
        if not cap.isOpened():
            cap.release()
            return None
        if not self.is_file:
            # Force USB webcam to use MJPEG so 1280x720 can run at 30 FPS.
            try:
                cap.set(
                    cv2.CAP_PROP_FOURCC,
                    cv2.VideoWriter_fourcc(*"MJPG"),
                )
            except Exception:
                pass
            # Apply the camera profile in a deterministic order. MJPEG must be
            # selected before the high-resolution/FPS request on many USB webcams.
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAMERA.requested_width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAMERA.requested_height)
            cap.set(cv2.CAP_PROP_FPS, CAMERA.requested_fps)
            try:
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            except Exception:                                   # noqa: BLE001 - driver specific
                pass
            # A second FPS request after the format negotiation helps V4L2
            # drivers that reset frame interval when the size is accepted.
            cap.set(cv2.CAP_PROP_FPS, CAMERA.requested_fps)
        stable = 0
        for _ in range(CAMERA.warmup_frames):
            ok, frame = cap.read()
            if ok and frame is not None and frame.size:
                stable += 1
            elif self.is_file:
                break
            time.sleep(0.01)
        if stable < (1 if self.is_file else 3):
            cap.release()
            return None
        if self.is_file:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        info = CameraInfo(
            index=index, name=Path(str(index)).name if self.is_file else f"Camera {index}",
            backend="FILE" if self.is_file else name,
            width=int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), height=int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
            fps=float(cap.get(cv2.CAP_PROP_FPS) or 0.0), readable=True, stable_frames=stable)
        return cap, info

    def _open_index(self, index) -> tuple[cv2.VideoCapture, CameraInfo, int] | None:
        if self.is_file:
            r = self._probe(index, "FILE", cv2.CAP_ANY)
            return (*r, cv2.CAP_ANY) if r else None
        for name, flag in _backends():
            r = self._probe(index, name, flag)
            if r:
                return (*r, flag)
        return None

    def discover(self) -> list[CameraInfo]:
        found: list[CameraInfo] = []
        misses = 0
        _LOG.info("Scanning cameras...")
        for index in range(CAMERA.max_scan_index + 1):
            r = self._open_index(index)
            if r is None:
                misses += 1
                if found and misses >= 2:      # devices are contiguous in practice
                    break
                continue
            misses = 0
            cap, info, _ = r
            cap.release()
            found.append(info)
            _LOG.info("Camera %s via %s %s @ %.0f fps", info.index, info.backend, info.resolution, info.fps)
        return found

    @staticmethod
    def _score(info: CameraInfo) -> float:
        return (1000 if info.readable else 0) + (35 if info.backend in ("DSHOW", "V4L2", "AVFOUNDATION") else 0) \
            + min(info.stable_frames, CAMERA.warmup_frames) * 10 \
            + min(info.width * info.height / 1_000_000, 4) * 100 + min(info.fps, 60)

    def open(self, index: int | str | None = None) -> CameraInfo | None:
        """Open ``index``; with no argument use the constructor source or auto-select."""
        self.close()
        index = self.source if index is None else index
        if index is None:
            cams = self.discover()
            if not cams:
                return None
            index = max(cams, key=self._score).index
        self.source = index
        r = self._open_index(index)
        if r is None:
            return None
        self.cap, self.info, self._backend_flag = r
        self.frames = self.dropped = self.consecutive_failures = 0
        self.lost = self.ended = False
        self._stop.clear()
        self._packet, self._seq_seen = None, 0
        self._thread = threading.Thread(target=self._reader, name="aira-camera", daemon=True)
        self._thread.start()
        _LOG.info("Opened %s (%s, %s, %.1f fps)", self.info.name, self.info.backend,
                  self.info.resolution, self.info.fps)
        return self.info

    # ------------------------------------------------------------- reading
    def _reader(self) -> None:
        cap = self.cap
        period = 1.0 / (self.info.fps if self.is_file and self.info and self.info.fps > 1 else 30.0)
        seq = 0
        next_due = time.perf_counter()
        while not self._stop.is_set() and cap is not None:
            ok, frame = cap.read()
            if not ok or frame is None or not frame.size:
                if self.is_file:
                    self.ended = self.lost = True
                    with self._cond:
                        self._cond.notify_all()
                    return
                self.dropped += 1
                self.consecutive_failures += 1
                if self.consecutive_failures >= CAMERA.max_read_failures:
                    self.lost = True
                    with self._cond:
                        self._packet = None
                        self._cond.notify_all()
                    return
                time.sleep(0.01)
                continue
            self.consecutive_failures = 0
            if CAMERA.source_is_mirrored:
                frame = cv2.flip(frame, 1)                      # undo driver mirroring
            seq += 1
            now = time.perf_counter()
            with self._cond:
                self._packet = Packet(frame, now, seq)
                self.frames += 1
                self._fps_window = (self._fps_window + [now])[-30:]
                self._cond.notify_all()
            if self.is_file:                                   # emulate real time for video files
                next_due += period
                time.sleep(max(0.0, next_due - time.perf_counter()))

    def read(self, timeout: float = 0.25) -> Packet | None:
        """Newest frame not returned before, or None on timeout / lost camera."""
        deadline = time.perf_counter() + timeout
        with self._cond:
            while not self.lost or self._packet is not None:
                if self._packet is not None and self._packet.seq != self._seq_seen:
                    self._seq_seen = self._packet.seq
                    return self._packet
                remaining = deadline - time.perf_counter()
                if remaining <= 0 or self.lost:
                    break
                self._cond.wait(remaining)
        return None

    @property
    def measured_fps(self) -> float:
        w = self._fps_window
        return (len(w) - 1) / (w[-1] - w[0]) if len(w) > 2 and w[-1] > w[0] else 0.0

    # ------------------------------------------------------------ lifecycle
    def health(self) -> dict:
        return {
            "connected": bool(self.cap is not None and not self.lost),
            "camera_index": self.source if not self.is_file else str(self.source),
            "camera_name": self.name, "backend": self.backend,
            "width": self.width, "height": self.height, "fps": self.fps,
            "measured_fps": round(self.measured_fps, 1),
            "frames": self.frames, "dropped_frames": self.dropped,
            "consecutive_failures": self.consecutive_failures,
            "drop_ratio": self.dropped / max(self.frames + self.dropped, 1),
            "mirrored_source": CAMERA.source_is_mirrored,
            "target_width": CAMERA.requested_width,
            "target_height": CAMERA.requested_height,
            "target_fps": CAMERA.requested_fps,
            "profile_ok": bool(
                self.width >= CAMERA.minimum_acceptable_width
                and self.height >= CAMERA.minimum_acceptable_height
                and self.fps >= CAMERA.minimum_acceptable_fps
            ),
        }

    def reconnect(self) -> bool:
        """Reopen the same device (never a different one)."""
        source = self.source
        for attempt in range(CAMERA.reconnect_attempts):
            self._shutdown()
            time.sleep(0.4 * (attempt + 1))
            if self.open(source):
                return True
        return False

    def _shutdown(self) -> None:
        self._stop.set()
        t = self._thread
        if t is not None and t.is_alive() and t is not threading.current_thread():
            t.join(timeout=1.5)
        if self.cap is not None:
            self.cap.release()
        self.cap, self._thread = None, None

    def close(self) -> None:
        self._shutdown()
        self.info = None
        self._packet = None

    @property
    def width(self): return self.info.width if self.info else 0
    @property
    def height(self): return self.info.height if self.info else 0
    @property
    def fps(self): return self.info.fps if self.info else 0.0
    @property
    def name(self): return self.info.name if self.info else "No camera"
    @property
    def backend(self): return self.info.backend if self.info else "None"
