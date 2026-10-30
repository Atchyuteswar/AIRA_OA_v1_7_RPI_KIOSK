"""Single-window Tk shell plus a touch action bar for the camera workflow."""
from __future__ import annotations

import os
import queue
import tkinter as tk
import tkinter.font as tkfont
from typing import Optional

import cv2
from PIL import Image, ImageTk

from core.config import DISPLAY

KEY_ENTER, KEY_ESC, KEY_SPACE, KEY_BACKSPACE, KEY_TAB = 13, 27, 32, 8, 9
KEY_QUIT_WINDOW = 1000
KEY_HOME = 1001
BG = "#0b1020"
BAR_BG, BTN, BTN_HOVER = "#0f1a30", "#1a2a47", "#243a5e"
ACCENT, ACCENT_HOVER, ON_ACCENT = "#62d8ff", "#8be6ff", "#06121f"
DANGER_BG, DANGER_HOVER, DANGER_FG = "#3b2230", "#52293a", "#ff9aa6"
TOUCH_WIDTH, TOUCH_HEIGHT = 1024, 600
TOUCH_BAR_H = 64                 # must equal 600 - DisplayConfig.canvas_height in Pi mode
TOUCH_MODE = os.environ.get("AIRA_RPI_TOUCH", os.environ.get("AIRA_RPI", "0")) == "1"

_KEYMAP = {"Return": KEY_ENTER, "KP_Enter": KEY_ENTER, "Escape": KEY_ESC,
           "space": KEY_SPACE, "BackSpace": KEY_BACKSPACE, "Tab": KEY_TAB}


class Display:
    def __init__(self):
        self.root: Optional[tk.Tk] = None
        self.label: Optional[tk.Label] = None
        self._photo = None
        self._keys: "queue.Queue[int]" = queue.Queue()
        self._camera_mode = False
        self.closed = False
        self._touch_bar = None

    def get_root(self) -> tk.Tk:
        if self.root is None or not self._alive():
            self.root = tk.Tk()
            self.root.title("AIRA-OA | Movement Screening")
            self.root.configure(bg=BG)
            if TOUCH_MODE:
                self.root.geometry(f"{TOUCH_WIDTH}x{TOUCH_HEIGHT}")
                try: self.root.attributes("-fullscreen", True)
                except tk.TclError: pass
            else:
                self.root.minsize(900, 600)
            if os.environ.get("AIRA_RPI_FULLSCREEN", "0") == "1":
                try: self.root.attributes("-fullscreen", True)
                except tk.TclError: pass
            self.root.protocol("WM_DELETE_WINDOW", self._on_close)
            self.root.bind_all("<KeyPress>", self._on_key, add="+")
            self.closed = False
        return self.root

    def _alive(self):
        try: return bool(self.root is not None and self.root.winfo_exists())
        except tk.TclError: return False

    def _on_close(self):
        self.closed = True
        self._keys.put(KEY_QUIT_WINDOW)
        try: self.root.quit()
        except tk.TclError: pass

    def _on_key(self, event):
        if not self._camera_mode: return
        code = _KEYMAP.get(event.keysym)
        if code is None and event.char: code = ord(event.char.lower())
        if code is not None: self._keys.put(code)

    def close(self):
        if self._alive():
            try: self.root.destroy()
            except tk.TclError: pass
        self.root = None

    def enter_camera_mode(self):
        root = self.get_root()
        if self._camera_mode and self.label is not None and self.label.winfo_exists(): return
        for child in root.winfo_children(): child.destroy()
        root.title("AIRA-OA | Assessment")
        if TOUCH_MODE:
            root.geometry(f"{TOUCH_WIDTH}x{TOUCH_HEIGHT}")
            self.label = tk.Label(root, bg="black", bd=0, highlightthickness=0)
            self.label.place(x=0, y=0, relwidth=1, height=TOUCH_HEIGHT - TOUCH_BAR_H)
        else:
            root.geometry(f"{DISPLAY.canvas_width}x{DISPLAY.canvas_height}")
            self.label = tk.Label(root, bg="black", bd=0, highlightthickness=0)
            self.label.place(x=0, y=0, relwidth=1, relheight=1)
        self._camera_mode = True
        self._touch_bar = None
        self._drain()
        root.update()

    def exit_camera_mode(self):
        self._camera_mode = False
        self.label = None
        self._photo = None
        if self._touch_bar is not None:
            try: self._touch_bar.destroy()
            except tk.TclError: pass
        self._touch_bar = None
        self._drain()

    # words that make a touch action the primary / a cautionary one (whole words only,
    # so "Restart" is not mistaken for "Start")
    _PRIMARY = {"START", "CONTINUE", "ACCEPT", "FINISH", "DONE", "NEW", "SAVE"}
    _CAUTION = {"QUIT", "CANCEL"}

    def set_touch_actions(self, actions):
        if not TOUCH_MODE or not self._camera_mode or self.label is None: return
        if self._touch_bar is not None:
            try: self._touch_bar.destroy()
            except tk.TclError: pass
        bar = tk.Frame(self.root, bg=BAR_BG, bd=0, highlightthickness=0)
        bar.place(relx=0, rely=1.0, anchor="sw", relwidth=1.0, height=TOUCH_BAR_H)
        tk.Frame(bar, bg="#26406a", height=1).pack(side="top", fill="x")
        row = tk.Frame(bar, bg=BAR_BG); row.pack(fill="both", expand=True, padx=6, pady=6)
        self._touch_bar = bar
        fam = font_family()
        for i, (label, code) in enumerate(actions):
            words = set(str(label).upper().replace(".", " ").split())
            primary, caution = bool(words & self._PRIMARY), bool(words & self._CAUTION)
            bg, hover, fg = ((ACCENT, ACCENT_HOVER, ON_ACCENT) if primary else
                             (DANGER_BG, DANGER_HOVER, DANGER_FG) if caution else (BTN, BTN_HOVER, "#eef4ff"))
            b = tk.Button(row, text=label, command=lambda c=code: self._keys.put(c),
                          bg=bg, fg=fg, activebackground=hover, activeforeground=fg,
                          relief="flat", bd=0, highlightthickness=0, takefocus=0, cursor="hand2",
                          font=(fam, 11, "bold"))
            b.bind("<Enter>", lambda _e, w=b, h=hover: w.configure(bg=h))
            b.bind("<Leave>", lambda _e, w=b, c=bg: w.configure(bg=c))
            b.grid(row=0, column=i, sticky="nsew", padx=3)
            row.columnconfigure(i, weight=1, uniform="touch")
        row.rowconfigure(0, weight=1)

    def _drain(self):
        while True:
            try: self._keys.get_nowait()
            except queue.Empty: return

    def show(self, canvas_bgr):
        if not self._camera_mode or self.label is None: self.enter_camera_mode()
        try:
            w = max(320, self.label.winfo_width()); h = max(180, self.label.winfo_height())
            ch, cw = canvas_bgr.shape[:2]
            if (w, h) != (cw, ch):
                scale = min(w / cw, h / ch)
                canvas_bgr = cv2.resize(canvas_bgr, (max(2,int(cw*scale)), max(2,int(ch*scale))), interpolation=cv2.INTER_LINEAR)
            rgb = cv2.cvtColor(canvas_bgr, cv2.COLOR_BGR2RGB)
            self._photo = ImageTk.PhotoImage(image=Image.fromarray(rgb))
            self.label.configure(image=self._photo)
        except tk.TclError:
            self.closed = True

    def poll_key(self):
        if not self._alive(): return KEY_QUIT_WINDOW
        try:
            self.root.update_idletasks(); self.root.update()
        except tk.TclError:
            self.closed = True; return KEY_QUIT_WINDOW
        try: return self._keys.get_nowait()
        except queue.Empty: return -1


_DISPLAY: Optional[Display] = None

def get_display():
    global _DISPLAY
    if _DISPLAY is None: _DISPLAY = Display()
    return _DISPLAY

def get_root(): return get_display().get_root()

def font_family():
    root = get_root(); available = set(tkfont.families(root))
    for name in ("Noto Sans", "DejaVu Sans", "Arial", "Segoe UI", "Helvetica Neue"):
        if name in available: return name
    return "TkDefaultFont"

def mono_family():
    root = get_root(); available = set(tkfont.families(root))
    for name in ("DejaVu Sans Mono", "Noto Sans Mono", "Courier New"):
        if name in available: return name
    return "TkFixedFont"
