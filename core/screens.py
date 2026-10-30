"""Touch-first Tk screens for the AIRA-OA kiosk.

The Raspberry Pi target is a 7-inch 1024x600 touchscreen.  Every operator
screen therefore exposes a visible touch action, text fields open an on-screen
keyboard, and list/detail views use large paging controls instead of relying
on mouse-wheel scrolling or a physical keyboard.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import platform
import shutil
import tkinter as tk
from pathlib import Path
from tkinter import ttk

from assessment.patients import PatientValidationError, list_patients, list_sessions, load_patient, save_patient
from assessment.questionnaire import DOMAIN_LABELS, QUESTIONS
from assessment.report import export_features_csv, export_report
from core.display import TOUCH_HEIGHT, TOUCH_MODE, TOUCH_WIDTH, font_family, get_display, get_root, mono_family
from core.touch import TouchKeyboard
from core.version import DISCLAIMER, __version__
from core.paths import data_dir, logs_dir

BG, PANEL, PANEL2, FIELD = "#0b1020", "#121a2d", "#18233b", "#0d1527"
TEXT, MUTED, ACCENT = "#eef4ff", "#91a0ba", "#62d8ff"
GOOD, WARN, DANGER = "#62e6a7", "#ffcc66", "#ff7b8a"
BORDER, BTN, BTN_HOVER = "#25375a", "#1c2d4d", "#2a4373"
ACCENT_HOVER, ON_ACCENT = "#8be6ff", "#06121f"
DANGER_BG, DANGER_HOVER, DANGER_FG = "#3b2230", "#52293a", "#ff9aa6"


def flat_button(parent, text, command, family, primary=False, danger=False, width=15, size=11):
    """Borderless touch button with hover/pressed colours (no native outline)."""
    bg, hover, fg = ((ACCENT, ACCENT_HOVER, ON_ACCENT) if primary else
                     (DANGER_BG, DANGER_HOVER, DANGER_FG) if danger else (BTN, BTN_HOVER, TEXT))
    b = tk.Button(parent, text=text, command=command, bg=bg, fg=fg, activebackground=hover,
                  activeforeground=fg, relief="flat", bd=0, highlightthickness=0, takefocus=0,
                  cursor="hand2", padx=12, pady=10, font=(family, size, "bold"), width=width)
    b.bind("<Enter>", lambda _e, w=b, h=hover: w.configure(bg=h))
    b.bind("<Leave>", lambda _e, w=b, c=bg: w.configure(bg=c))
    return b


def card_frame(parent, bg=PANEL, padx=16, pady=14):
    return tk.Frame(parent, bg=bg, padx=padx, pady=pady, highlightthickness=1,
                    highlightbackground=BORDER, highlightcolor=BORDER)


def center_window(win, width, height):
    root = get_root()
    root.update_idletasks()
    x = max(0, root.winfo_rootx() + (root.winfo_width() - width) // 2)
    y = max(0, root.winfo_rooty() + (root.winfo_height() - height) // 2)
    win.geometry(f"{width}x{height}+{x}+{y}")


class Screen:
    def __init__(self, title: str, width: int = TOUCH_WIDTH, height: int = TOUCH_HEIGHT):
        self.disp = get_display()
        self.root = get_root()
        self.disp.exit_camera_mode()
        self.font, self.mono = font_family(), mono_family()
        self.result = None
        self.keyboard = TouchKeyboard(self.root)
        r = self.root
        for child in r.winfo_children(): child.destroy()
        r.title(f"AIRA-OA | {title}")
        if TOUCH_MODE:
            r.geometry(f"{TOUCH_WIDTH}x{TOUCH_HEIGHT}")
        else:
            r.geometry(f"{width}x{height}")
            r.minsize(900, 600)
        r.configure(bg=BG)
        r.unbind("<Return>"); r.unbind("<Escape>")
        style = ttk.Style(r); style.theme_use("clam")
        style.configure("Treeview", background=PANEL, fieldbackground=PANEL, foreground=TEXT, rowheight=44,
                        borderwidth=0, font=(self.font, 10))
        style.configure("Treeview.Heading", background=PANEL2, foreground=TEXT, relief="flat", font=(self.font, 10, "bold"))
        style.map("Treeview", background=[("selected", "#244765")], foreground=[("selected", "white")])
        style.configure("TCombobox", fieldbackground=FIELD, background=PANEL2, foreground=TEXT,
                        borderwidth=0, relief="flat", padding=5, arrowsize=14)
        style.map("TCombobox", fieldbackground=[("readonly", FIELD)], foreground=[("readonly", TEXT)])
        style.configure("AIRA.TCombobox", fieldbackground=FIELD, background=BTN, foreground=TEXT,
                        bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER, arrowcolor=ACCENT,
                        borderwidth=1, relief="flat", padding=6, arrowsize=18)
        style.map("AIRA.TCombobox", fieldbackground=[("readonly", FIELD)], foreground=[("readonly", TEXT)],
                  background=[("active", BTN_HOVER), ("readonly", BTN)], bordercolor=[("focus", ACCENT)],
                  arrowcolor=[("active", ACCENT_HOVER)])
        r.option_add("*TCombobox*Listbox.background", FIELD)
        r.option_add("*TCombobox*Listbox.foreground", TEXT)
        r.option_add("*TCombobox*Listbox.selectBackground", "#244765")
        r.option_add("*TCombobox*Listbox.selectForeground", "white")
        r.option_add("*TCombobox*Listbox.font", (self.font, 13))

    def label(self, parent, text, size=11, color=TEXT, bold=False, **kw):
        return tk.Label(parent, text=text, bg=parent.cget("bg"), fg=color,
                        font=(self.font, size, "bold" if bold else "normal"), **kw)

    def button(self, parent, text, command, primary=False, danger=False, width=15):
        return flat_button(parent, text, command, self.font, primary, danger, width)

    def card(self, parent, bg=PANEL, padx=16, pady=14):
        return card_frame(parent, bg, padx, pady)

    def nav(self, back=None, home=None, primary=None, primary_label="Continue", extra=None):
        """Bottom action bar: Back/Home on the left; ``extra`` actions then the primary on the right,
        in the order given (left to right)."""
        bar = tk.Frame(self.root, bg=BG)
        bar.pack(fill="x", side="bottom")
        tk.Frame(bar, bg=BORDER, height=1).pack(fill="x")
        inner = tk.Frame(bar, bg=BG)
        inner.pack(fill="x", padx=22, pady=(8, 10))
        if back is not None: self.button(inner, "◀  Back", back, width=11).pack(side="left", padx=(0, 6))
        if home is not None: self.button(inner, "⌂  Home", home, width=11).pack(side="left", padx=6)
        right = [(label, cmd, False) for label, cmd in (extra or [])]
        if primary is not None: right.append((primary_label, primary, True))
        for label, cmd, is_primary in reversed(right):
            danger = label.strip().lower() in ("cancel", "exit", "quit")
            self.button(inner, label, cmd, is_primary, danger, width=11).pack(side="right", padx=(6, 0))
        return bar

    def attach_entry(self, entry, numeric=False, next_callback=None):
        entry.bind("<Button-1>", lambda _e, w=entry, n=numeric, cb=next_callback: self.keyboard.attach(w, n, cb), add="+")
        entry.bind("<FocusIn>", lambda _e, w=entry, n=numeric, cb=next_callback: self.keyboard.attach(w, n, cb), add="+")

    def finish(self, value=None):
        self.keyboard.hide(); self.result = value; self.root.quit()

    def run(self):
        self.root.mainloop()
        self.keyboard.hide()
        return None if self.disp.closed else self.result


def _touch_dialog(title: str, message: str, buttons: list[tuple[str, object]], accent_index: int = 0):
    root = get_root(); win = tk.Toplevel(root); win.title(f"AIRA-OA | {title}"); win.configure(bg=BG)
    win.transient(root); win.grab_set(); center_window(win, 860, 470)
    try: win.attributes("-topmost", True)
    except tk.TclError: pass
    f = font_family()
    outer = card_frame(win, PANEL, 0, 0); outer.pack(fill="both", expand=True, padx=14, pady=14)
    tk.Frame(outer, bg=ACCENT, width=5).pack(side="left", fill="y")
    body = tk.Frame(outer, bg=PANEL); body.pack(fill="both", expand=True, padx=26, pady=20)
    tk.Label(body, text=title, bg=PANEL, fg=TEXT, font=(f, 21, "bold")).pack(anchor="w")
    tk.Label(body, text=message, bg=PANEL, fg=MUTED, justify="left", anchor="nw", wraplength=740,
             font=(f, 12)).pack(fill="both", expand=True, pady=(10, 8), anchor="nw")
    bar = tk.Frame(body, bg=PANEL); bar.pack(fill="x")
    result = {"value": None}
    def choose(v):
        result["value"] = v
        try: win.grab_release(); win.destroy()
        except tk.TclError: pass
    for i, (label, value) in enumerate(reversed(buttons)):
        flat_button(bar, label, lambda v=value: choose(v), f,
                    primary=(len(buttons) - 1 - i) == accent_index, width=12).pack(side="right", padx=(8, 0))
    win.protocol("WM_DELETE_WINDOW", lambda: choose(False)); win.wait_window(); return result["value"]


def _system_stats() -> dict:
    mem_total = mem_available = 0
    try:
        for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
            k, v = line.split(":", 1); val = int(v.strip().split()[0])
            if k == "MemTotal": mem_total = val
            elif k == "MemAvailable": mem_available = val
    except (OSError, ValueError):
        pass
    disk = shutil.disk_usage(data_dir())
    return {
        "cpu": os.cpu_count() or 1,
        "ram_total": mem_total / 1024 / 1024 if mem_total else 0,
        "ram_available": mem_available / 1024 / 1024 if mem_available else 0,
        "disk_free": disk.free / 1024**3,
        "disk_total": disk.total / 1024**3,
        "platform": platform.machine(),
        "python": platform.python_version(),
    }


def _latest_summary() -> tuple[list[dict], list[dict]]:
    patients = list_patients()
    sessions = list_sessions()
    return patients, sessions


def _dashboard_window(title: str, subtitle: str):
    root = get_root(); win = tk.Toplevel(root); win.title(f"AIRA-OA | {title}"); win.configure(bg=BG)
    win.transient(root); win.grab_set(); center_window(win, 970, 540)
    try: win.attributes("-topmost", True)
    except tk.TclError: pass
    f = font_family()
    tk.Label(win, text=title, bg=BG, fg=TEXT, font=(f, 21, "bold")).pack(anchor="w", padx=26, pady=(18, 2))
    tk.Label(win, text=subtitle, bg=BG, fg=MUTED, font=(f, 10)).pack(anchor="w", padx=26, pady=(0, 10))
    body = tk.Frame(win, bg=BG); body.pack(fill="both", expand=True, padx=22)
    return win, body, f


def _stat_card(parent, row, col, title, value, detail="", tone=TEXT):
    card = card_frame(parent, PANEL2, 16, 12); card.grid(row=row, column=col, sticky="nsew", padx=6, pady=6)
    parent.rowconfigure(row, weight=1)
    f = font_family()
    tk.Label(card, text=title.upper(), bg=PANEL2, fg=MUTED, font=(f, 9, "bold")).pack(anchor="w")
    tk.Label(card, text=str(value), bg=PANEL2, fg=tone, font=(f, 17, "bold"), wraplength=250, justify="left").pack(anchor="w", pady=(6, 2))
    if detail: tk.Label(card, text=detail, bg=PANEL2, fg=MUTED, wraplength=250, justify="left", font=(f, 9)).pack(anchor="w")


def camera_system_dialog(health: dict) -> None:
    """High-level system readiness; detailed camera metrics stay in Diagnostics."""
    win, body, f = _dashboard_window("Camera & System", "Kiosk readiness at a glance. Use Camera Diagnostics for raw capture metrics.")
    for c in range(3): body.columnconfigure(c, weight=1)
    h = health or {}; st = _system_stats()
    connected = bool(h.get("connected")); fps = float(h.get("measured_fps") or h.get("fps") or 0)
    cam_ok = connected and bool(h.get("profile_ok", False)) and fps >= 24
    _stat_card(body,0,0,"Camera", "READY" if cam_ok else "CHECK", f"{h.get('camera_name','Camera 0')} • {h.get('backend','-')}", GOOD if cam_ok else WARN)
    _stat_card(body,0,1,"Capture profile", f"{h.get('width',0)}×{h.get('height',0)}", f"{fps:.1f} measured FPS • target {h.get('target_fps',30)} FPS", GOOD if cam_ok else WARN)
    _stat_card(body,0,2,"Capture health", f"{h.get('dropped_frames',0)} dropped", f"{h.get('drop_ratio',0)*100:.1f}% drop ratio • {h.get('frames',0)} frames", GOOD if not h.get('dropped_frames') else WARN)
    _stat_card(body,1,0,"Pose engine", os.environ.get("AIRA_POSE_BACKEND","movenet").upper(), "MoveNet Lightning • CPU inference", ACCENT)
    _stat_card(body,1,1,"Raspberry Pi", st['platform'], f"Python {st['python']} • {st['cpu']} CPU threads", TEXT)
    _stat_card(body,1,2,"Storage", f"{st['disk_free']:.1f} GB free", f"of {st['disk_total']:.1f} GB • local-first data", GOOD if st['disk_free'] > 1 else WARN)
    note = "SYSTEM READY — camera profile meets the kiosk target." if cam_ok else "SYSTEM CHECK — verify the USB camera and capture profile before assessment."
    tk.Label(win, text=note, bg=BG, fg=GOOD if cam_ok else WARN, font=(f, 11, "bold")).pack(anchor="w", padx=30, pady=8)
    flat_button(win, "Close", lambda: (win.grab_release(), win.destroy()), f, True, width=14).pack(side="right", padx=26, pady=14)
    win.protocol("WM_DELETE_WINDOW", lambda:(win.grab_release(),win.destroy())); win.wait_window()


def quick_status_dialog(health: dict) -> None:
    """Workflow/data status — deliberately avoids repeating camera diagnostics."""
    win, body, f = _dashboard_window("Quick Status", "What is happening with the kiosk and its stored assessment records right now.")
    for c in range(3): body.columnconfigure(c, weight=1)
    patients, sessions = _latest_summary()
    latest = sessions[0] if sessions else {}
    snap = latest.get("patient_snapshot") or {}
    quality = (latest.get("assessment_quality") or {}).get("overall_status", "—")
    last_when = dt.datetime.fromtimestamp(latest.get("started_at_epoch",0)).strftime("%d %b %Y %H:%M") if latest.get("started_at_epoch") else "No assessments yet"
    _stat_card(body,0,0,"Patients",len(patients),"Patient-linked records stored on this kiosk",ACCENT)
    _stat_card(body,0,1,"Assessments",len(sessions),"Completed or partially saved session records",ACCENT)
    _stat_card(body,0,2,"Latest quality",quality,f"{last_when}",GOOD if quality == "PASS" else WARN if quality in ("REVIEW","PARTIAL") else TEXT)
    _stat_card(body,1,0,"Latest patient",snap.get("name","—"),snap.get("patient_id","No patient record"),TEXT)
    _stat_card(body,1,1,"Latest assessment",latest.get("assessment_id","—"),"Open Patient History to inspect the full record",TEXT)
    next_action = "Start a new assessment" if patients else "Register the first patient"
    _stat_card(body,1,2,"Next action",next_action,"The kiosk stores data locally on the device",GOOD)
    tk.Label(win, text="This panel is intentionally separate from Camera Diagnostics: it reports workflow/data state, not raw camera telemetry.", bg=BG, fg=MUTED, font=(f,10)).pack(anchor="w", padx=30, pady=7)
    flat_button(win, "Close", lambda: (win.grab_release(), win.destroy()), f, True, width=14).pack(side="right", padx=26, pady=14)
    win.protocol("WM_DELETE_WINDOW", lambda:(win.grab_release(),win.destroy())); win.wait_window()


def camera_info_dialog(health: dict) -> None:
    profile = "PASS" if health.get("profile_ok") else "CHECK"
    _touch_dialog("Camera Diagnostics",
        f"Camera: {health.get('camera_name')}\nBackend: {health.get('backend')}\n"
        f"Active profile: {health.get('width')}x{health.get('height')} @ {health.get('fps', 0):.1f} FPS\n"
        f"Measured FPS: {health.get('measured_fps', 0):.1f}\n"
        f"Target: {health.get('target_width', 1280)}x{health.get('target_height', 720)} @ {health.get('target_fps', 30)} FPS\n"
        f"Profile status: {profile}\nFrames: {health.get('frames')}\n"
        f"Dropped: {health.get('dropped_frames')} ({health.get('drop_ratio', 0)*100:.1f}%)\n"
        f"Connected: {'yes' if health.get('connected') else 'NO'}", [("Close", True)])


def no_camera_dialog() -> None:
    _touch_dialog("Camera not available",
        "No usable camera was found.\n\nCheck the USB camera connection and ensure no other application is using it.\n"
        "Run python tools/camera_check.py for diagnostics.", [("Close", True)])


def error_dialog(title: str, message: str, technical: str | None = None) -> None:
    if not technical:
        _touch_dialog(title, message, [("Close", True)])
        return
    root = get_root(); win = tk.Toplevel(root); win.title(f"AIRA-OA | {title}"); win.configure(bg=BG)
    win.transient(root); win.grab_set(); center_window(win, 900, 500)
    try: win.attributes("-topmost", True)
    except tk.TclError: pass
    f = font_family()
    outer = card_frame(win, PANEL, 0, 0); outer.pack(fill="both", expand=True, padx=14, pady=14)
    tk.Frame(outer, bg=DANGER, width=5).pack(side="left", fill="y")
    body = tk.Frame(outer, bg=PANEL); body.pack(fill="both", expand=True, padx=26, pady=18)
    tk.Label(body, text=title, bg=PANEL, fg=DANGER, font=(f, 21, "bold")).pack(anchor="w")
    tk.Label(body, text=message, bg=PANEL, fg=TEXT, justify="left", anchor="w", wraplength=770, font=(f, 12)).pack(fill="x", pady=(8, 4), anchor="w")
    tk.Label(body, text="TECHNICAL DETAIL", bg=PANEL, fg=MUTED, font=(f, 9, "bold")).pack(anchor="w", pady=(8, 3))
    tk.Label(body, text=technical, bg=FIELD, fg=WARN, justify="left", anchor="w", wraplength=760, font=(f, 10)).pack(fill="x", ipady=10, ipadx=8)
    tk.Label(body, text=f"Full log: {logs_dir() / 'aira.log'}", bg=PANEL, fg=MUTED, font=(f, 9)).pack(anchor="w", pady=(6, 0))
    flat_button(body, "Close", lambda: (win.grab_release(), win.destroy()), f, True, width=14).pack(side="bottom", anchor="e", pady=(8, 0))
    win.protocol("WM_DELETE_WINDOW", lambda: (win.grab_release(), win.destroy())); win.wait_window()


def info_dialog(title: str, message: str) -> None:
    _touch_dialog(title, message, [("Done", True)])


def confirm(title: str, message: str) -> bool:
    return bool(_touch_dialog(title, message, [("No", False), ("Yes", True)], 1))


def home_screen(camera_health: dict | None = None) -> str:
    """Kiosk landing screen: one obvious primary action, three supporting areas."""
    s = Screen("Screening Console"); r = s.root

    header = tk.Frame(r, bg=BG)
    header.pack(fill="x", padx=28, pady=(16, 4))
    brand = tk.Frame(header, bg=BG); brand.pack(side="left")
    s.label(brand, "AIRA-OA", 28, TEXT, True).pack(anchor="w")
    s.label(brand, "Personalized biomechanical screening", 11, ACCENT, True).pack(anchor="w")

    h = camera_health or {}
    connected = bool(h.get("connected"))
    fps = float(h.get("measured_fps") or h.get("fps") or 0)
    res = f"{h.get('width', 0)}×{h.get('height', 0)}" if h.get("width") else "—"
    camera_ok = connected and bool(h.get("profile_ok", True)) and fps >= 24
    dot = GOOD if camera_ok else WARN if connected else DANGER
    status = card_frame(header, PANEL, 14, 9); status.pack(side="right", pady=6)
    tk.Label(status, text="●", bg=PANEL, fg=dot, font=(s.font, 14, "bold")).pack(side="left")
    box = tk.Frame(status, bg=PANEL); box.pack(side="left", padx=(8, 0))
    s.label(box, "Camera ready" if camera_ok else ("Camera needs attention" if connected else "Camera offline"),
            11, TEXT, True).pack(anchor="w")
    s.label(box, f"{res}  •  {fps:.0f} FPS" if connected else "Connect a USB camera", 9, MUTED).pack(anchor="w")

    hero = card_frame(r, PANEL, 0, 0); hero.pack(fill="x", padx=26, pady=(10, 10))
    hero.columnconfigure(1, weight=1)
    tk.Frame(hero, bg=ACCENT, width=5).grid(row=0, column=0, sticky="ns")
    text_col = tk.Frame(hero, bg=PANEL); text_col.grid(row=0, column=1, sticky="nsew", padx=22, pady=16)
    s.label(text_col, "GUIDED ASSESSMENT", 10, ACCENT, True).pack(anchor="w")
    s.label(text_col, "Start a new screening session", 22, TEXT, True).pack(anchor="w", pady=(2, 3))
    s.label(text_col, "Patient  →  camera check  →  movement tests  →  symptom profile  →  results",
            11, MUTED, wraplength=600, justify="left").pack(anchor="w")
    s.button(hero, "＋  New assessment", lambda: s.finish("new"), True, width=19).grid(
        row=0, column=2, padx=(10, 22), sticky="e")

    grid = tk.Frame(r, bg=BG)
    grid.pack(fill="both", expand=True, padx=26, pady=(0, 6))
    for c in range(3): grid.columnconfigure(c, weight=1, uniform="home")
    grid.rowconfigure(0, weight=1)
    cards = [
        ("RECORDS", "Patient history", "Profiles, assessment timelines, data quality and exported reports.",
         "history", "Open history"),
        ("SYSTEM", "Camera & system", "Camera readiness, pose engine, storage and capture health.",
         "camera", "System check"),
        ("OVERVIEW", "Quick status", "Patients, assessments and the latest result at a glance.",
         "status", "View status"),
    ]
    try:
        patients, sessions = _latest_summary()
        latest_q = ((sessions[0].get("assessment_quality") or {}).get("overall_status", "—")) if sessions else "—"
    except Exception:                                             # noqa: BLE001 - never block the home screen
        patients, sessions, latest_q = [], [], "—"
    metrics = {
        "history": (f"{len(patients)} patient{'s' if len(patients) != 1 else ''}", f"{len(sessions)} assessment{'s' if len(sessions) != 1 else ''} stored", ACCENT),
        "camera": ((f"{fps:.0f} FPS" if connected else "Offline"), (f"{res} capture" if connected else "No camera detected"),
                   GOOD if camera_ok else WARN if connected else DANGER),
        "status": (latest_q, "Latest data quality" if sessions else "No assessments yet",
                   GOOD if latest_q == "PASS" else WARN if latest_q in ("REVIEW", "PARTIAL") else MUTED),
    }
    for i, (tag, title, desc, action, label) in enumerate(cards):
        f = card_frame(grid, PANEL, 16, 14)
        f.grid(row=0, column=i, sticky="nsew", padx=6)
        s.label(f, tag, 9, ACCENT, True).pack(anchor="w")
        s.label(f, title, 15, TEXT, True).pack(anchor="w", pady=(2, 4))
        s.label(f, desc, 10, MUTED, wraplength=270, justify="left").pack(anchor="w")
        big, small, tone = metrics[action]
        s.label(f, big, 22, tone, True).pack(anchor="w", pady=(14, 0))
        s.label(f, small, 10, MUTED).pack(anchor="w")
        s.button(f, label, lambda a=action: s.finish(a), False, width=14).pack(side="bottom", anchor="w", pady=(10, 0))

    footer = tk.Frame(r, bg=BG)
    footer.pack(fill="x", padx=28, pady=(2, 12))
    s.label(footer, "Local-first   •   Data stays on this device   •   Not a clinical diagnosis", 9, MUTED).pack(side="left")
    s.button(footer, "Exit", lambda: s.finish("quit"), False, danger=True, width=8).pack(side="right")

    for key, action in (("n", "new"), ("h", "history"), ("c", "camera"), ("s", "status"), ("q", "quit")):
        r.bind(key, lambda _e, a=action: s.finish(a))
    r.bind("<Escape>", lambda _e: s.finish("quit"))
    return s.run() or "quit"


def patient_form(existing: dict | None = None) -> dict | None:
    existing=existing or {}; s=Screen("Patient Registration"); r=s.root
    head=tk.Frame(r,bg=BG); head.pack(fill="x",padx=26,pady=(14,4))
    s.label(head,"Patient Registration",22,bold=True).pack(side="left")
    s.label(head,"Tap a field to open the keyboard   •   * required",10,MUTED).pack(side="right",pady=6)
    panel=s.card(r,PANEL,20,10); panel.pack(fill="both",expand=True,padx=26,pady=4)
    for c in (1,3): panel.columnconfigure(c,weight=1,uniform="f")
    fields={}
    def entry(label,key,row,col,span=1):
        s.label(panel,label,10,MUTED,True).grid(row=row,column=col,sticky="w",pady=(7,0))
        e=tk.Entry(panel,bg=FIELD,fg=TEXT,insertbackground=ACCENT,relief="flat",font=(s.font,13),
                   highlightthickness=1,highlightbackground=BORDER,highlightcolor=ACCENT)
        e.grid(row=row,column=col+1,columnspan=span,sticky="ew",padx=(10,18),pady=(7,0),ipady=7)
        e.insert(0,str(existing.get(key,""))); fields[key]=e
    entry("Name / reference *","name",0,0,3)
    entry("Age *","age",1,0); entry("Contact","contact",1,2)
    def combo(label,key,values,row,col=0):
        s.label(panel,label,10,MUTED,True).grid(row=row,column=col,sticky="w",pady=(7,0))
        cb=ttk.Combobox(panel,values=values,state="readonly",style="AIRA.TCombobox",font=(s.font,11)); cb.grid(row=row,column=col+1,sticky="ew",padx=(10,18),pady=(7,0),ipady=5); cb.set(existing.get(key) if existing.get(key) in values else values[0]); fields[key]=cb
    combo("Sex","sex",["Male","Female","Other","Prefer not to say"],2,0)
    combo("Dominant side","dominant_side",["Right","Left","Both / unclear","Unknown"],2,2)
    combo("OA-related assessment","oa_history",["Yes","No","Unknown"],3,0)
    combo("Symptomatic area","symptomatic_area",["Right knee","Left knee","Both knees","Hip","Other / unclear","No current pain"],3,2)
    consent=tk.BooleanVar(value=bool(existing.get("consent",False)))
    consent_text="Participant consent / screening-purpose confirmation recorded *"
    cb=tk.Checkbutton(panel,text="☐  "+consent_text,variable=consent,indicatoron=False,bg=BTN,fg=TEXT,selectcolor="#1d5a77",
                      activebackground=BTN_HOVER,activeforeground=TEXT,font=(s.font,11,"bold"),highlightthickness=0,bd=0,
                      relief="flat",padx=14,pady=10,anchor="w",cursor="hand2",takefocus=0)
    cb.grid(row=4,column=0,columnspan=4,sticky="ew",padx=(0,18),pady=(12,3))
    consent.trace_add("write",lambda *_:cb.configure(text=("☑  " if consent.get() else "☐  ")+consent_text))
    if consent.get(): cb.configure(text="☑  "+consent_text)
    err=s.label(panel,"",10,DANGER,True); err.grid(row=5,column=0,columnspan=4,sticky="w")
    def save():
        profile={k:w.get() for k,w in fields.items()}; profile["consent"]=consent.get()
        if existing.get("patient_id"): profile["patient_id"]=existing["patient_id"]
        try: s.finish(save_patient(profile))
        except PatientValidationError as exc: err.configure(text=str(exc))
    order=[fields["name"],fields["age"],fields["contact"]]
    for i,e in enumerate(order): s.attach_entry(e,numeric=(e is not fields["name"]),next_callback=(lambda j=i: order[min(j+1,len(order)-1)].focus_set()))
    s.nav(back=lambda:s.finish(None),primary=save,primary_label="Save & Continue",extra=[("Cancel",lambda:s.finish(None))])
    # The touch keyboard can move focus away from the Entry, so Return is
    # intentionally global while this form is active. Clean the global tags
    # immediately after leaving the form so callbacks cannot leak into later
    # screens.
    r.bind_all("<Return>", lambda _e: save(), add="+")
    r.bind_all("<Escape>", lambda _e: s.finish(None), add="+")
    order[0].focus_set()
    try:
        return s.run()
    finally:
        try: r.unbind_all("<Return>")
        except tk.TclError: pass
        try: r.unbind_all("<Escape>")
        except tk.TclError: pass


def select_existing_patient() -> dict | None:
    patients=list_patients()
    if not patients: info_dialog("No patients","No patient records exist yet. Register a new patient first."); return None
    s=Screen("Select Patient"); r=s.root
    head=tk.Frame(r,bg=BG); head.pack(fill="x",padx=26,pady=(14,4)); s.label(head,"Select existing patient",22,bold=True).pack(side="left"); s.label(head,"Search, then tap Use",10,MUTED).pack(side="right",pady=6)
    q=tk.StringVar(); ent=tk.Entry(r,textvariable=q,bg=FIELD,fg=TEXT,insertbackground=ACCENT,relief="flat",font=(s.font,13),highlightthickness=1,highlightbackground=BORDER,highlightcolor=ACCENT); ent.pack(fill="x",padx=26,pady=6,ipady=8); s.attach_entry(ent)
    list_frame=tk.Frame(r,bg=BG); list_frame.pack(fill="both",expand=True,padx=26,pady=4)
    page=[0]; filtered=[]; per=4
    def refresh(*_):
        filtered[:]=[p for p in patients if not q.get().strip() or q.get().strip().lower() in f"{p.get('patient_id','')} {p.get('name','')}".lower()]
        page[0]=min(page[0],max(0,(len(filtered)-1)//per)); render()
    def render():
        for c in list_frame.winfo_children(): c.destroy()
        start=page[0]*per; chunk=filtered[start:start+per]
        for i,p in enumerate(chunk):
            f=s.card(list_frame,PANEL,16,10); f.pack(fill="x",pady=4)
            col=tk.Frame(f,bg=PANEL); col.pack(side="left")
            s.label(col,p.get("name","-"),14,bold=True).pack(anchor="w")
            s.label(col,f"{p.get('patient_id','-')}   •   Age {p.get('age','-')}   •   {p.get('sex','-')}",10,MUTED).pack(anchor="w")
            s.button(f,"Use",lambda pid=p.get("patient_id"):s.finish(load_patient(pid) or p),True,width=9).pack(side="right")
        if not chunk: s.label(list_frame,"No matching patients.",11,MUTED).pack(pady=24)
        info=s.label(list_frame,f"Patients {start+1 if filtered else 0}–{min(start+per,len(filtered))} of {len(filtered)}",10,MUTED); info.pack(anchor="w",pady=4)
    q.trace_add("write",refresh); refresh()
    def choose_first(_e=None):
        if filtered:
            s.finish(load_patient(filtered[0].get("patient_id")) or filtered[0])
    ent.bind("<Return>", choose_first, add="+")
    r.bind_all("<Return>", choose_first, add="+")
    def prev(): page[0]=max(0,page[0]-1); render()
    def nxt(): page[0]=min(max(0,(len(filtered)-1)//per),page[0]+1); render()
    s.nav(back=lambda:s.finish(None),primary=None,extra=[("Previous",prev),("Next",nxt),("Cancel",lambda:s.finish(None))])
    ent.focus_set()
    try:
        return s.run()
    finally:
        try: r.unbind_all("<Return>")
        except tk.TclError: pass


def patient_entry_flow() -> dict | None:
    while True:
        s=Screen("Patient"); r=s.root
        s.label(r,"Who is being assessed?",26,bold=True).pack(anchor="w",padx=30,pady=(22,2))
        s.label(r,"Choose a patient record to continue.",12,MUTED).pack(anchor="w",padx=30)
        body=tk.Frame(r,bg=BG); body.pack(fill="both",expand=True,padx=24,pady=18); body.columnconfigure((0,1),weight=1,uniform="e"); body.rowconfigure(0,weight=1)
        for c,(num,title,mode,desc,btn,primary,points) in enumerate((("1","New patient","new","Register a new patient and create a linked record.","Register patient",True,("Name, age and consent","About one minute")),("2","Existing patient","existing","Continue with a patient who is already registered, keeping their history.","Choose patient",False,("Search by name or ID","Earlier results are kept")))):
            f=s.card(body,PANEL,26,22); f.grid(row=0,column=c,sticky="nsew",padx=8)
            badge=tk.Label(f,text=num,bg=ACCENT if primary else BTN,fg=ON_ACCENT if primary else ACCENT,font=(s.font,16,"bold"),width=2)
            badge.pack(anchor="w")
            s.label(f,title,20,TEXT,True).pack(anchor="w",pady=(14,4))
            s.label(f,desc,12,MUTED,wraplength=360,justify="left").pack(anchor="w")
            for line in points: s.label(f,"✓  "+line,11,TEXT).pack(anchor="w",pady=(8,0))
            s.button(f,btn,lambda m=mode:s.finish(m),primary,width=18).pack(side="bottom",anchor="w",pady=(14,0))
        s.nav(back=lambda:s.finish(None),primary=None,extra=[("Cancel",lambda:s.finish(None))]); r.bind("<Escape>", lambda _e: s.finish(None)); mode=s.run()
        if mode is None: return None
        patient=patient_form() if mode=="new" else select_existing_patient()
        if patient: return patient
        if get_display().closed: return None


def _pct(v): return "-" if v is None else f"{v:+.1f}%"


def detail_sections(d: dict):
    pat,q=d.get("patient_snapshot",{}),d.get("assessment_quality",{}); sts,gait,bal=d.get("sit_to_stand",{}),d.get("gait",{}),d.get("balance",{}); fp,qn=d.get("movement_fingerprint",{}),d.get("questionnaire",{}); base=d.get("personalized_baseline",{})
    def g(b):
        gate=b.get("quality_gate",{}); return gate.get("status","-")+ ("" if gate.get("passed") else f" ({'; '.join(gate.get('reasons',[]))})")
    legacy=d.get("algorithm_version")!="1.4"
    secs=[("ASSESSMENT",[("Assessment ID",d.get("assessment_id","-")),("Patient",f"{pat.get('name','-')} ({pat.get('patient_id',d.get('patient_id') or '-')})"),("Started",dt.datetime.fromtimestamp(d["started_at_epoch"]).strftime("%d %b %Y %H:%M") if d.get("started_at_epoch") else "-"),("App / algorithm",f"v{d.get('version','?')} / {d.get('algorithm_version','legacy (<=1.3)')}"),("Overall quality",q.get("overall_status","-")),("Tests passed",f"{q.get('tests_passed',0)} / {q.get('tests_evaluated',0)}  (skipped {q.get('tests_skipped',0)})")])]
    if legacy: secs[0][1].append(("Notice","Recorded with an older algorithm; not comparable with v1.4 and not used for baselines."))
    secs += [("SIT-TO-STAND",[("Quality",g(sts)),("Valid / total repetitions",f"{sts.get('valid_repetitions',0)} / {sts.get('repetitions',0)}"),("Knee ROM L / R (deg)",f"{sts.get('left_knee_rom_deg',0)} / {sts.get('right_knee_rom_deg',0)}"),("ROM symmetry",sts.get('knee_rom_symmetry_ratio',0)),("Mean rep time (s)",sts.get('average_rep_time_seconds',0)),("Mean rise time (s)",sts.get('average_rise_time_seconds',0)),("Rep-time CV",sts.get('rep_time_cv',0)),("Trunk compensation (deg)",sts.get('peak_trunk_compensation_deg',0)),("Smoothness",sts.get('movement_smoothness',0))]),
        ("GAIT",[("Quality",g(gait)),("Steps (L/R)",f"{gait.get('total_steps',0)} ({gait.get('left_steps',0)}/{gait.get('right_steps',0)})"),("Walking bout (s)",gait.get('walking_bout_seconds',gait.get('duration_seconds',0))),("Cadence (steps/min)",gait.get('cadence_steps_per_minute',0)),("Step-time symmetry",gait.get('left_right_step_balance',0)),("Step interval CV",gait.get('step_interval_cv',0)),("Knee ROM symmetry",gait.get('knee_rom_symmetry_ratio',0))]),
        ("BALANCE",[("Quality",g(bal)),("Sway RMS",bal.get('sway_rms',0)),("Path length",bal.get('sway_path_length',0)),("Mean velocity",bal.get('sway_velocity',0)),("95% ellipse area",bal.get('sway_ellipse_area_95','-')),("Max displacement",bal.get('max_displacement',0)),("Drift",bal.get('normalized_drift',0))]),
        ("SYMPTOM PROFILE (custom, non-validated)",[("Index",f"{qn.get('score',0)} / {qn.get('max_score',0)}")]+[(v.get('label',k),f"{v.get('score',0)} / {v.get('max_score',0)}") for k,v in qn.get('domains',{}).items()]),
        ("FINGERPRINT",[("Fused modalities",", ".join(fp.get('modality_fusion',{}).get('qualified_modalities',[])) or "none"),("Excluded",", ".join(fp.get('modality_fusion',{}).get('excluded_modalities',[])) or "none"),("Fusion quality",fp.get('quality',{}).get('fusion_quality','-')),("Evidence coverage",fp.get('quality',{}).get('fusion_coverage','-'))]),
        ("CHANGE VS BASELINE",[("Status",base.get('status','-')),("Reference",base.get('baseline_assessment_id') or "this assessment")]+[(k,f"{v['baseline']} -> {v['current']} ({_pct(v.get('percent_change'))})" + (" REVIEW" if v.get('exceeds_review_threshold') else "")) for k,v in base.get('changes',{}).items()])]
    return secs


def assessment_detail(d: dict) -> None:
    s=Screen("Assessment Details"); r=s.root
    head=tk.Frame(r,bg=BG); head.pack(fill="x",padx=24,pady=(12,4)); s.label(head,"Assessment details",22,bold=True).pack(side="left")
    overall=(d.get("assessment_quality") or {}).get("overall_status","-")
    tone={"PASS":GOOD,"PARTIAL":WARN,"REVIEW":WARN}.get(overall,MUTED)
    pill=tk.Frame(head,bg=PANEL2,padx=12,pady=5); pill.pack(side="right")
    tk.Label(pill,text="●",bg=PANEL2,fg=tone,font=(s.font,11,"bold")).pack(side="left")
    s.label(pill,f" {overall}",11,tone,True).pack(side="left")
    s.label(head,f"{d.get('assessment_id','-')}  |  {d.get('patient_snapshot',{}).get('patient_id','-')}   ",10,ACCENT,True).pack(side="right")
    mode=["report"]
    wrap=card_frame(r,FIELD,0,0); wrap.pack(fill="both",expand=True,padx=24,pady=6)
    text=tk.Text(wrap,bg=FIELD,fg=TEXT,relief="flat",bd=0,highlightthickness=0,font=(s.font,12),wrap="word",padx=18,pady=8,cursor="arrow",spacing1=2,spacing3=2); text.pack(fill="both",expand=True)
    text.tag_configure("h",foreground=ACCENT,background=PANEL2,font=(s.font,11,"bold"),spacing1=12,spacing3=6,lmargin1=10,lmargin2=10)
    text.tag_configure("row",lmargin1=12,lmargin2=300,tabs=("300",),spacing1=4,spacing3=4)
    text.tag_configure("k",foreground=MUTED)
    text.tag_configure("v",foreground=TEXT,font=(s.font,12,"bold"))
    text.tag_configure("good",foreground=GOOD,font=(s.font,12,"bold"))
    text.tag_configure("warn",foreground=WARN,font=(s.font,12,"bold"))
    text.tag_configure("m",foreground=MUTED,font=(s.font,10),spacing1=14)
    def fmt(v):
        return f"{v:.4f}" if isinstance(v,float) and abs(v)<1 else f"{v:.2f}" if isinstance(v,float) else str(v)
    def render():
        text.configure(state="normal",font=(s.mono,10) if mode[0]=="json" else (s.font,12)); text.delete("1.0","end")
        if mode[0]=="report":
            for title,rows in detail_sections(d):
                text.insert("end",title+"\n","h")
                for k,v in rows:
                    value=fmt(v); head=value.split(" ",1)[0]
                    vt="good" if head=="PASS" else "warn" if head in ("REVIEW","PARTIAL") else "v"
                    text.insert("end",str(k),("row","k")); text.insert("end","\t",("row",)); text.insert("end",value+"\n",("row",vt))
            text.insert("end","\n"+DISCLAIMER,"m")
        else: text.insert("1.0",json.dumps(d,indent=2,ensure_ascii=False))
        text.configure(state="disabled"); text.yview_moveto(0)
    render()
    # touch: drag the page to scroll; no text selection on a kiosk
    text.bind("<ButtonPress-1>", lambda e: (text.scan_mark(e.x,e.y),"break")[1])
    text.bind("<B1-Motion>", lambda e: (text.scan_dragto(e.x,e.y,gain=1),"break")[1])
    def up(): text.yview_scroll(-8,"units")
    def down(): text.yview_scroll(8,"units")
    def export():
        try: info_dialog("Report exported",f"Saved to:\n{export_report(d)}")
        except OSError as exc: error_dialog("Export failed",str(exc))
    s.nav(back=lambda:s.finish(None),extra=[("Report",lambda:(mode.__setitem__(0,"report"),render())),("Raw JSON",lambda:(mode.__setitem__(0,"json"),render())),("▲ Up",up),("▼ Down",down)],primary=export,primary_label="Export")
    r.bind("<Escape>", lambda _e: s.finish(None))
    s.run()


def history_screen() -> dict | None:
    """Touch-first patient hub with a compact profile, timeline and actions."""
    while True:
        s = Screen("Patient History")
        r = s.root
        patients = list_patients()
        selected = [None]
        sessions = []

        head = tk.Frame(r, bg=BG)
        head.pack(fill="x", padx=22, pady=(10, 3))
        s.label(head, "Patient history", 22, bold=True).pack(side="left")
        s.label(head, "Profiles  •  assessments  •  observed change", 9, MUTED).pack(side="right", pady=5)

        # Search row — deliberately separate from the patient list so the list never jumps.
        search = tk.Frame(r, bg=BG)
        search.pack(fill="x", padx=22, pady=(1, 5))
        s.label(search, "SEARCH", 10, ACCENT, True).pack(side="left", padx=(0, 8))
        q = tk.StringVar()
        ent = tk.Entry(search, textvariable=q, bg=FIELD, fg=TEXT, insertbackground=ACCENT,
                       relief="flat", font=(s.font, 12), highlightthickness=1,
                       highlightbackground=BORDER, highlightcolor=ACCENT)
        ent.pack(side="left", fill="x", expand=True, ipady=7)
        s.attach_entry(ent)
        s.label(search, f"{len(patients)} patient records", 10, MUTED).pack(side="right", padx=(10, 0))

        content = tk.Frame(r, bg=BG)
        content.pack(fill="both", expand=True, padx=22, pady=3)
        content.columnconfigure(0, weight=4)
        content.columnconfigure(1, weight=6)
        content.rowconfigure(0, weight=1)

        left = tk.Frame(content, bg=PANEL, padx=10, pady=8)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        right = tk.Frame(content, bg=PANEL, padx=14, pady=9)
        right.grid(row=0, column=1, sticky="nsew", padx=(5, 0))
        filtered = []
        ppage = [0]
        per = 4

        def clear(frame):
            for child in frame.winfo_children():
                child.destroy()

        def select_patient(p):
            selected[0] = p
            sessions[:] = list_sessions(p.get("patient_id"))
            render_patients()
            render_right()

        def render_patients(*_):
            query = q.get().strip().lower()
            filtered[:] = [
                p for p in patients
                if not query or query in f"{p.get('patient_id','')} {p.get('name','')}".lower()
            ]
            ppage[0] = min(ppage[0], max(0, (len(filtered) - 1) // per))
            clear(left)
            s.label(left, "PATIENTS", 10, ACCENT, True).pack(anchor="w", padx=4, pady=(0, 3))
            start = ppage[0] * per
            for p in filtered[start:start + per]:
                is_selected = selected[0] and p.get("patient_id") == selected[0].get("patient_id")
                bg = "#1f3b59" if is_selected else PANEL2
                f = tk.Frame(left, bg=bg, padx=9, pady=6,
                             highlightthickness=1 if is_selected else 0,
                             highlightbackground=ACCENT)
                f.pack(fill="x", pady=3)
                top = tk.Frame(f, bg=bg); top.pack(fill="x")
                s.label(top, p.get("name", "-"), 10, TEXT, True).pack(side="left")
                count = len(list_sessions(p.get("patient_id")))
                s.label(top, f"{count} test{'s' if count != 1 else ''}", 8,
                        ACCENT if count else MUTED, True).pack(side="right")
                s.label(f, f"{p.get('patient_id','-')}  •  Age {p.get('age','-')}  •  {p.get('sex','-')}",
                        7, MUTED).pack(anchor="w", pady=(2, 0))
                last = list_sessions(p.get("patient_id"))[:1]
                when = (dt.datetime.fromtimestamp(last[0].get("started_at_epoch", 0)).strftime("%d %b %Y")
                        if last and last[0].get("started_at_epoch") else "No assessment yet")
                s.label(f, f"Last assessment  {when}", 9, MUTED).pack(anchor="w", pady=(1, 0))
                for w in [f, *f.winfo_children(), *[c for ch in f.winfo_children() for c in ch.winfo_children()]]:
                    w.configure(cursor="hand2")
                    w.bind("<Button-1>", lambda _e, x=p: select_patient(x))
            if not filtered:
                s.label(left, "No matching patients.", 9, MUTED).pack(pady=24)
            shown_end = min(start + per, len(filtered))
            footer = f"Patients {start + 1 if filtered else 0}–{shown_end} of {len(filtered)}"
            s.label(left, footer, 9, MUTED).pack(anchor="w", pady=(2, 0))

        def render_right():
            clear(right)
            p = selected[0]
            if not p:
                s.label(right, "Choose a patient", 17, TEXT, True).pack(anchor="w", pady=(18, 2))
                s.label(right, "Tap a patient card to view the patient's timeline, quality and assessment details.",
                        9, MUTED, wraplength=430, justify="left").pack(anchor="w", pady=(0, 12))
                hint = tk.Frame(right, bg=PANEL2, padx=14, pady=12); hint.pack(fill="x")
                s.label(hint, "PATIENT WORKSPACE", 10, ACCENT, True).pack(anchor="w")
                s.label(hint, "Start a new assessment from the selected profile. Previous records stay local to this kiosk.",
                        8, MUTED, wraplength=410, justify="left").pack(anchor="w", pady=(4, 0))
                return

            # Profile header
            s.label(right, p.get("name", "-"), 17, TEXT, True).pack(anchor="w")
            s.label(right, f"{p.get('patient_id','-')}  •  Age {p.get('age','-')}  •  {p.get('sex','-')}",
                    8, MUTED).pack(anchor="w", pady=(1, 0))
            s.label(right,
                    f"Area: {p.get('symptomatic_area','-')}  •  OA history: {p.get('oa_history','-')}  •  Dominant: {p.get('dominant_side','-')}",
                    7, MUTED, wraplength=500).pack(anchor="w", pady=(2, 6))

            metrics = tk.Frame(right, bg=PANEL)
            metrics.pack(fill="x", pady=(0, 6))
            metrics.columnconfigure((0, 1, 2), weight=1)
            quality = (sessions[0].get("assessment_quality") or {}).get("overall_status", "—") if sessions else "—"
            last_date = (dt.datetime.fromtimestamp(sessions[0].get("started_at_epoch", 0)).strftime("%d %b %Y")
                         if sessions and sessions[0].get("started_at_epoch") else "—")
            for col, title, value, tone in (
                (0, "ASSESSMENTS", str(len(sessions)), ACCENT),
                (1, "LATEST QUALITY", quality, GOOD if quality == "PASS" else WARN if quality in ("REVIEW", "PARTIAL") else MUTED),
                (2, "LAST TEST", last_date, TEXT),
            ):
                box = tk.Frame(metrics, bg=PANEL2, padx=8, pady=5)
                box.grid(row=0, column=col, sticky="nsew", padx=2)
                s.label(box, title, 9, MUTED, True).pack(anchor="w")
                s.label(box, value, 10, tone, True).pack(anchor="w", pady=(2, 0))

            s.label(right, "ASSESSMENT TIMELINE", 10, MUTED, True).pack(anchor="w", pady=(1, 2))
            timeline = tk.Frame(right, bg=PANEL)
            timeline.pack(fill="both", expand=True)
            for sess in sessions[:3]:
                when = (dt.datetime.fromtimestamp(sess.get("started_at_epoch", 0)).strftime("%d %b %Y  •  %H:%M")
                        if sess.get("started_at_epoch") else "Unknown time")
                aq = (sess.get("assessment_quality") or {}).get("overall_status", "-")
                tests = (sess.get("assessment_quality") or {}).get("tests_passed", 0)
                te = (sess.get("assessment_quality") or {}).get("tests_evaluated", 0)
                tone = GOOD if aq == "PASS" else WARN if aq in ("REVIEW", "PARTIAL") else MUTED
                row = tk.Frame(timeline, bg=PANEL2, padx=8, pady=5)
                row.pack(fill="x", pady=2)
                leftrow = tk.Frame(row, bg=PANEL2); leftrow.pack(side="left", fill="x", expand=True)
                s.label(leftrow, when, 10, TEXT, True).pack(anchor="w")
                s.label(leftrow, f"{sess.get('assessment_id','-')}  •  {tests}/{te} tests", 9, MUTED).pack(anchor="w", pady=(1, 0))
                s.label(row, aq, 10, tone, True).pack(side="right", padx=(6, 8))
                s.button(row, "Details", lambda x=sess: assessment_detail(x), False, width=7).pack(side="right")
            if not sessions:
                empty = tk.Frame(timeline, bg=PANEL2, padx=12, pady=12); empty.pack(fill="x")
                s.label(empty, "No assessments recorded yet.", 9, MUTED).pack(anchor="w")
                s.label(empty, "Start an assessment to create the first movement record for this patient.",
                        7, MUTED).pack(anchor="w", pady=(3, 0))

            actions = tk.Frame(right, bg=PANEL)
            actions.pack(fill="x", pady=(6, 0))
            s.button(actions, "＋ Start Assessment", lambda: s.finish(selected[0]), True, width=15).pack(side="left")
            s.button(actions, "Export CSV", export_patient, False, width=10).pack(side="left", padx=6)

        def export_patient():
            if not selected[0]:
                return
            try:
                info_dialog("Patient export", f"Saved to:\n{export_features_csv(sessions)}")
            except OSError as exc:
                error_dialog("Export failed", str(exc))

        q.trace_add("write", render_patients)
        render_patients()
        render_right()

        def prev_page():
            ppage[0] = max(0, ppage[0] - 1)
            render_patients()

        def next_page():
            ppage[0] = min(max(0, (len(filtered) - 1) // per), ppage[0] + 1)
            render_patients()

        s.nav(back=lambda: s.finish(None),
              home=lambda: s.finish(None), extra=[("Previous", prev_page), ("Next", next_page)])
        r.bind("<Escape>", lambda _e: s.finish(None))
        result = s.run()
        if isinstance(result, dict):
            return result
        return None

