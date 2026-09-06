"""NC Studio look: dark panel chrome, phosphor accents, monospace everything.

Mid-2000s tool UI means beveled group boxes, dense layout, small bold caps labels
and chunky bordered buttons. Tkinter's native widgets fight that, so most controls
here are built from Frames and Labels and drawn by hand.
"""

import tkinter as tk

# ---- palette -------------------------------------------------------------

BG        = "#0a0c0d"   # window ground
PANEL     = "#14181a"   # group box body
PANEL_HI  = "#1d2427"   # group box header strip
SUNKEN    = "#050708"   # log / inset areas
BORDER    = "#2e3639"
BORDER_HI = "#3f4a4e"

FG        = "#c3d0cc"
DIM       = "#6d7d79"
AMBER     = "#ffb03a"   # primary accent
GREEN     = "#7fd98c"   # success
RED       = "#ff6b5e"   # failure
CYAN      = "#5fd4d0"   # info / headings

# ---- fonts ---------------------------------------------------------------

MONO      = ("Consolas", 10)
MONO_SM   = ("Consolas", 9)
MONO_BOLD = ("Consolas", 10, "bold")
UI        = ("Tahoma", 8)
UI_BOLD   = ("Tahoma", 8, "bold")


def group(parent, title, accent=CYAN):
    """A beveled group box. Returns the body frame to pack children into."""
    outer = tk.Frame(parent, bg=BORDER, bd=0, highlightthickness=0)

    head = tk.Frame(outer, bg=PANEL_HI, height=18)
    head.pack(fill="x", padx=1, pady=(1, 0))
    tk.Label(head, text=f" {title.upper()} ", bg=PANEL_HI, fg=accent,
             font=UI_BOLD, anchor="w").pack(side="left", pady=1)

    body = tk.Frame(outer, bg=PANEL)
    body.pack(fill="both", expand=True, padx=1, pady=(0, 1))
    outer.body = body
    return outer


class Button(tk.Frame):
    """Flat bordered button with hover and pressed states."""

    def __init__(self, parent, text, command, accent=AMBER, width=None):
        super().__init__(parent, bg=BORDER, bd=0, highlightthickness=0)
        self.command = command
        self.accent = accent
        self._enabled = True

        self.label = tk.Label(self, text=text, bg=PANEL_HI, fg=accent,
                              font=UI_BOLD, pady=5, cursor="hand2")
        if width:
            self.label.configure(width=width)
        self.label.pack(fill="both", expand=True, padx=1, pady=1)

        self.label.bind("<Enter>", self._enter)
        self.label.bind("<Leave>", self._leave)
        self.label.bind("<Button-1>", self._press)
        self.label.bind("<ButtonRelease-1>", self._release)

    def _enter(self, _):
        if self._enabled:
            self.label.configure(bg=BORDER_HI)

    def _leave(self, _):
        if self._enabled:
            self.label.configure(bg=PANEL_HI)

    def _press(self, _):
        if self._enabled:
            self.label.configure(bg=self.accent, fg=BG)

    def _release(self, _):
        if not self._enabled:
            return
        self.label.configure(bg=BORDER_HI, fg=self.accent)
        self.command()

    def set_enabled(self, on):
        self._enabled = on
        self.label.configure(fg=self.accent if on else DIM,
                             bg=PANEL_HI if on else PANEL,
                             cursor="hand2" if on else "arrow")


def field(parent, key, value, value_color=FG):
    """One dense `key ....... value` row, the way old tools listed properties."""
    row = tk.Frame(parent, bg=PANEL)
    tk.Label(row, text=key, bg=PANEL, fg=DIM, font=MONO_SM,
             anchor="w", width=13).pack(side="left")
    val = tk.Label(row, text=value, bg=PANEL, fg=value_color, font=MONO_SM, anchor="w")
    val.pack(side="left", fill="x", expand=True)
    row.pack(fill="x", padx=6, pady=0)
    row.value_label = val
    return row
