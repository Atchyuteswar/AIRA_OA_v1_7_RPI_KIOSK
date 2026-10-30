"""Headless smoke test of the Tk screens:  xvfb-run -a python tools/ui_smoke.py"""
import os, sys, tempfile, tkinter as tk
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["AIRA_DATA_DIR"] = tempfile.mkdtemp(prefix="aira_ui_")

from core import screens
from core.display import get_display, get_root

d = get_display(); root = get_root(); root.geometry("1100x800+0+0"); root.update()
fails = []


def walk(w):
    for c in w.winfo_children():
        yield c
        yield from walk(c)


def press(key, delay=250):
    root.after(delay, lambda: (root.focus_force(), root.event_generate(f"<KeyPress-{key}>")))


def check(name, cond):
    print(("ok   " if cond else "FAIL ") + name)
    if not cond:
        fails.append(name)

press("h"); check("home -> history via key", screens.home_screen({"backend": "V4L2", "width": 640, "height": 480, "measured_fps": 30}) == "history")
press("q"); check("home -> quit via key", screens.home_screen(None) == "quit")

# patient form: invalid age first, then valid
def fill_form(age, consent=True):
    def go():
        entries = [w for w in walk(root) if isinstance(w, tk.Entry)]
        for e, v in zip(entries, ("José Ramírez", age, "ref-1")):
            e.delete(0, "end"); e.insert(0, v)
        if consent:
            [w for w in walk(root) if isinstance(w, tk.Checkbutton)][0].select()
        root.focus_force(); root.event_generate("<Return>")
    return go
root.after(300, fill_form("abc"))
def second():
    lbls = [w.cget("text") for w in walk(root) if isinstance(w, tk.Label)]
    check("invalid age shows inline error", any("whole number" in t for t in lbls))
    fill_form("58")()
root.after(700, second)
p = screens.patient_form()
check("patient saved with unicode name", bool(p) and p["name"] == "José Ramírez" and p["age"] == 58)

root.after(300, lambda: (root.focus_force(), root.event_generate("<Return>")))
sel = screens.select_existing_patient()
check("select existing patient (Enter)", bool(sel) and sel["patient_id"] == p["patient_id"])

# closing the window must not hang or crash later code
legacy = {"assessment_id": "AIRA-OLD", "patient_snapshot": {"name": "Old"}, "version": "1.3.0", "sit_to_stand": {"repetitions": 3}}
press("Escape"); screens.assessment_detail(legacy); check("detail screen renders legacy record", True)
press("Escape"); screens.history_screen(); check("history screen opens/closes", True)
press("Escape"); r = screens.patient_entry_flow(); check("patient_entry_flow cancel -> None", r is None)

# window close button while a screen is up
root.after(300, root._on_close if hasattr(root, "_on_close") else d._on_close)
res = screens.home_screen(None)
check("window close ends app loop", d.closed)
print("\nFAILURES:" if fails else "\nALL UI CHECKS PASSED", fails or "")
sys.exit(1 if fails else 0)
