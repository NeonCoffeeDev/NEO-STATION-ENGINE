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


def style_ttk(root):
    """Drag ttk's combo boxes, tabs and entries into the same century as the rest.

    Tkinter's own widgets are drawn by hand above, but comboboxes and notebooks
    have no plain equivalent, so they arrive as native Windows controls: light
    grey boxes on a black panel. `clam` is the only stock theme that lets colours
    be set at all -- the Windows themes ignore them and draw from the OS -- so it
    is the base here.

    The dropdown *list* a combobox pops up is not a ttk widget; it is a Tk
    listbox the widget owns and never exposes, so it can only be reached through
    the option database. Without those four lines the box looks right until you
    click it and a white menu appears.
    """
    from tkinter import ttk
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        return style

    style.configure(".", background=PANEL, foreground=FG, font=UI,
                    bordercolor=BORDER, lightcolor=BORDER, darkcolor=BORDER,
                    focuscolor=AMBER)

    style.configure("TCombobox", fieldbackground=SUNKEN, background=PANEL_HI,
                    foreground=FG, arrowcolor=AMBER, bordercolor=BORDER,
                    lightcolor=BORDER, darkcolor=BORDER, insertcolor=AMBER,
                    padding=3)
    style.map("TCombobox",
              fieldbackground=[("readonly", SUNKEN), ("disabled", PANEL)],
              foreground=[("readonly", FG), ("disabled", DIM)],
              background=[("active", BORDER_HI)],
              arrowcolor=[("disabled", DIM)],
              selectbackground=[("readonly", SUNKEN)],
              selectforeground=[("readonly", FG)],
              bordercolor=[("focus", AMBER)])
    for option, value in (("Listbox.background", SUNKEN),
                          ("Listbox.foreground", FG),
                          ("Listbox.selectBackground", AMBER),
                          ("Listbox.selectForeground", BG),
                          ("Listbox.font", MONO_SM)):
        root.option_add("*TCombobox*" + option, value)

    style.configure("TNotebook", background=BG, borderwidth=0, tabmargins=(2, 2, 0, 0))
    style.configure("TNotebook.Tab", background=PANEL, foreground=DIM,
                    font=UI_BOLD, padding=(12, 5), borderwidth=0)
    style.map("TNotebook.Tab",
              background=[("selected", PANEL_HI), ("active", BORDER_HI)],
              foreground=[("selected", AMBER)])

    style.configure("TEntry", fieldbackground=SUNKEN, foreground=FG,
                    insertcolor=AMBER, bordercolor=BORDER, padding=3)
    style.map("TEntry", bordercolor=[("focus", AMBER)])

    style.configure("TFrame", background=PANEL)
    style.configure("Treeview", background=SUNKEN, fieldbackground=SUNKEN,
                    foreground=FG, rowheight=24, bordercolor=BORDER)
    style.map("Treeview", background=[("selected", AMBER)],
              foreground=[("selected", BG)])
    style.configure("Treeview.Heading", background=PANEL_HI, foreground=CYAN,
                    relief="flat")
    style.map("Treeview.Heading", background=[("active", BORDER_HI)])
    style.configure("TLabel", background=PANEL, foreground=FG, font=UI)
    style.configure("TLabelframe", background=PANEL, bordercolor=BORDER)
    style.configure("TLabelframe.Label", background=PANEL, foreground=CYAN, font=UI_BOLD)
    style.configure("TCheckbutton", background=PANEL, foreground=FG,
                    indicatorcolor=SUNKEN)
    style.map("TCheckbutton", indicatorcolor=[("selected", AMBER)],
              background=[("active", PANEL)])
    style.configure("Vertical.TScrollbar", background=PANEL_HI, troughcolor=SUNKEN,
                    bordercolor=BORDER, arrowcolor=DIM)
    return style


def entry(parent, **kw):
    """A plain Tk entry that matches the panel, for use outside ttk forms."""
    kw.setdefault("bg", SUNKEN)
    kw.setdefault("fg", FG)
    kw.setdefault("insertbackground", AMBER)
    kw.setdefault("relief", "flat")
    kw.setdefault("highlightthickness", 1)
    kw.setdefault("highlightbackground", BORDER)
    kw.setdefault("highlightcolor", AMBER)
    kw.setdefault("font", MONO_SM)
    return tk.Entry(parent, **kw)


def label(parent, text, fg=DIM, bg=PANEL, font=UI, **kw):
    return tk.Label(parent, text=text, bg=bg, fg=fg, font=font, anchor="w", **kw)


def dialog(parent, title, size):
    """A modal Toplevel already wearing the theme."""
    win = tk.Toplevel(parent)
    win.title(title)
    win.geometry(size)
    win.configure(bg=BG)
    win.transient(parent.winfo_toplevel())
    return win
