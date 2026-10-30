"""Touch-only interaction helpers for the 7-inch 1024x600 AIRA-OA kiosk."""
from __future__ import annotations

import tkinter as tk
from typing import Callable, Optional

from core.display import TOUCH_MODE, font_family

BG = "#0b1020"
KB_BG = "#0e1730"
KEY, KEY_HOVER = "#1c2d4d", "#2a4373"
KEY_SPECIAL, KEY_SPECIAL_HOVER = "#142340", "#1f3560"
PANEL2 = "#182b47"
TEXT = "#eef4ff"
ACCENT, ACCENT_HOVER, ON_ACCENT = "#62d8ff", "#8be6ff", "#06121f"
MUTED = "#91a0ba"


class TouchKeyboard:
    """Large, predictable on-screen keyboard for touch-first Entry widgets."""

    ALPHA_ROWS = [list("1234567890"), list("qwertyuiop"), list("asdfghjkl"), list("zxcvbnm")]
    NUMERIC_ROWS = [list("12345"), list("67890")]

    def __init__(self, root: tk.Tk):
        self.root = root
        self.frame: Optional[tk.Frame] = None
        self.target: Optional[tk.Entry] = None
        self.numeric = False
        self.shift = False
        self.font = font_family()
        self._next_callback: Optional[Callable[[], None]] = None

    def attach(self, entry: tk.Entry, numeric: bool = False, next_callback: Callable[[], None] | None = None):
        self.target = entry
        self.numeric = bool(numeric)
        self.shift = False
        self._next_callback = next_callback
        self.show()
        try:
            entry.focus_set()
        except tk.TclError:
            pass

    def show(self):
        if self.frame is None or not self.frame.winfo_exists():
            self.frame = tk.Frame(self.root, bg=KB_BG, bd=0, highlightthickness=1, highlightbackground="#2b4670",
                                  padx=6, pady=6)
            # Keep the keyboard inside the 600px kiosk viewport and leave enough
            # space for the active field/form above it.
            height = 232 if TOUCH_MODE else 240
            self.frame.place(relx=0.5, rely=1.0, anchor="s", relwidth=1.0, height=height)
        self._render()

    def hide(self):
        if self.frame is not None:
            try:
                self.frame.destroy()
            except tk.TclError:
                pass
        self.frame = None
        self.target = None
        self._next_callback = None

    def _insert(self, value: str):
        if self.target is None:
            return
        try:
            self.target.insert(tk.INSERT, value)
            self.target.focus_set()
        except tk.TclError:
            pass

    def _backspace(self):
        if self.target is None:
            return
        try:
            pos = int(self.target.index(tk.INSERT))
            if pos > 0:
                self.target.delete(pos - 1, pos)
            self.target.focus_set()
        except tk.TclError:
            pass

    def _clear(self):
        if self.target is not None:
            try:
                self.target.delete(0, "end")
                self.target.focus_set()
            except tk.TclError:
                pass

    def _next(self):
        cb = self._next_callback
        if cb:
            cb()

    def _toggle_shift(self):
        self.shift = not self.shift
        self._render()

    def _key(self, label, command, cols, row, col, kind="key"):
        """One key on the 20-column grid (a letter spans 2 columns)."""
        if kind == "primary":
            bg, hover, fg = ACCENT, ACCENT_HOVER, ON_ACCENT
        elif kind == "special":
            bg, hover, fg = KEY_SPECIAL, KEY_SPECIAL_HOVER, TEXT
        else:
            bg, hover, fg = KEY, KEY_HOVER, TEXT
        size = 14 if kind == "key" else 11
        b = tk.Button(self.frame, text=label, command=command, bg=bg, fg=fg,
                      activebackground=hover, activeforeground=fg, relief="flat", bd=0,
                      highlightthickness=0, takefocus=0, cursor="hand2",
                      font=(self.font, size, "bold"))
        b.bind("<Enter>", lambda _e, w=b, h=hover: w.configure(bg=h))
        b.bind("<Leave>", lambda _e, w=b, c=bg: w.configure(bg=c))
        b.grid(row=row, column=col, columnspan=cols, sticky="nsew", padx=3, pady=3)
        return b

    def _render(self):
        if self.frame is None:
            return
        for child in self.frame.winfo_children():
            child.destroy()
        for i in range(8):                                  # forget the previous layout's rows
            self.frame.rowconfigure(i, weight=0, uniform="", minsize=0)
        cols = 20
        ins = lambda v: (lambda: self._insert(v))

        if self.numeric:
            # Centred 5x2 keypad (each key spans 3 of 20 columns) plus a control row.
            for ri, row in enumerate(self.NUMERIC_ROWS):
                for ci, value in enumerate(row):
                    self._key(value, ins(value), 3, ri, 2 + ci * 3)
            base = len(self.NUMERIC_ROWS)
            for label, cmd, kind, col in (("⌫", self._backspace, "special", 0), ("CLEAR", self._clear, "special", 5),
                                          ("NEXT", self._next, "primary", 10), ("DONE", self.hide, "primary", 15)):
                self._key(label, cmd, 5, base, col, kind)
        else:
            rows = self.ALPHA_ROWS
            offsets = (0, 0, 1, 3)                    # a-l indented half a key, z-m a key and a half
            for ri, row in enumerate(rows):
                for ci, value in enumerate(row):
                    shown = value.upper() if self.shift and value.isalpha() else value
                    self._key(shown, ins(shown), 2, ri, offsets[ri] + ci * 2)
            # shift and backspace flank the bottom letter row
            self._key("⇧", self._toggle_shift, 3, 3, 0, "primary" if self.shift else "special")
            self._key("⌫", self._backspace, 3, 3, 17, "special")
            base = len(rows)
            for label, cmd, kind, span, col in (("CLEAR", self._clear, "special", 3, 0),
                                                ("SPACE", ins(" "), "key", 9, 3),
                                                ("NEXT", self._next, "primary", 4, 12),
                                                ("DONE", self.hide, "primary", 4, 16)):
                self._key(label, cmd, span, base, col, kind)
            base += 0
        for i in range(cols):
            self.frame.columnconfigure(i, weight=1, uniform="k")
        for i in range(base + 1):
            self.frame.rowconfigure(i, weight=1, uniform="r")
