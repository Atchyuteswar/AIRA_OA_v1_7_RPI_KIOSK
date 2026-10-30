"""Headless end-to-end smoke test of the whole application flow.

Runs the real UI/camera/session code with a *synthetic* pose source (MediaPipe
is replaced by a scripted skeleton) and a generated video, drives it with
scripted key presses, and checks the saved records. Needs a display; on a
headless Linux box run:   xvfb-run -a python tools/e2e_smoke.py
"""
from __future__ import annotations

import dataclasses
import math
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ["AIRA_DATA_DIR"] = tempfile.mkdtemp(prefix="aira_e2e_")

import cv2
import numpy as np

import challenges.balance as balance_mod
from core import config, flow
from core.pose import PoseFrame

# shorten the balance test so the smoke test runs in ~1 minute
balance_mod.CFG = dataclasses.replace(config.BALANCE, duration_seconds=4.0, settle_seconds=0.5, min_analysed_seconds=2.5)


def make_video(path: str, seconds=90, fps=30):
    vw = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"mp4v"), fps, (640, 480))
    rng = np.random.default_rng(0)
    base = rng.integers(90, 170, (480, 640, 3), dtype=np.uint8)
    for i in range(seconds * fps):
        vw.write(np.roll(base, i % 640, axis=1))
    vw.release()


class FakePose:
    """Scripted skeleton whose motion depends on the challenge being shown."""
    mode = "idle"

    def __enter__(self): return self
    def __exit__(self, *a): return False

    def process(self, bgr, t):
        h, w = bgr.shape[:2]
        lm = np.zeros((33, 4)); lm[:, 3] = 0.95
        pts = {11: (.45, .25), 12: (.55, .25), 23: (.46, .5), 24: (.54, .5), 25: (.46, .7), 26: (.54, .7),
               27: (.46, .9), 28: (.54, .9)}
        for i, (x, y) in pts.items():
            lm[i, :2] = (x, y)
        theta_l = theta_r = 170.0
        torso_px = 0.25 * h
        if self.mode == "sit_to_stand":
            ph = (t % 2.0) / 2.0
            if ph < 0.4:
                f = 0.5 * (1 - math.cos(math.pi * ph / 0.4))          # sit down
            elif ph < 0.6:
                f = 1.0                                               # seated
            else:
                f = 0.5 * (1 + math.cos(math.pi * (ph - 0.6) / 0.4))  # stand up
            th = 170 - 75 * f
            theta_l, theta_r = th, th * 0.96
        elif self.mode == "gait":
            s = 0.35 * math.sin(2 * math.pi * 0.9 * t) * torso_px / w
            lm[27, 0] = 0.5 + s / 2; lm[28, 0] = 0.5 - s / 2
            for i in (11, 12, 23, 24, 25, 26):
                lm[i, 0] += -0.2 + 0.06 * (t % 6.0)                 # walking across the frame
            theta_l = 150 + 15 * math.sin(2 * math.pi * 0.9 * t)
            theta_r = 150 - 15 * math.sin(2 * math.pi * 0.9 * t)
        elif self.mode == "balance":
            lm[23:25, 0] += 0.004 * math.sin(2 * math.pi * 0.4 * t)
        world = np.zeros((33, 3))
        for hip, knee, ankle, th in ((23, 25, 27, theta_l), (24, 26, 28, theta_r)):
            world[knee] = (0, 0.45, 0)
            a = math.radians(th)
            world[ankle] = (0.45 * math.sin(a), 0.45 - 0.45 * math.cos(a), 0)
        return PoseFrame(t=t, lm=lm, width=w, height=h, world=world)


T0 = time.perf_counter()


class Script:
    """Injects key presses according to which screen is active."""
    def __init__(self, display):
        self.d, self.screen, self.t0, self.sent = display, "none", time.perf_counter(), 0
        self.log = []
        orig = display.poll_key
        def poll():
            k = orig()
            if k != -1:
                return k
            return self.policy()
        display.poll_key = poll

    def enter(self, name):
        self.screen, self.t0, self.sent = name, time.perf_counter(), 0
        self.log.append(name)
        print(f"[{time.perf_counter() - T0:6.1f}s] screen={name} mode={FakePose.mode}", flush=True)

    def policy(self):
        dt = time.perf_counter() - self.t0
        s = self.screen
        if s == "info" and dt > 0.4: return self._once(13)
        if s == "readiness" and dt > 2.4: return self._once(13)
        if s == "record":
            need = {"sit_to_stand": 10.0, "gait": 7.0, "balance": 99}[FakePose.mode]
            if dt > need: return self._once(13)
        if s == "review" and dt > 0.4: return self._once(13)
        if s == "questionnaire" and dt > 0.08 * (self.sent + 1): self.sent += 1; return ord(str(1 + self.sent % 3))
        if s == "results":
            if dt > 0.5 and self.sent == 0: return self._once(ord("e"))
            if dt > 1.5: return 27
        return -1

    def _once(self, key):
        if self.sent == 0:
            self.sent = 1
            return key
        return -1


def run() -> int:
    from assessment.patients import list_sessions, save_patient
    from core.camera import CameraManager
    from core.display import get_display
    import app

    vid = str(Path(os.environ["AIRA_DATA_DIR"]) / "fake.mp4")
    make_video(vid)
    display = get_display(); display.get_root()
    camera = CameraManager(vid)
    assert camera.open(), "video did not open"
    script = Script(display)

    for name, label in (("info_screen", "info"), ("readiness_screen", "readiness"), ("record_screen", "record"),
                        ("review_screen", "review"), ("questionnaire_screen", "questionnaire"), ("results_screen", "results")):
        orig = getattr(flow, name)
        def wrap(*a, _o=orig, _l=label, **k):
            script.enter(_l)
            if _l == "readiness":
                FakePose.mode = a[1]
            if _l == "record":
                script.enter("record")
            return _o(*a, **k)
        setattr(flow, name, wrap)
    # review keeps "record" mode text; nothing else to patch

    rt = flow.Runtime(camera, FakePose(), display)
    patient = save_patient({"name": "Smoke Test", "age": 61, "consent": True, "sex": "Female"})
    failures = []
    for n in (1, 2):
        # a second assessment for the same patient exercises baseline comparison
        out = app.run_assessment(rt, patient)
        print(f"assessment {n}: outcome={out}")
        if out not in ("home", "new"):
            failures.append(f"unexpected outcome {out}")
    camera.close()

    sessions = sorted(list_sessions(patient["patient_id"]), key=lambda s: s["started_at_epoch"])
    print("saved sessions:", len(sessions))
    if len(sessions) != 2:
        failures.append("expected 2 saved sessions")
    for s in sessions:
        q = s["assessment_quality"]
        sts, gait, bal = s["sit_to_stand"], s["gait"], s["balance"]
        print(f" {s['assessment_id']} quality={q['overall_status']} "
              f"STS valid={sts.get('valid_repetitions')}/{sts.get('repetitions')} gate={sts['quality_gate']['status']} "
              f"gait steps={gait.get('total_steps')} cad={gait.get('cadence_steps_per_minute')} gate={gait['quality_gate']['status']} "
              f"balance rms={bal.get('sway_rms')} gate={bal['quality_gate']['status']}")
        for name, blk in (("sts", sts), ("gait", gait), ("balance", bal)):
            if not blk["quality_gate"]["passed"]:
                failures.append(f"{name} gate failed: {blk['quality_gate']['reasons']}")
        if not (4 <= sts.get("valid_repetitions", 0) <= 6):
            failures.append(f"STS reps {sts.get('valid_repetitions')} (expected ~5)")
        if not (abs(gait.get("cadence_steps_per_minute", 0) - 108) < 15):
            failures.append(f"gait cadence {gait.get('cadence_steps_per_minute')} (expected ~108)")
    if sessions:
        cmp_ = sessions[-1]["personalized_baseline"]
        print("second session baseline status:", cmp_["status"], "metrics compared:", len(cmp_["changes"]))
        if cmp_["status"] != "COMPARED":
            failures.append("second session did not compare with baseline")
    rep = list((Path(os.environ["AIRA_DATA_DIR"]) / "reports").glob("*.html"))
    print("reports exported:", len(rep))
    if not rep:
        failures.append("no report exported")
    display.close()
    print("\nFAILURES:" if failures else "\nALL CHECKS PASSED")
    for f in failures:
        print(" -", f)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(run())
