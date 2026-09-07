"""The NCScript editor built into NC Studio.

Why this exists: `.ncs` is a language no editor on earth knows. Opening it in
Notepad -- which is what the file association gave you -- means writing game
logic with no colour, no line numbers, and no way to get from "line 42: unknown
function" to line 42. That is the difference between a toy and something you can
work in.

The highlighter is not a parser. It colours what a reader needs to tell apart at
a glance -- keywords, the engine API, strings, numbers, comments -- and the real
compiler is one keypress away to tell you the truth. Its word lists come from
ncscript.py and ncscript_api.py directly, so the colours cannot drift from the
language the way a hand-copied list would.
"""

import os
import re
import tkinter as tk

from theme import (AMBER, BG, BORDER, CYAN, DIM, FG, GREEN, MONO, MONO_SM,
                   PANEL, PANEL_HI, RED, SUNKEN)

# The language, from the compiler rather than from memory.
try:
    from ncc.ncscript import KEYWORDS, BANNED
    from ncc.ncscript_api import FUNCTIONS, CONSTANTS
except ImportError:                     # pragma: no cover - Studio runs with ncc
    KEYWORDS, BANNED, FUNCTIONS, CONSTANTS = set(), {}, {}, {}

INDENT = "    "                          # NCScript is spaces only

WORD_RE = re.compile(r"[A-Za-z_][A-Za-z_0-9]*")
NUM_RE = re.compile(r"\b\d+\b")
STR_RE = re.compile(r'"[^"\n]*"')


class ScriptEditor(tk.Frame):
    """A text editor with a gutter, NCScript colours and an error marker."""

    def __init__(self, parent, on_save=None, on_run=None):
        super().__init__(parent, bg=BORDER)
        self.on_save = on_save
        self.on_run = on_run
        self.path = None
        self._dirty = False
        self._pending = None

        head = tk.Frame(self, bg=PANEL_HI)
        head.pack(fill="x", padx=1, pady=(1, 0))
        self.title = tk.Label(head, text=" NO SCRIPT OPEN ", bg=PANEL_HI,
                              fg=DIM, font=MONO_SM, anchor="w")
        self.title.pack(side="left", pady=2)
        self.hint = tk.Label(head, text="Ctrl+S save   F5 save + run  ",
                             bg=PANEL_HI, fg=DIM, font=MONO_SM, anchor="e")
        self.hint.pack(side="right", pady=2)

        body = tk.Frame(self, bg=BORDER)
        body.pack(fill="both", expand=True, padx=1, pady=(0, 1))

        # The gutter is a Text rather than a Canvas so it scrolls with the same
        # yview call and never drifts a pixel out of step.
        self.gutter = tk.Text(body, width=5, bg=PANEL, fg=DIM, font=MONO,
                              bd=0, highlightthickness=0, padx=4, pady=6,
                              takefocus=0, cursor="arrow", wrap="none")
        self.gutter.pack(side="left", fill="y")
        self.gutter.configure(state="disabled")

        self.text = tk.Text(body, bg=SUNKEN, fg=FG, font=MONO, wrap="none",
                            bd=0, highlightthickness=0, padx=8, pady=6,
                            insertbackground=AMBER, undo=True,
                            tabs=("2c",), selectbackground="#26333a")
        self.scroll = tk.Scrollbar(body, command=self._yview, bg=PANEL,
                                   troughcolor=SUNKEN, bd=0,
                                   highlightthickness=0, width=12)
        self.text.configure(yscrollcommand=self._on_scroll)
        self.scroll.pack(side="right", fill="y")
        self.text.pack(side="left", fill="both", expand=True)

        for name, colour in (("kw", AMBER), ("api", CYAN), ("const", GREEN),
                             ("num", GREEN), ("str", GREEN), ("com", DIM),
                             ("banned", RED), ("def", CYAN)):
            self.text.tag_configure(name, foreground=colour)
        self.text.tag_configure("errline", background="#3a1416")
        # Marks are drawn under everything else so an error stripe does not hide
        # the syntax colours on that line.
        self.text.tag_lower("errline")

        self.text.bind("<KeyRelease>", self._on_key)
        self.text.bind("<Control-s>", self._on_ctrl_s)
        self.text.bind("<Tab>", self._on_tab)
        self.text.bind("<Shift-Tab>", self._on_shift_tab)
        self.text.bind("<Return>", self._on_return)
        self.text.bind("<F5>", self._on_f5)
        self.text.bind("<Button-1>", lambda _e: self.after(1, self._clear_error))
        self.text.bind("<MouseWheel>", self._on_wheel)
        self.gutter.bind("<MouseWheel>", self._on_wheel)

        self.set_enabled(False)

    # ---- scrolling ------------------------------------------------------

    def _yview(self, *args):
        self.text.yview(*args)
        self.gutter.yview(*args)

    def _on_scroll(self, first, last):
        self.scroll.set(first, last)
        self.gutter.yview_moveto(first)

    def _on_wheel(self, event):
        delta = -1 * int(event.delta / 120)
        self.text.yview_scroll(delta, "units")
        self.gutter.yview_moveto(self.text.yview()[0])
        return "break"

    # ---- file -----------------------------------------------------------

    def load(self, path):
        try:
            with open(path, encoding="utf-8") as fh:
                content = fh.read()
        except OSError as exc:
            return str(exc)

        self.path = path
        self.set_enabled(True)
        self.text.delete("1.0", "end")
        self.text.insert("1.0", content)
        self.text.edit_reset()           # a fresh file has nothing to undo to
        self.text.mark_set("insert", "1.0")
        # Tk keeps the old scroll offset, which lands a newly opened file
        # halfway down at whatever line you were reading in the last one.
        self.text.yview_moveto(0)
        self._dirty = False
        self._refresh_title()
        self._highlight()
        self._gutter()
        return None

    def clear(self, why):
        """Empty the editor and say why, rather than leaving a stale file open.

        Showing the last project's script while a different project is selected
        is worse than showing nothing: it looks like it is the right file.
        """
        self.path = None
        self._dirty = False
        self.set_enabled(True)
        self.text.delete("1.0", "end")
        self.text.insert("1.0", "# %s\n" % why)
        self.text.edit_reset()
        self.set_enabled(False)
        self._highlight()
        self._gutter()
        self._refresh_title()

    def save(self):
        if not self.path:
            return False
        try:
            # Newline "" keeps the file's own line endings rather than
            # rewriting them; a diff full of line-ending noise helps nobody.
            with open(self.path, "w", encoding="utf-8", newline="") as fh:
                fh.write(self.text.get("1.0", "end-1c"))
        except OSError:
            return False
        self._dirty = False
        self._refresh_title()
        return True

    def is_dirty(self):
        return self._dirty

    def set_enabled(self, on):
        self.text.configure(state="normal" if on else "disabled")

    def _refresh_title(self):
        if not self.path:
            self.title.configure(text=" NO SCRIPT OPEN ", fg=DIM)
            return
        mark = " *" if self._dirty else ""
        self.title.configure(
            text=" %s%s " % (os.path.basename(self.path), mark),
            fg=AMBER if self._dirty else FG)

    # ---- editing --------------------------------------------------------

    def _on_key(self, event):
        if event.keysym in ("Up", "Down", "Left", "Right", "Home", "End",
                            "Prior", "Next", "Shift_L", "Shift_R",
                            "Control_L", "Control_R"):
            return
        if not self._dirty:
            self._dirty = True
            self._refresh_title()
        self._schedule()

    def _schedule(self):
        # Re-colouring the whole buffer on every keystroke is wasted work on a
        # file of any size, so it is deferred until typing pauses.
        if self._pending:
            self.after_cancel(self._pending)
        self._pending = self.after(120, self._recolour)

    def _recolour(self):
        self._pending = None
        self._highlight()
        self._gutter()

    def _on_ctrl_s(self, _event):
        if self.on_save:
            self.on_save()
        else:
            self.save()
        return "break"

    def _on_f5(self, _event):
        if self.on_run:
            self.on_run()
        return "break"

    def _on_tab(self, _event):
        # Spaces, never a tab character: the compiler rejects tabs outright,
        # and finding that out from a build error is a poor introduction.
        self.text.insert("insert", INDENT)
        self._schedule()
        return "break"

    def _on_shift_tab(self, _event):
        line = self.text.get("insert linestart", "insert lineend")
        strip = len(line) - len(line.lstrip(" "))
        if strip:
            n = min(len(INDENT), strip)
            self.text.delete("insert linestart", "insert linestart+%dc" % n)
        self._schedule()
        return "break"

    def _on_return(self, _event):
        line = self.text.get("insert linestart", "insert")
        indent = line[:len(line) - len(line.lstrip(" "))]
        # A block opener indents the next line for you, the way it does in any
        # editor that knows Python-shaped syntax.
        if line.rstrip().endswith(":"):
            indent += INDENT
        self.text.insert("insert", "\n" + indent)
        self.text.see("insert")
        self._schedule()
        return "break"

    # ---- highlighting ---------------------------------------------------

    def _gutter(self):
        total = int(self.text.index("end-1c").split(".")[0])
        self.gutter.configure(state="normal")
        self.gutter.delete("1.0", "end")
        self.gutter.insert("1.0", "\n".join("%4d" % n
                                            for n in range(1, total + 1)))
        self.gutter.configure(state="disabled")
        self.gutter.yview_moveto(self.text.yview()[0])

    def _highlight(self):
        source = self.text.get("1.0", "end-1c")
        for tag in ("kw", "api", "const", "num", "str", "com", "banned", "def"):
            self.text.tag_remove(tag, "1.0", "end")

        for lineno, line in enumerate(source.split("\n"), 1):
            # Comments first and then skip the rest of the line: a '#' inside a
            # string is not a comment, and a keyword inside a comment is not a
            # keyword. Handling the two in the wrong order colours both wrongly.
            comment = self._comment_start(line)
            body = line if comment is None else line[:comment]
            if comment is not None:
                self._tag("com", lineno, comment, len(line))

            for m in STR_RE.finditer(body):
                self._tag("str", lineno, m.start(), m.end())
            spans = [(m.start(), m.end()) for m in STR_RE.finditer(body)]

            for m in NUM_RE.finditer(body):
                if not self._inside(m.start(), spans):
                    self._tag("num", lineno, m.start(), m.end())

            for m in WORD_RE.finditer(body):
                if self._inside(m.start(), spans):
                    continue
                word = m.group(0)
                if word in BANNED:
                    tag = "banned"
                elif word in KEYWORDS:
                    tag = "kw"
                elif word in CONSTANTS:
                    tag = "const"
                elif word in FUNCTIONS:
                    tag = "api"
                elif body[:m.start()].strip() == "func":
                    tag = "def"          # the name of a function being defined
                else:
                    continue
                self._tag(tag, lineno, m.start(), m.end())

    @staticmethod
    def _comment_start(line):
        """Index of the '#' that starts a comment, or None.

        Scans for a quote first so a '#' inside a string literal is left alone.
        """
        in_string = False
        for i, ch in enumerate(line):
            if ch == '"':
                in_string = not in_string
            elif ch == "#" and not in_string:
                return i
        return None

    @staticmethod
    def _inside(pos, spans):
        return any(a <= pos < b for a, b in spans)

    def _tag(self, tag, lineno, start, end):
        self.text.tag_add(tag, "%d.%d" % (lineno, start),
                          "%d.%d" % (lineno, end))

    # ---- errors ---------------------------------------------------------

    def show_error(self, lineno):
        """Put the caret on the line the compiler complained about."""
        self._clear_error()
        if not self.path:
            return
        total = int(self.text.index("end-1c").split(".")[0])
        lineno = max(1, min(lineno, total))
        self.text.tag_add("errline", "%d.0" % lineno, "%d.end+1c" % lineno)
        self.text.mark_set("insert", "%d.0" % lineno)
        self.text.see("%d.0" % lineno)
        self.text.focus_set()

    def _clear_error(self):
        self.text.tag_remove("errline", "1.0", "end")
