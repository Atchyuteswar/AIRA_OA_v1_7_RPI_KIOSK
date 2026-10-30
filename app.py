"""AIRA-OA v1.7 - non-diagnostic movement screening research prototype.

    python app.py                 # normal use (auto-selects a camera)
    python app.py --camera 1      # force a camera index
    python app.py --video demo.mp4  # analyse a recording instead of a live camera
"""
from __future__ import annotations

import argparse
import os
import sys

from core.version import __version__


def _parse(argv):
    p = argparse.ArgumentParser(description="AIRA-OA movement screening prototype")
    p.add_argument("--camera", type=int, default=None, help="camera index (default: auto)")
    p.add_argument("--video", default=None, help="use a video file instead of a camera")
    p.add_argument("--data-dir", default=None, help="folder for patient/session data")
    p.add_argument("--debug", action="store_true", help="show camera/debug overlay")
    p.add_argument("--fullscreen", action="store_true", help="start the Tk window fullscreen")
    p.add_argument("--version", action="version", version=f"AIRA-OA {__version__}")
    return p.parse_args(argv)


def run_assessment(rt, patient) -> str:
    """Guided assessment for one patient. Returns "home", "new" or "quit"."""
    from assessment.patients import list_sessions
    from assessment.session import AssessmentSession
    from core import flow, screens
    from challenges.balance import Balance
    from challenges.gait import Gait
    from challenges.sit_to_stand import SitToStand
    from assessment.report import export_report
    from core.quality import skipped_block

    history = list_sessions(patient.get("patient_id"))
    session = AssessmentSession(rt.camera.health(), patient=patient, history=history)
    _log = __import__("core.log", fromlist=["get"]).get("app.assessment")

    def challenge_step(cls, step, controls):
        ch = cls()
        while True:
            r = flow.readiness_screen(rt, ch.key, ch.title, step)
            if r == "skip":
                session.add_test(ch.key, skipped_block(ch.key))
                return "next"
            if r != "ready":
                return r
            code, block = flow.record_screen(rt, ch, step, controls)
            if code == "skip":
                session.add_test(ch.key, skipped_block(ch.key))
                return "next"
            if code != "done":
                return code
            verdict = flow.review_screen(rt, ch, block, step)
            if verdict == "accept":
                session.add_test(ch.key, block)
                return "next"
            if verdict == "skip":
                session.add_test(ch.key, skipped_block(ch.key))
                return "next"
            if verdict != "repeat":
                return verdict

    rec_controls = "P Pause   R Restart   ENTER Finish   S Skip   ESC Back   Q Quit"
    steps = [
        lambda: flow.info_screen(rt, "Assessment Setup", [
            f"Patient: {patient.get('name')}  ({patient.get('patient_id')})", "",
            "Three movement tests follow, then a short symptom questionnaire.",
            "Before each test the system checks that the whole body is visible,",
            "well lit and in focus. You can repeat or skip any test.", "",
            "Place a chair side-on or front-on, with the camera 2-3 m away,",
            "at about waist height, so the full body including feet is in view."], 1),
        lambda: challenge_step(SitToStand, 2, rec_controls),
        lambda: challenge_step(Gait, 3, rec_controls),
        lambda: challenge_step(Balance, 4, "R Restart   S Skip   ESC Back   Q Quit"),
        lambda: flow.questionnaire_screen(rt, session, 5),
    ]
    i = 0
    while i < len(steps):
        try:
            code = steps[i]()
        except Exception as exc:  # noqa: BLE001 - kiosk must recover to a safe screen
            _log.exception("Unhandled assessment error at step %s for %s: %s", i + 1, patient.get("patient_id"), exc)
            # Preserve whatever has already been collected. A later run can
            # continue from the patient's history instead of losing the session.
            try:
                if any(session.has(k) for k in ("sit_to_stand", "gait", "balance")) or session.data.get("questionnaire_draft"):
                    session.save()
            except Exception:
                _log.exception("Could not save partial assessment after UI failure")
            screens.error_dialog(
                "Assessment safely stopped",
                "AIRA-OA recovered from an unexpected workflow error. "
                "Any completed data that could be saved has been preserved. "
                "You can return to the patient history and start another assessment.",
                technical=f"{type(exc).__name__}: {exc}",
            )
            return "home"
        if code == "next":
            i += 1
        elif code == "back":
            if i == 0:
                return "home"
            i -= 1
        elif code in ("home", "quit", "camera_error", "pose_error"):
            if code == "camera_error":
                screens.error_dialog(
                    "Camera connection lost",
                    "AIRA-OA could not restore the camera connection. "
                    "The assessment has been stopped safely."
                )
            elif code == "pose_error":
                screens.error_dialog(
                    "Pose engine temporarily failed",
                    "MoveNet could not process the camera frame after several retries. "
                    "The assessment has been stopped safely and completed data can be preserved.",
                    technical=rt.last_error or "Unknown pose inference error",
                )
            done = [k for k in ("sit_to_stand", "gait", "balance") if session.has(k)]
            has_draft = bool(session.data.get("questionnaire_draft"))
            if done or has_draft:
                if screens.confirm(
                    "Save partial assessment?",
                    "Keep the completed tests and any questionnaire progress on this device?"
                ):
                    try:
                        session.save()
                    except OSError as exc:
                        screens.error_dialog("Save failed", str(exc))
            return "quit" if code == "quit" else "home"
        else:
            i += 1

    while True:                                           # save (retry on disk error)
        try:
            path = session.save()
            break
        except OSError as exc:
            if not screens.confirm("Could not save", f"{exc}\n\nTry again?"):
                return "home"
    data = session.data
    rt.display.enter_camera_mode()
    code = flow.results_screen(rt, session, data, path, 6, screens.assessment_detail, lambda d: export_report(d))
    rt.display.exit_camera_mode()
    return code


def main(argv=None) -> int:
    args = _parse(argv if argv is not None else sys.argv[1:])
    if args.data_dir:
        os.environ["AIRA_DATA_DIR"] = args.data_dir
    if args.fullscreen:
        os.environ["AIRA_RPI_FULLSCREEN"] = "1"
    from core import log
    logger = log.setup()
    logger.info("AIRA-OA %s starting", __version__)

    from core import screens
    from core.camera import CameraManager
    from core.config import CAMERA
    from core.display import get_display
    from core.flow import Runtime
    from core.pose import PoseBackendError, PoseEstimator

    display = get_display()
    display.get_root()
    source = args.video if args.video else args.camera
    camera = CameraManager(source)
    if camera.open() is None:
        logger.warning("no camera available at start-up")

    try:
        with PoseEstimator(inference_width=CAMERA.inference_width) as pose:
            rt = Runtime(camera, pose, display, debug=args.debug)
            while not display.closed:
                action = screens.home_screen(camera.health() if camera.cap else None)
                if action == "quit" or display.closed:
                    break
                if action == "history":
                    selected_patient = screens.history_screen()
                    if selected_patient:
                        outcome = run_assessment(rt, selected_patient)
                        if outcome == "quit":
                            break
                    continue
                if action in ("camera", "status"):
                    if camera.cap is None and camera.open() is None:
                        screens.no_camera_dialog()
                    else:
                        health = camera.health()
                        if action == "camera":
                            screens.camera_system_dialog(health)
                        else:
                            screens.quick_status_dialog(health)
                    continue
                # action == "new"
                if camera.cap is None or camera.lost:
                    if not (camera.reconnect() if camera.source is not None else camera.open()):
                        screens.no_camera_dialog()
                        continue
                while not display.closed:
                    patient = screens.patient_entry_flow()
                    if not patient:
                        break
                    outcome = run_assessment(rt, patient)
                    if outcome != "new":
                        break
                if display.closed:
                    break
    except PoseBackendError as exc:
        logger.error("%s", exc)
        screens.error_dialog("Pose engine unavailable", str(exc))
        return 2
    except Exception as exc:  # noqa: BLE001 - last-resort kiosk recovery
        logger.exception("Fatal application error: %s", exc)
        try:
            screens.error_dialog(
                "AIRA-OA recovered from an error",
                "The application encountered an unexpected error. "
                "Please return to the home screen and try again. "
                "Technical details were written to the local application log."
            )
        except Exception:
            pass
        return 1
    finally:
        camera.close()
        display.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
