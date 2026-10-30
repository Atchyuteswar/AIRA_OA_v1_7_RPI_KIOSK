"""Camera-driven screens: setup, readiness, recording, review, questionnaire,
results. All loops share one ``Runtime`` so pose/camera/display are wired once.

Return codes from every screen: "next", "back", "skip", "home", "quit".
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

from assessment.questionnaire import QUESTIONS, Questionnaire
from challenges.balance import Balance
from challenges.base import Challenge
from challenges.gait import Gait
from challenges.sit_to_stand import SitToStand
from core import hud, log as _log
from core.camera import CameraManager
from core.display import KEY_BACKSPACE, KEY_ENTER, KEY_ESC, KEY_HOME, KEY_QUIT_WINDOW, KEY_SPACE, Display
from core.pose import PoseEstimator, PoseFrame, REQUIRED
from core.quality import PASS, SKIPPED
from core.readiness import ReadinessGate

_LOG = _log.get("flow")
TOTAL_STEPS = 6
COUNTDOWN_SECONDS = 3
ENTER_KEYS = (KEY_ENTER, 10, KEY_SPACE)
Q = ord("q")
INSTRUCTION_SECONDS = 8.0        # full instructions are shown this long, then a small label


@dataclass
class Runtime:
    camera: CameraManager
    pose: PoseEstimator
    display: Display
    debug: bool = False
    last_error: str | None = field(default=None, init=False)
    last_error_context: str | None = field(default=None, init=False)

    def frame(self, pose_needed: bool = True):
        """Next (packet, PoseFrame|None), with bounded recovery for bad frames.

        A single native/TFLite/OpenCV failure must not tear down the whole kiosk.
        The runtime retries pose inference on a fresh frame before surfacing the
        failure to the assessment boundary, where the operator gets a useful
        technical message and the partial session can be preserved.
        """
        self.last_error = None
        self.last_error_context = None
        pose_attempts = 0
        for _ in range(3):
            pkt = self.camera.read(0.5)
            if pkt is not None:
                if not pose_needed:
                    return pkt, None
                try:
                    pf = self.pose.process(pkt.image, pkt.t)
                    return pkt, pf
                except Exception as exc:  # noqa: BLE001 - native inference can fail transiently
                    pose_attempts += 1
                    self.last_error = f"{type(exc).__name__}: {exc}"
                    self.last_error_context = "pose inference"
                    _LOG.exception("Pose inference failed (attempt %s/3)", pose_attempts)
                    time.sleep(0.03)
                    continue
            if self.camera.ended:
                self.last_error = "Camera/video source ended"
                self.last_error_context = "camera"
                return None, None
            if self.camera.lost:
                _LOG.warning("camera lost; reconnecting")
                if not self.camera.reconnect():
                    self.last_error = "Camera reconnect failed"
                    self.last_error_context = "camera"
                    return None, None
        return None, None

    def key(self) -> int:
        return self.display.poll_key()


def _global_key(k: int) -> str | None:
    if k == KEY_QUIT_WINDOW or k == Q:
        return "quit"
    if k == KEY_HOME:
        return "home"
    return None


def _cam_text(rt: Runtime) -> str:
    return f"{rt.camera.width}x{rt.camera.height}  {rt.camera.measured_fps:.0f} fps"


def _frame_failure(rt: Runtime) -> str:
    return "pose_error" if rt.last_error_context == "pose inference" else "camera_error"


def _touch(rt: Runtime, actions):
    """Configure large touchscreen controls for the active camera screen."""
    rt.display.set_touch_actions(actions)


def _debug_overlay(rt: Runtime, canvas, extra=""):
    if not rt.debug:
        return
    h = rt.camera.health()
    hud.panel(canvas, 24, 100, 470, 176, 0.85)
    hud.text(canvas, f"{h['camera_name']} | {h['backend']} | {h['measured_fps']} fps", 34, 124, 0.4, hud.MUTED)
    hud.text(canvas, f"dropped {h['dropped_frames']} ({h['drop_ratio']*100:.1f}%)  {extra}", 34, 148, 0.4, hud.MUTED)


# ------------------------------------------------------------------ info
def info_screen(rt: Runtime, title: str, lines: list[str], step: int,
                controls="ENTER Continue   ESC Back   Q Quit"):
    """Professional assessment-introduction screen with a clear workflow."""
    rt.display.enter_camera_mode()
    _touch(rt, [("Home", KEY_HOME), ("Back", KEY_ESC), ("Continue", KEY_ENTER)])
    while True:
        pkt, _ = rt.frame(pose_needed=False)
        if pkt is None:
            return _frame_failure(rt)
        canvas, _ = hud.compose(pkt.image, dim=0.30)
        hud.header(canvas, title, step, TOTAL_STEPS, _cam_text(rt))

        # Main information card
        x1, x2 = 40, hud.W - 40
        y1, y2 = hud.HEADER_H + 14, hud.H - hud.FOOTER_H - 14
        hud.panel(canvas, x1, y1, x2, y2, 0.94, border=hud.EDGE)
        hud.text(canvas, "ASSESSMENT OVERVIEW", x1 + 30, y1 + 38, 0.5, hud.ACCENT, 2)

        y = y1 + 76
        for ln in lines:
            if not ln:
                y += 8
                continue
            tone = hud.GOOD if ln.startswith("Patient:") else hud.WARN if "Place a chair" in ln else hud.INK
            for part in hud.wrap(ln, 0.58, (x2 - x1) - 70):
                hud.text(canvas, part, x1 + 32, y, 0.58, tone, 2 if tone == hud.GOOD else 1)
                y += 29
            y += 3

        hud.chip(canvas, "CAMERA  " + _cam_text(rt), x1 + 30, y2 - 18, hud.GOOD)
        hud.footer(canvas, "Review the setup, then begin when the participant is ready.",
                   "ENTER Continue   ESC Back   Q Quit")
        rt.display.show(canvas)

        k = rt.key()
        global_action = _global_key(k)
        if global_action:
            return global_action
        if k in ENTER_KEYS:
            return "next"
        if k == KEY_ESC:
            return "back"


# ------------------------------------------------------------- readiness
def readiness_screen(rt: Runtime, challenge: str, title: str, step: int) -> str:
    """Returns "ready", "skip", "back", "quit" or "camera_error"."""
    rt.display.enter_camera_mode()
    _touch(rt, [("Home", KEY_HOME), ("Back", KEY_ESC), ("Skip", ord("s")), ("Start", KEY_ENTER)])
    gate = ReadinessGate(challenge)
    labels = (("person", "PERSON DETECTED"), ("landmarks", "JOINTS VISIBLE"), ("framing", "BODY IN FRAME"),
              ("lighting", "LIGHTING"), ("sharpness", "IMAGE SHARPNESS"))
    while True:
        pkt, pf = rt.frame()
        if pkt is None:
            return _frame_failure(rt)
        s = gate.update(pf, pkt.image, pkt.t)
        canvas, tr = hud.compose(pkt.image)
        hud.draw_pose(canvas, pf, tr)
        if s["bbox"] and tr:
            x1, y1, x2, y2 = s["bbox"]
            p1, p2 = tr.to_canvas(x1, y1), tr.to_canvas(x2, y2)
            tone = hud.GOOD if s["ok"] else hud.WARN
            hud.cv2.rectangle(canvas, (min(p1[0], p2[0]), p1[1]), (max(p1[0], p2[0]), p2[1]), tone, 2)
        hud.header(canvas, f"Get ready - {title}", step, TOTAL_STEPS, _cam_text(rt))
        top = hud.HEADER_H + 12
        row_h = 38
        box_h = 48 + row_h * len(labels) + 24
        hud.panel(canvas, 16, top, 306, top + box_h, 0.86, border=hud.EDGE)
        hud.text(canvas, "CHECKLIST", 32, top + 30, 0.46, hud.MUTED)
        for n, (key, label) in enumerate(labels):
            ok = s["checks"][key]
            y = top + 48 + n * row_h + 14
            hud.cv2.circle(canvas, (38, y - 6), 8, hud.GOOD if ok else hud.BAD, -1, hud.cv2.LINE_AA)
            hud.text(canvas, label, 58, y, 0.55, hud.INK if ok else hud.MUTED)
        hud.progress_bar(canvas, 32, top + box_h - 20, 258,
                         s["held"] / s["hold_seconds"], hud.GOOD if s["ready"] else hud.ACCENT, 8)
        tone = hud.GOOD if s["ready"] else hud.WARN
        bar_y = hud.H - hud.FOOTER_H - 62
        hud.panel(canvas, hud.W // 2 - 320, bar_y, hud.W // 2 + 320, bar_y + 48, 0.9, border=hud.EDGE)
        ready_text = "READY - tap START" if hud.TOUCH_MODE else "READY - press ENTER to start"
        msg = ready_text if s["ready"] else s["message"]
        hud.text_center(canvas, hud.fit(msg, 0.66, 600, 2), hud.W // 2, bar_y + 32, 0.66, tone, 2)
        _debug_overlay(rt, canvas, f"vis {s['visibility']:.2f}")
        hud.footer(canvas, f"Positioning for {title.lower()}.", "ENTER Start   S Skip   D Debug   ESC Back   Q Quit")
        rt.display.show(canvas)
        k = rt.key()
        global_action = _global_key(k)
        if global_action:
            return global_action
        if k == ord("d"):
            rt.debug = not rt.debug
        elif k == KEY_ESC:
            return "back"
        elif k == ord("s"):
            return "skip"
        elif k in ENTER_KEYS and s["ready"]:
            return countdown(rt, challenge, step)


def countdown(rt: Runtime, challenge: str, step: int) -> str:
    _touch(rt, [("Back", KEY_ESC), ("Cancel", KEY_HOME)])
    end = time.perf_counter() + COUNTDOWN_SECONDS
    while time.perf_counter() < end:
        pkt, pf = rt.frame()
        if pkt is None:
            return _frame_failure(rt)
        canvas, tr = hud.compose(pkt.image)
        hud.draw_pose(canvas, pf, tr)
        hud.header(canvas, "Starting", step, TOTAL_STEPS, _cam_text(rt))
        hud.big_count(canvas, str(int(end - time.perf_counter()) + 1), "Keep your position")
        hud.footer(canvas, "Recording begins automatically.", "ESC Cancel")
        rt.display.show(canvas)
        k = rt.key()
        global_action = _global_key(k)
        if global_action:
            return global_action
        if k == KEY_ESC:
            return "back"
    return "ready"


# ------------------------------------------------------------- recording
def _hud_cards(ch: Challenge, live: dict, now: float):
    if ch.key == "sit_to_stand":
        return [("REPETITIONS", live["repetitions"], hud.GOOD), ("LEFT ROM", f"{live['left_rom']:.0f} deg"),
                ("RIGHT ROM", f"{live['right_rom']:.0f} deg"), ("STATE", live["state"]),
                ("TRACKING", f"{live['quality']*100:.0f}%")]
    if ch.key == "gait":
        return [("STEPS", live["steps"], hud.GOOD), ("CADENCE /MIN", f"{live['cadence']:.0f}"),
                ("LEFT", live["left"]), ("RIGHT", live["right"]), ("TRACKING", f"{live['quality']*100:.0f}%")]
    remaining = max(0.0, live["target"] - live["elapsed"])
    return [("TIME LEFT", f"{remaining:.1f}s", hud.ACCENT), ("PHASE", "SETTLE" if live["settling"] else "MEASURING"),
            ("VALID FRAMES", live["valid"]), ("TRACKING", f"{live['quality']*100:.0f}%")]


def record_screen(rt: Runtime, ch: Challenge, step: int, controls: str) -> tuple[str, dict | None]:
    """Record until finished. Returns (code, result_block|None)."""
    ch.start(time.perf_counter())
    _touch(rt, [("Home", KEY_HOME), ("Back", KEY_ESC), ("Pause", ord("p")), ("Restart", ord("r")), ("Finish", KEY_ENTER)])
    paused, paused_at, paused_total = False, 0.0, 0.0
    last_t = time.perf_counter()
    rec_started = time.perf_counter()
    while True:
        pkt, pf = rt.frame()
        if pkt is None:
            return _frame_failure(rt), None
        t = pkt.t - paused_total
        last_t = pkt.t
        if not paused:
            ch.update(pf, t)
        live = ch.live()
        canvas, tr = hud.compose(pkt.image)
        hud.draw_pose(canvas, pf, tr)
        hud.header(canvas, f"{step-1:02d} | {ch.title}", step, TOTAL_STEPS, _cam_text(rt))
        hud.cards(canvas, _hud_cards(ch, live, t))
        top = hud.HEADER_H + 10 + (74 if hud.COMPACT else 92) + 12
        if ch.instructions and time.perf_counter() - rec_started < INSTRUCTION_SECONDS:
            bw = 480
            hud.panel(canvas, 16, top, 16 + bw, top + 46 + 27 * len(ch.instructions), 0.84, border=hud.EDGE)
            hud.text(canvas, ch.title.upper(), 34, top + 31, 0.64, hud.ACCENT, 2)
            for n, ln in enumerate(ch.instructions):
                hud.text(canvas, hud.fit(ln, 0.52, bw - 36), 34, top + 62 + n * 27, 0.52, hud.INK)
        else:
            hud.chip(canvas, ch.title.upper(), 16, top + 22, hud.ACCENT)
        floor = hud.H - hud.FOOTER_H
        if pf is None:
            hud.chip(canvas, "NO PERSON DETECTED", 16, floor - 44, hud.BAD)
        elif live.get("valid_ratio", 1) < 0.6 and ch.stats.total > 60:
            hud.chip(canvas, "TRACKING WEAK - keep whole body visible", 16, floor - 44, hud.WARN)
        prog = ch.progress(t)
        if prog is not None:
            hud.progress_bar(canvas, 16, floor - 22, hud.W - 32, prog, hud.ACCENT, 10)
        rec_label = "PAUSED" if paused else "REC"
        rec_w = hud.text_width(rec_label, 0.5) + 38
        hud.chip(canvas, rec_label, hud.W - 16 - rec_w, top + 22, hud.WARN if paused else hud.BAD)
        _debug_overlay(rt, canvas)
        hud.footer(canvas, "Perform the movement naturally.", controls)
        rt.display.show(canvas)

        k = rt.key()
        global_action = _global_key(k)
        if global_action:
            return global_action, None
        if k == KEY_ESC:
            return "back", None
        if k == ord("d"):
            rt.debug = not rt.debug
        elif k == ord("s"):
            return "skip", None
        elif k == ord("r"):
            ch.start(time.perf_counter())
            rec_started = time.perf_counter()
            paused, paused_total = False, 0.0
        elif k == ord("p") and not ch.auto_finish:
            paused = not paused
            if paused:
                paused_at = pkt.t
            else:
                paused_total += pkt.t - paused_at
        elif k in (KEY_ENTER, 10) or ch.is_complete(t):
            if ch.auto_finish and not ch.is_complete(t) and k in (KEY_ENTER, 10):
                pass                                   # balance must run its full duration
            else:
                return "done", ch.finish(t)


FOOT_GAP = hud.FOOTER_H + 22


# ---------------------------------------------------------------- review
def review_screen(rt: Runtime, ch: Challenge, block: dict, step: int) -> str:
    """Show the quality verdict; operator accepts, repeats or skips."""
    gate = block.get("quality_gate", {})
    passed = gate.get("passed", False)
    lines = _summary_lines(ch.key, block)
    if not passed:
        lines += [""] + ["Why review is needed:"] + [f"- {r}" for r in gate.get("reasons", [])]
        lines += ["", "Press R to repeat the test, or ENTER to keep it as REVIEW (it will be excluded from fusion)."]
    rt.display.enter_camera_mode()
    _touch(rt, [("Home", KEY_HOME), ("Back", KEY_ESC), ("Repeat", ord("r")), ("Skip", ord("s")), ("Accept", KEY_ENTER)])
    while True:
        pkt, _ = rt.frame(pose_needed=False)
        if pkt is None:
            return _frame_failure(rt)
        canvas, _ = hud.compose(pkt.image, dim=0.3)
        hud.header(canvas, f"{ch.title} - result", step, TOTAL_STEPS, _cam_text(rt))
        hud.message_box(canvas, "QUALITY PASSED" if passed else "QUALITY REVIEW", lines,
                        hud.GOOD if passed else hud.WARN, width=900)
        hud.footer(canvas, "Accept this recording or repeat it.", "ENTER Accept   R Repeat   S Skip test   Q Quit")
        rt.display.show(canvas)
        k = rt.key()
        global_action = _global_key(k)
        if global_action:
            return global_action
        if k in ENTER_KEYS:
            return "accept"
        if k == ord("r"):
            return "repeat"
        if k == ord("s"):
            return "skip"
        if k == KEY_ESC:
            return "repeat"


def _summary_lines(key: str, b: dict) -> list[str]:
    if key == "sit_to_stand":
        return [f"Repetitions: {b.get('valid_repetitions', 0)} valid of {b.get('repetitions', 0)}",
                f"Knee ROM  L {b.get('left_knee_rom_deg', 0):.0f} deg / R {b.get('right_knee_rom_deg', 0):.0f} deg"
                f"   symmetry {b.get('knee_rom_symmetry_ratio', 0):.2f}",
                f"Mean rise time {b.get('average_rise_time_seconds', 0):.2f}s   mean repetition {b.get('average_rep_time_seconds', 0):.2f}s"]
    if key == "gait":
        return [f"Steps: {b.get('total_steps', 0)} in {b.get('walking_bout_seconds', 0):.1f}s of walking",
                f"Cadence {b.get('cadence_steps_per_minute', 0):.0f}/min   step-time symmetry {b.get('left_right_step_balance', 0):.2f}",
                f"Step interval CV {b.get('step_interval_cv', 0):.2f}"]
    return [f"Analysed {b.get('analysed_seconds', 0):.1f}s of quiet standing",
            f"Sway RMS {b.get('sway_rms', 0):.4f}   path {b.get('sway_path_length', 0):.3f} (torso lengths)",
            f"Max displacement {b.get('max_displacement', 0):.3f}   drift {b.get('normalized_drift', 0):.3f}"]


# ---------------------------------------------------------- questionnaire
def questionnaire_screen(rt: Runtime, session, step: int) -> str:
    """Touch-first symptom profile with draft persistence and real back navigation."""
    qn = Questionnaire()

    # Restore a draft/final answer set so Back never silently discards work.
    existing = session.data.get("questionnaire_draft") or session.data.get("questionnaire") or {}
    restored = existing.get("answers") if isinstance(existing, dict) else None
    if restored:
        qn.answers = list(restored)
        qn.index = min(len(qn.answers), len(QUESTIONS))

    rt.display.enter_camera_mode()
    last_q_index = -1
    while not qn.complete():
        pkt, _ = rt.frame(pose_needed=False)
        if pkt is None:
            return _frame_failure(rt)
        canvas, _ = hud.compose(pkt.image, dim=0.25)
        hud.header(canvas, "Symptom Profile", step, TOTAL_STEPS,
                   f"QUESTION {qn.index + 1}/{len(QUESTIONS)}")
        q = qn.current_question
        if qn.index != last_q_index:
            _touch(rt, [(f"{i}. {label}", ord(str(i))) for i, (label, _) in enumerate(q["options"], start=1)]
                   + [("Back", KEY_ESC), ("Home", KEY_HOME)])
            last_q_index = qn.index

        px1, px2 = 40, hud.W - 40
        py1, py2 = hud.HEADER_H + 12, hud.H - hud.FOOTER_H - 12
        hud.panel(canvas, px1, py1, px2, py2, 0.94, border=hud.EDGE)
        hud.text(canvas, "STRUCTURED SYMPTOM PROFILE", px1 + 30, py1 + 34, 0.5, hud.ACCENT, 2)
        counter = f"{qn.index + 1:02d} / {len(QUESTIONS):02d}"
        hud.text(canvas, counter, px2 - 30 - hud.text_width(counter, 0.5), py1 + 34, 0.5, hud.MUTED, 1)
        hud.progress_bar(canvas, px1 + 30, py1 + 48, px2 - px1 - 60,
                         qn.index / max(1, len(QUESTIONS)), hud.ACCENT, 8)

        y = py1 + 100
        for ln in hud.wrap(q["question"], 0.72, px2 - px1 - 80, 2):
            hud.text(canvas, ln, px1 + 30, y, 0.72, hud.INK, 2)
            y += 34

        y += 8
        row_h = min(52, max(40, int((py2 - y - 14) / 4) - 8))
        for number, (label, _) in enumerate(q["options"], start=1):
            hud.panel(canvas, px1 + 30, y, px2 - 30, y + row_h, 0.9, (52, 36, 26), border=hud.EDGE)
            cy = y + row_h // 2
            hud.cv2.circle(canvas, (px1 + 30 + 26, cy), 15, (96, 66, 38), -1, hud.cv2.LINE_AA)
            hud.text_center(canvas, str(number), px1 + 30 + 26, cy + 7, 0.6, hud.ACCENT, 2)
            hud.text(canvas, label, px1 + 30 + 58, cy + 8, 0.64, hud.INK)
            y += row_h + 8

        answered = len(qn.answers)
        hud.footer(canvas,
                   f"{answered} of {len(QUESTIONS)} answered • Choose the response that best describes the participant.",
                   "1-4 Answer   BACKSPACE Previous   ESC Back")
        rt.display.show(canvas)

        k = rt.key()
        global_action = _global_key(k)
        if global_action:
            session.data["questionnaire_draft"] = qn.finish()
            return global_action
        if ord("1") <= k <= ord("4"):
            if qn.answer(k - ord("0")):
                session.data["questionnaire_draft"] = qn.finish()
                last_q_index = -1
        elif k == KEY_BACKSPACE:
            if qn.undo():
                session.data["questionnaire_draft"] = qn.finish()
                last_q_index = -1
        elif k == KEY_ESC:
            session.data["questionnaire_draft"] = qn.finish()
            return "back"

    session.data["questionnaire"] = qn.finish()
    session.data.pop("questionnaire_draft", None)
    return "next"


# ---------------------------------------------------------------- results
def results_screen(rt: Runtime, session, data: dict, saved_path, step: int, on_details, on_report) -> str:
    sts = data.get("sit_to_stand", {})
    gait = data.get("gait", {})
    bal = data.get("balance", {})
    qn = data.get("questionnaire", {})
    q = data.get("assessment_quality", {})
    fp = data.get("movement_fingerprint", {})
    rt.display.enter_camera_mode()
    _touch(rt, [("Details", ord("v")), ("Export", ord("e")), ("New", ord("n")), ("Home", KEY_HOME)])

    def tone(block):
        st = (block.get("quality_gate") or {}).get("status", "REVIEW")
        return hud.GOOD if st == "PASS" else hud.MUTED if st == SKIPPED else hud.WARN

    def status(block):
        return (block.get("quality_gate") or {}).get("status", "-")

    banner = ""
    while True:
        pkt, _ = rt.frame(pose_needed=False)
        if pkt is None:
            return "quit"
        canvas, _ = hud.compose(pkt.image, dim=0.22)
        hud.header(canvas, "Assessment complete", step, TOTAL_STEPS, _cam_text(rt))
        px1, px2 = 16, hud.W - 16
        py = hud.HEADER_H + 10
        hud.panel(canvas, px1, py, px2, hud.H - hud.FOOTER_H - 10, 0.95, border=hud.EDGE)
        inner_w = px2 - px1 - 48
        pat = data.get("patient_snapshot", {})
        hud.text(canvas, "ASSESSMENT SAVED", px1 + 24, py + 36, 0.9, hud.INK, 2)
        hud.text(canvas, hud.fit(f"{pat.get('name', '-')}  |  {pat.get('patient_id', '-')}  |  {data.get('assessment_id')}",
                                 0.5, inner_w), px1 + 26, py + 60, 0.5, hud.MUTED)

        items = [
            ("SIT-TO-STAND", f"{sts.get('valid_repetitions', 0)} reps", tone(sts), status(sts)),
            ("GAIT", f"{gait.get('total_steps', 0)} steps", tone(gait), status(gait)),
            ("BALANCE", f"RMS {bal.get('sway_rms', 0):.3f}", tone(bal), status(bal)),
            ("SYMPTOM INDEX", f"{qn.get('score', 0)} / {qn.get('max_score', 0)}", hud.INK, "custom"),
        ]
        gap = 12
        tile_w = int((inner_w - gap * 3) / 4)
        ty = py + 78
        for i, (label, value, tn, st) in enumerate(items):
            x = px1 + 24 + i * (tile_w + gap)
            hud.card(canvas, x, ty, tile_w, label, value, tn, 88)
            hud.text(canvas, st, x + tile_w - 14 - hud.text_width(st, 0.44, 1), ty + 24, 0.44, tn, 1)

        overall = q.get("overall_status", "REVIEW")
        ry = ty + 88 + 34
        hud.text(canvas, "OVERALL DATA QUALITY", px1 + 26, ry, 0.44, hud.MUTED)
        hud.text(canvas, overall, px1 + 26, ry + 34, 0.9, hud.GOOD if overall == "PASS" else hud.WARN, 2)
        fusion = fp.get("modality_fusion", {})
        fx = px1 + 24 + int(inner_w * 0.34)
        hud.text(canvas, "FUSED MODALITIES", fx, ry, 0.44, hud.MUTED)
        fused = ", ".join(fusion.get("qualified_modalities", [])) or "none qualified"
        hud.text(canvas, hud.fit(fused, 0.58, px2 - fx - 24), fx, ry + 32, 0.58, hud.INK)
        excl = fusion.get("excluded_modalities", [])
        if excl:
            hud.text(canvas, hud.fit("Excluded: " + ", ".join(excl), 0.46, px2 - fx - 24), fx, ry + 56, 0.46, hud.WARN)

        base = data.get("personalized_baseline", {})
        by = ry + 76
        hud.text(canvas, "BASELINE / OBSERVED CHANGE", px1 + 26, by, 0.44, hud.MUTED)
        base_text = ("First usable assessment - this assessment is now the baseline"
                     if base.get("status") == "BASELINE"
                     else f"Compared with {base.get('baseline_assessment_id', '-')}: {len(base.get('changes', {}))} metrics")
        hud.text(canvas, hud.fit(base_text, 0.56, inner_w), px1 + 26, by + 28, 0.56, hud.INK)
        saved = Path(str(saved_path))
        hud.text(canvas, hud.fit(f"Saved: {saved.parent.name}/{saved.name}", 0.44, inner_w),
                 px1 + 26, by + 58, 0.44, hud.MUTED)
        hud.text(canvas, "Research prototype - no clinical diagnosis is generated.", px1 + 26, by + 80, 0.44, hud.MUTED)
        if banner:
            hud.chip(canvas, hud.fit(banner, 0.5, inner_w - 60), px1 + 26, by + 116, hud.GOOD)
        hud.footer(canvas, "Assessment saved successfully.", "Use the touch controls below.")
        rt.display.show(canvas)
        k = rt.key()
        global_action = _global_key(k)
        if global_action:
            return global_action
        if k == ord("v"):
            rt.display.exit_camera_mode()
            on_details(data)
            rt.display.enter_camera_mode()
            _touch(rt, [("Details", ord("v")), ("Export", ord("e")), ("New", ord("n")), ("Home", KEY_HOME)])
        elif k == ord("e"):
            try:
                banner = f"Report saved: {Path(str(on_report(data))).name}"
            except OSError as exc:
                banner = f"Export failed: {exc}"
        elif k == ord("n"):
            return "new"
        elif k == KEY_ESC:
            return "home"

