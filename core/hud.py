"""Heads-up display drawn with OpenCV on a fixed 1280x720 canvas.

v1.3 drew at hard-coded pixel positions on whatever size the camera produced,
so the layout broke on 640x480 cameras and every translucent panel copied the
whole 1080p frame (a dozen full-frame copies per frame). Here every screen is
composed on one canvas and panels only blend their own rectangle.
"""
from __future__ import annotations

import os
import unicodedata
from dataclasses import dataclass
from functools import lru_cache

import cv2
import numpy as np

from core.config import DISPLAY
from core.pose import L_ANKLE, L_HIP, L_KNEE, PoseFrame, SKELETON

W, H = DISPLAY.canvas_width, DISPLAY.canvas_height
# Touch kiosk: the controls live on the Tk touch bar, so the in-canvas footer only
# carries a one-line message and keyboard hints are dropped.
TOUCH_MODE = os.environ.get("AIRA_RPI_TOUCH", os.environ.get("AIRA_RPI", "0")) == "1"
COMPACT = H <= 620
HEADER_H = 62 if COMPACT else 78
FOOTER_H = 40 if TOUCH_MODE else (56 if COMPACT else 62)
FONT = cv2.FONT_HERSHEY_SIMPLEX

# BGR palette
INK = (250, 244, 238)
MUTED = (190, 168, 152)
PANEL = (45, 26, 18)
PANEL_HI = (66, 44, 30)
EDGE = (92, 66, 46)
ACCENT = (255, 216, 98)
GOOD = (167, 230, 98)
WARN = (102, 204, 255)
BAD = (138, 123, 255)

_MAP = str.maketrans({"✓": "OK", "✔": "OK", "○": "o", "●": "*", "•": "|", "—": "-", "–": "-",
                      "−": "-", "×": "x", "≤": "<=", "≥": ">=", "→": "->", "←": "<-", "°": " deg",
                      "“": '"', "”": '"', "‘": "'", "’": "'", "Ⅱ": "||", "…": "..."})


def ascii_safe(value) -> str:
    """OpenCV's Hershey fonts are ASCII-only; anything else prints as '???'."""
    s = str(value).translate(_MAP)
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")


# ------------------------------------------------------------ canvas glue
@dataclass
class Transform:
    scale: float
    ox: int
    oy: int
    fw: int
    fh: int
    mirror: bool

    def to_canvas(self, x: float, y: float) -> tuple[int, int]:
        if self.mirror:
            x = 1.0 - x
        return int(self.ox + x * self.fw * self.scale), int(self.oy + y * self.fh * self.scale)


def compose(frame: np.ndarray | None, mirror: bool = DISPLAY.mirror_preview,
            dim: float = 1.0) -> tuple[np.ndarray, Transform | None]:
    """Letter-box a camera frame onto the fixed canvas (display-only mirroring)."""
    canvas = np.full((H, W, 3), (22, 14, 10), np.uint8)
    if frame is None:
        return canvas, None
    fh, fw = frame.shape[:2]
    scale = min(W / fw, H / fh)
    nw, nh = max(2, int(fw * scale)), max(2, int(fh * scale))
    img = cv2.resize(frame, (nw, nh), interpolation=cv2.INTER_AREA if scale < 1 else cv2.INTER_LINEAR)
    if mirror:
        img = cv2.flip(img, 1)
    if dim < 1.0:
        img = (img * dim).astype(np.uint8)
    ox, oy = (W - nw) // 2, (H - nh) // 2
    canvas[oy:oy + nh, ox:ox + nw] = img
    return canvas, Transform(scale, ox, oy, fw, fh, mirror)


def draw_pose(canvas: np.ndarray, pf: PoseFrame | None, tr: Transform | None,
              min_vis: float = 0.35) -> None:
    if pf is None or tr is None:
        return
    pts = {}
    for i in range(33):
        if pf.lm[i, 3] >= min_vis:
            pts[i] = tr.to_canvas(pf.lm[i, 0], pf.lm[i, 1])
    for a, b in SKELETON:
        if a in pts and b in pts:
            cv2.line(canvas, pts[a], pts[b], (245, 240, 235), 3, cv2.LINE_AA)
    for i, p in pts.items():
        # colour codes anatomy: left = accent, right = warm (labels are anatomical, not mirrored)
        left = i % 2 == 1
        centre = (int(p[0]), int(p[1]))
        cv2.circle(canvas, centre, 6, (20, 14, 10), -1, cv2.LINE_AA)
        cv2.circle(canvas, centre, 4, ACCENT if left else WARN, -1, cv2.LINE_AA)


# -------------------------------------------------------------- primitives
@lru_cache(maxsize=96)
def _round_mask(h: int, w: int, r: int) -> np.ndarray:
    m = np.zeros((h, w), np.uint8)
    r = max(0, min(r, h // 2, w // 2))
    if r == 0:
        m[:] = 255
        return m
    cv2.rectangle(m, (r, 0), (w - 1 - r, h - 1), 255, -1)
    cv2.rectangle(m, (0, r), (w - 1, h - 1 - r), 255, -1)
    for cx, cy in ((r, r), (w - 1 - r, r), (r, h - 1 - r), (w - 1 - r, h - 1 - r)):
        cv2.circle(m, (cx, cy), r, 255, -1, cv2.LINE_AA)
    return m


@lru_cache(maxsize=96)
def _edge_mask(h: int, w: int, r: int) -> np.ndarray:
    m = _round_mask(h, w, r)
    padded = cv2.copyMakeBorder(m, 1, 1, 1, 1, cv2.BORDER_CONSTANT, value=0)   # erode would treat the edge as solid
    inner = cv2.erode(padded, np.ones((3, 3), np.uint8))[1:-1, 1:-1]
    return cv2.subtract(m, inner)


def panel(img, x1, y1, x2, y2, alpha=0.80, color=PANEL, radius=10, border=None):
    """Translucent rounded rectangle; only its own rectangle is blended."""
    x1, y1, x2, y2 = int(max(0, x1)), int(max(0, y1)), int(min(W, x2)), int(min(H, y2))
    if x2 - x1 < 2 or y2 - y1 < 2:
        return
    roi = img[y1:y2, x1:x2]
    h, w = roi.shape[:2]
    mask = _round_mask(h, w, radius) > 0
    blended = cv2.addWeighted(np.full_like(roi, color), alpha, roi, 1 - alpha, 0)
    roi[mask] = blended[mask]
    if border is not None:
        roi[_edge_mask(h, w, radius) > 0] = border


def text(img, value, x, y, scale=0.62, color=INK, thickness=1, shadow=True):
    s = ascii_safe(value)
    if shadow:
        cv2.putText(img, s, (int(x) + 1, int(y) + 1), FONT, scale, (0, 0, 0), thickness + 1, cv2.LINE_AA)
    cv2.putText(img, s, (int(x), int(y)), FONT, scale, color, thickness, cv2.LINE_AA)


def text_width(value, scale=0.62, thickness=1) -> int:
    return cv2.getTextSize(ascii_safe(value), FONT, scale, thickness)[0][0]


def text_center(img, value, cx, y, scale=0.62, color=INK, thickness=1):
    text(img, value, int(cx - text_width(value, scale, thickness) / 2), y, scale, color, thickness)


def fit(value, scale: float, max_width: int, thickness: int = 1) -> str:
    """Shorten with an ellipsis so the text never runs off its container."""
    s = ascii_safe(value)
    if text_width(s, scale, thickness) <= max_width:
        return s
    while len(s) > 1 and text_width(s + "...", scale, thickness) > max_width:
        s = s[:-1]
    return s + "..."


def fit_scale(value, max_width: int, start: float, floor: float = 0.45, thickness: int = 1) -> float:
    """Largest font scale (<= start) at which ``value`` fits ``max_width``."""
    sc = start
    while sc > floor and text_width(value, sc, thickness) > max_width:
        sc -= 0.04
    return max(sc, floor)


def wrap(value: str, scale: float, max_width: int, thickness: int = 1) -> list[str]:
    words, lines, cur = ascii_safe(value).split(), [], ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if text_width(trial, scale, thickness) <= max_width or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def progress_bar(img, x, y, w, frac, tone=ACCENT, h=10):
    x, y, w, h = int(x), int(y), int(w), int(h)
    r = h // 2
    panel(img, x, y, x + w, y + h, 1.0, (70, 58, 50), radius=r)
    fw = int(w * max(0.0, min(1.0, frac)))
    if fw >= 2:
        panel(img, x, y, x + max(fw, h), y + h, 1.0, tone, radius=r)


def header(img, title: str, step: int, total: int, right: str = ""):
    """Product identity (left), workflow progress and capture status (right)."""
    panel(img, 0, 0, W, HEADER_H, 0.95, radius=0)
    cv2.rectangle(img, (0, HEADER_H - 2), (W, HEADER_H), (110, 78, 42), -1)
    text(img, "AIRA-OA", 20, 30, 0.9, INK, 2)
    text(img, fit(title, 0.52, W - 340), 22, HEADER_H - 12, 0.52, ACCENT, 1)
    bw = 200
    x0 = W - bw - 22
    text(img, f"STEP {step} OF {total}", x0, 22, 0.46, INK, 1)
    progress_bar(img, x0, 29, bw, step / max(total, 1), ACCENT, 6)
    if right:
        cv2.circle(img, (x0 + 5, HEADER_H - 17), 4, GOOD, -1, cv2.LINE_AA)
        text(img, fit(right, 0.42, bw - 16), x0 + 16, HEADER_H - 12, 0.42, MUTED)


def footer(img, message: str, controls: str = ""):
    panel(img, 0, H - FOOTER_H, W, H, 0.96, radius=0)
    cv2.rectangle(img, (0, H - FOOTER_H), (W, H - FOOTER_H + 2), (110, 78, 42), -1)
    show_controls = controls and not TOUCH_MODE
    room = W - 56 - (text_width(controls, 0.42) + 24 if show_controls else 0)
    text(img, fit(message, 0.52, room), 24, H - FOOTER_H // 2 + 7, 0.52, INK)
    if show_controls:
        text(img, controls, W - text_width(controls, 0.42) - 24, H - FOOTER_H // 2 + 6, 0.42, MUTED)


def card(img, x, y, w, label, value, tone=INK, h=82):
    panel(img, x, y, x + w, y + h, 0.88, border=EDGE)
    if tone != INK:
        cv2.rectangle(img, (int(x) + 1, int(y) + 14), (int(x) + 4, int(y) + h - 14), tone, -1)
    text(img, label, x + 14, y + 24, 0.42, MUTED)
    val = str(value)
    sc = fit_scale(val, w - 26, 0.95 if h >= 80 else 0.85, 0.5, 2)
    text(img, val, x + 14, y + h - 16, sc, tone, 2)


def cards(img, items, y=HEADER_H + 10, x=16, w=200, gap=10):
    n = max(1, len(items))
    avail = W - 2 * x
    gap = max(8, min(gap, 12))
    w = max(120, int((avail - gap * (n - 1)) / n))
    for k, (label, value, *rest) in enumerate(items):
        card(img, x + k * (w + gap), y, w, label, value, rest[0] if rest else INK, 74 if COMPACT else 92)


def chip(img, label, x, y, tone=INK):
    """Pill with a coloured dot; ``y`` is the text baseline. Returns its width."""
    label = ascii_safe(label)
    w = text_width(label, 0.5, 1) + 38
    panel(img, x, y - 22, x + w, y + 10, 0.9, color=(34, 22, 15), radius=16, border=EDGE)
    cv2.circle(img, (int(x) + 16, int(y) - 6), 5, tone, -1, cv2.LINE_AA)
    text(img, label, x + 28, y, 0.5, INK)
    return w


def message_box(img, title: str, lines: list[str], tone=INK, width=760, top=None):
    width = min(width, W - 48)
    scale = 0.54 if COMPACT else 0.58
    line_h = 25 if COMPACT else 30
    body = []
    for ln in lines:
        body += wrap(ln, scale, width - 64) if ln else [""]
    avail = H - HEADER_H - FOOTER_H - 28
    max_body = max(3, int((avail - 76) / line_h))
    if len(body) > max_body:
        body = body[:max_body - 1] + ["... tap Repeat to run the test again, or Details later for the full record"]
    h = min(avail, 76 + line_h * len(body))
    x1 = (W - width) // 2
    y1 = top if top is not None else HEADER_H + 14 + max(0, (avail - h) // 2)
    panel(img, x1, y1, x1 + width, y1 + h, 0.94, border=EDGE)
    cv2.rectangle(img, (x1 + 1, y1 + 16), (x1 + 5, y1 + h - 16), tone, -1)
    text(img, title, x1 + 28, y1 + 42, 0.8 if COMPACT else 0.9, tone, 2)
    y = y1 + 76
    for ln in body:
        text(img, ln, x1 + 28, y, scale, INK)
        y += line_h


def big_count(img, value, sub=""):
    cx, cy = W // 2, (HEADER_H + H - FOOTER_H) // 2
    panel(img, cx - 150, cy - 130, cx + 150, cy + 110, 0.9, border=EDGE)
    text_center(img, value, cx, cy + 25, 4.0, ACCENT, 8)
    if sub:
        text_center(img, sub, cx, cy + 82, 0.62, INK)


def leg_hint(img, pf, tr):     # tiny helper used by readiness overlay
    if pf is None or tr is None:
        return
    for i in (L_HIP, L_KNEE, L_ANKLE):
        if pf.lm[i, 3] > 0.35:
            cv2.circle(img, tr.to_canvas(pf.lm[i, 0], pf.lm[i, 1]), 9, ACCENT, 2, cv2.LINE_AA)
