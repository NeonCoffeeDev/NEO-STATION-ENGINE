"""NC Studio -- the Neon Coffee build environment.

A front end for `ncc`. Everything it does is also available from the command line;
this exists so the edit/build/run loop, the console, the PS1's TTY output and the
hardware budgets are all visible at once.

Tkinter, deliberately: it ships with Python, so the GUI adds no dependency to a
project whose whole premise is a self-contained toolchain.
"""

import json
import os
import queue
import re
import subprocess
import sys
import threading
import tkinter as tk

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.join(_HERE, "..", "ncc"))

from theme import (AMBER, BG, BORDER, CYAN, DIM, FG, GREEN, MONO, MONO_SM, PANEL,
                   PANEL_HI, RED, SUNKEN, UI, UI_BOLD, Button, field, group)
from editor import ScriptEditor

from ncc import toolchain as tc
from ncc.build import DEFAULT_TEMPLATE, list_templates
from ncc.targets import TARGETS


BANNER_TITLE = "NEON COFFEE ENGINE  ::  NC STUDIO"
BANNER_SUB = "PlayStation 1 / PlayStation 2 homebrew build environment"

# The console is a debugging tool, not an archive. Without a cap a long session
# of rebuilds grows the Text widget until redraws crawl.
MAX_LOG_LINES = 4000

# Drain at most this many queued lines per tick, so a noisy build cannot starve
# the event loop and freeze the window.
DRAIN_BUDGET = 300

SETTINGS_PATH = os.path.join(
    os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"),
    "NeonCoffee", "studio.json")


def load_settings():
    try:
        with open(SETTINGS_PATH, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def save_settings(data):
    try:
        os.makedirs(os.path.dirname(SETTINGS_PATH), exist_ok=True)
        with open(SETTINGS_PATH, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
    except OSError:
        pass          # settings are a convenience; never let them break startup


def find_projects(root):
    """Any directory holding a CMakeLists.txt, at the root or under examples/."""
    found = []
    for base in (root, os.path.join(root, "examples")):
        if not os.path.isdir(base):
            continue
        try:
            names = sorted(os.listdir(base))
        except OSError:
            continue
        for name in names:
            p = os.path.join(base, name)
            if os.path.isdir(p) and os.path.isfile(os.path.join(p, "CMakeLists.txt")):
                found.append(p)
    return found


def reveal(path):
    """Open a file or folder with whatever Windows associates with it."""
    try:
        os.startfile(path)  # noqa: S606 - intentional shell-open on Windows
        return True
    except (OSError, AttributeError):
        return False


class Studio:
    def __init__(self, root):
        self.root = root
        self.repo = tc.project_root()
        self.q = queue.Queue()
        self.running = False
        self.proc = None
        self.failed = False
        self.explain_on_fail = False
        self.projects = []
        self.settings = load_settings()
        self.autoscroll = tk.BooleanVar(value=self.settings.get("autoscroll", True))
        self.release = bool(self.settings.get("release", False))

        root.title("NC Studio")
        root.configure(bg=BG)
        root.geometry(self.settings.get("geometry", "1120x720"))
        root.minsize(940, 580)
        root.protocol("WM_DELETE_WINDOW", self.on_close)

        self._build_titlebar()

        main = tk.Frame(root, bg=BG)
        main.pack(fill="both", expand=True, padx=8, pady=(0, 6))

        left = tk.Frame(main, bg=BG, width=296)
        left.pack(side="left", fill="y", padx=(0, 8))
        left.pack_propagate(False)

        self._build_projects(left)
        self._build_target(left)
        self._build_actions(left)
        self._build_tools(left)
        self._build_hardware(left)
        self._build_output(main)
        self._build_statusbar()
        self._bind_keys()

        self.refresh_projects()
        self._sync_config_button()
        self.set_target(self.settings.get("target", "ps1"))
        self.log(f"repo   {self.repo}", CYAN)
        self.log("F5 build+run   F7 build   F8 check   F9 doctor   Ctrl+L clear",
                 DIM)
        self.check_toolchain()

        self._tty_pos = 0
        self.root.after(60, self._drain)
        self.root.after(1000, self._poll_tty)

    # ---- chrome ---------------------------------------------------------

    def _build_titlebar(self):
        bar = tk.Canvas(self.root, height=46, bg=BG, highlightthickness=0, bd=0)
        bar.pack(fill="x", padx=8, pady=(8, 6))

        def draw(_=None):
            bar.delete("all")
            w = bar.winfo_width() or 1000
            # Vertical gradient, the mid-2000s way.
            for i in range(46):
                v = int(20 + 14 * (1 - i / 45.0))
                bar.create_line(0, i, w, i, fill="#%02x%02x%02x" % (v, v + 3, v + 4))
            bar.create_line(0, 45, w, 45, fill=BORDER)
            bar.create_text(14, 14, text=BANNER_TITLE, anchor="w", fill=AMBER,
                            font=("Consolas", 13, "bold"))
            bar.create_text(15, 32, text=BANNER_SUB, anchor="w", fill=DIM, font=UI)
            bar.create_text(w - 14, 23, text="v0.0.1", anchor="e", fill=DIM,
                            font=MONO_SM)

        bar.bind("<Configure>", draw)
        draw()

    def _build_projects(self, parent):
        g = group(parent, "project", CYAN)
        g.pack(fill="x", pady=(0, 6))

        wrap = tk.Frame(g.body, bg=BORDER)
        wrap.pack(fill="x", padx=6, pady=6)
        self.plist = tk.Listbox(
            wrap, height=6, bg=SUNKEN, fg=FG, font=MONO_SM,
            selectbackground=AMBER, selectforeground=BG,
            highlightthickness=0, bd=0, activestyle="none", exportselection=False)
        self.plist.pack(fill="x", padx=1, pady=1)
        self.plist.bind("<<ListboxSelect>>", lambda _: self.on_select())
        self.plist.bind("<Double-Button-1>", lambda _: self.run_ncc("run"))

        row = tk.Frame(g.body, bg=PANEL)
        row.pack(fill="x", padx=6, pady=(0, 6))
        Button(row, "RESCAN", self.refresh_projects, CYAN).pack(side="left")
        Button(row, "NEW...", self.new_project, GREEN).pack(side="left", padx=(4, 0))

    def _build_target(self, parent):
        g = group(parent, "target", CYAN)
        g.pack(fill="x", pady=(0, 6))
        self.target = tk.StringVar(value="ps1")
        row = tk.Frame(g.body, bg=PANEL)
        row.pack(fill="x", padx=6, pady=6)
        self.tbuttons = {}
        for key, label in (("ps1", "PS1"), ("ps2", "PS2")):
            b = Button(row, label, lambda k=key: self.set_target(k), AMBER, width=8)
            b.pack(side="left", padx=(0, 4))
            self.tbuttons[key] = b

        # Debug is -Og and keeps every function separate, which is what you want
        # while iterating. Release is -O2 and inlines the script away.
        self.b_cfg = Button(row, "DEBUG", self.toggle_config, DIM, width=9)
        self.b_cfg.pack(side="right")

    def _build_actions(self, parent):
        g = group(parent, "actions", CYAN)
        g.pack(fill="x", pady=(0, 6))
        body = tk.Frame(g.body, bg=PANEL)
        body.pack(fill="x", padx=6, pady=6)

        self.b_run = Button(body, "BUILD  +  RUN     F5",
                            lambda: self.run_ncc("run"), GREEN)
        self.b_run.pack(fill="x", pady=(0, 4))

        row = tk.Frame(body, bg=PANEL)
        row.pack(fill="x")
        self.b_build = Button(row, "BUILD", lambda: self.run_ncc("build"), AMBER,
                              width=9)
        self.b_build.pack(side="left")
        self.b_clean = Button(row, "CLEAN", lambda: self.run_ncc("clean"), DIM,
                              width=9)
        self.b_clean.pack(side="left", padx=4)
        self.b_doc = Button(row, "CHECK", self.check_project, CYAN, width=9)
        self.b_doc.pack(side="left")

        self.b_stop = Button(body, "STOP", self.stop_running, RED)
        self.b_stop.pack(fill="x", pady=(4, 0))
        self.b_stop.set_enabled(False)

    def _build_tools(self, parent):
        g = group(parent, "open", CYAN)
        g.pack(fill="x", pady=(0, 6))
        body = tk.Frame(g.body, bg=PANEL)
        body.pack(fill="x", padx=6, pady=6)

        top = tk.Frame(body, bg=PANEL)
        top.pack(fill="x")
        Button(top, "script", self.open_script, AMBER, width=8).pack(side="left")
        Button(top, "scene", self.open_scene_json, CYAN, width=8).pack(side="left",
                                                                      padx=4)
        Button(top, "main.c", self.open_main, DIM, width=8).pack(side="left")

        row2 = tk.Frame(body, bg=PANEL)
        row2.pack(fill="x", pady=(4, 0))
        Button(row2, "FOLDER", self.open_folder, DIM, width=8).pack(side="left")
        Button(row2, "OUTPUT", self.open_output, DIM, width=8).pack(side="left",
                                                                   padx=4)
        # A project owns its copy of the runtime, so engine fixes do not reach
        # it on their own. This is the way back into step.
        Button(row2, "SYNC", lambda: self.run_ncc("sync"), DIM,
               width=8).pack(side="left")

        self.b_godot = Button(body, "EDIT SCENE IN GODOT", self.open_godot, GREEN)
        self.b_godot.pack(fill="x", pady=(4, 0))

    def _build_hardware(self, parent):
        g = group(parent, "hardware profile", CYAN)
        g.pack(fill="both", expand=True)
        self.hw = tk.Frame(g.body, bg=PANEL)
        self.hw.pack(fill="both", expand=True, pady=6)

    def _build_output(self, parent):
        outer = tk.Frame(parent, bg=BG)
        outer.pack(side="left", fill="both", expand=True)

        # Custom tab strip. ttk.Notebook cannot be themed convincingly on Windows.
        strip = tk.Frame(outer, bg=BG)
        strip.pack(fill="x")
        self.tabs = {}
        for key, label in (("console", "CONSOLE"), ("tty", "PS1 TTY"),
                           ("script", "SCRIPT")):
            lb = tk.Label(strip, text=f"  {label}  ", bg=PANEL, fg=DIM,
                          font=UI_BOLD, pady=4, cursor="hand2")
            lb.pack(side="left", padx=(0, 2))
            lb.bind("<Button-1>", lambda _e, k=key: self.show_tab(k))
            self.tabs[key] = lb

        ctl = tk.Frame(strip, bg=BG)
        ctl.pack(side="right")
        self.cb_scroll = tk.Checkbutton(
            ctl, text="autoscroll", variable=self.autoscroll, bg=BG, fg=DIM,
            selectcolor=SUNKEN, activebackground=BG, activeforeground=FG,
            font=UI, bd=0, highlightthickness=0)
        self.cb_scroll.pack(side="right", padx=(0, 6))
        Button(ctl, "CLEAR", self.clear_log, DIM).pack(side="right", padx=(0, 6))

        self.panes = tk.Frame(outer, bg=BG)
        self.panes.pack(fill="both", expand=True)

        self.text = self._make_pane()
        self.tty = self._make_pane()

        # The script editor is a pane like the others so the build output and
        # the source you are fixing share one window and one keyboard shortcut.
        self.editor = ScriptEditor(self.panes, on_save=self.save_script,
                                   on_run=self.save_and_run)
        self.editor.group = self.editor

        self.show_tab("console")

    def _make_pane(self):
        g = group(self.panes, "output", CYAN)
        wrap = tk.Frame(g.body, bg=BORDER)
        wrap.pack(fill="both", expand=True, padx=6, pady=6)

        txt = tk.Text(wrap, bg=SUNKEN, fg=FG, font=MONO, wrap="none",
                      highlightthickness=0, bd=0, padx=8, pady=6,
                      insertbackground=AMBER)
        sb = tk.Scrollbar(wrap, command=txt.yview, bg=PANEL, troughcolor=SUNKEN,
                          bd=0, highlightthickness=0, width=12)
        txt.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y", padx=(0, 1), pady=1)
        txt.pack(side="left", fill="both", expand=True, padx=(1, 0), pady=1)

        for name, color in (("fg", FG), ("dim", DIM), ("amber", AMBER),
                            ("green", GREEN), ("red", RED), ("cyan", CYAN)):
            txt.tag_configure(name, foreground=color)
        txt.configure(state="disabled")
        txt.group = g
        return txt

    def _build_statusbar(self):
        bar = tk.Frame(self.root, bg=PANEL_HI, height=22)
        bar.pack(fill="x", side="bottom")
        self.status = tk.Label(bar, text="ready", bg=PANEL_HI, fg=DIM,
                               font=MONO_SM, anchor="w", padx=8)
        self.status.pack(side="left", fill="x", expand=True)
        self.tcstat = tk.Label(bar, text="toolchain: ?", bg=PANEL_HI, fg=DIM,
                               font=MONO_SM, anchor="e", padx=8)
        self.tcstat.pack(side="right")

    def _bind_keys(self):
        self.root.bind("<F5>", lambda _: self.run_ncc("run"))
        self.root.bind("<F7>", lambda _: self.run_ncc("build"))
        self.root.bind("<Shift-F7>", lambda _: self.run_ncc("clean"))
        self.root.bind("<F8>", lambda _: self.check_project())
        self.root.bind("<F9>", lambda _: self.check_toolchain())
        self.root.bind("<Control-l>", lambda _: self.clear_log())
        self.root.bind("<Control-n>", lambda _: self.new_project())
        self.root.bind("<Escape>", lambda _: self.stop_running())

    # ---- tabs -----------------------------------------------------------

    def show_tab(self, key):
        self.active_tab = key
        for k, lb in self.tabs.items():
            on = k == key
            lb.configure(bg=PANEL_HI if on else PANEL, fg=AMBER if on else DIM)
        for k, w in (("console", self.text), ("tty", self.tty),
                     ("script", self.editor)):
            if k == key:
                w.group.pack(fill="both", expand=True)
            else:
                w.group.pack_forget()
        if key == "script":
            self.editor.text.focus_set()

    # ---- state ----------------------------------------------------------

    def set_status(self, msg, color=DIM):
        self.status.configure(text=msg, fg=color)

    def set_target(self, key):
        if key not in TARGETS:
            key = "ps1"
        self.target.set(key)
        for k, b in self.tbuttons.items():
            b.label.configure(fg=BG if k == key else AMBER,
                              bg=AMBER if k == key else PANEL_HI)
        self.show_hardware(key)
        if key == "ps2":
            self.log("PS2 backend is not implemented yet -- roadmap M6.", AMBER)

    def toggle_config(self):
        if self.running:
            return
        self.release = not self.release
        self._sync_config_button()
        self.log("build configuration: %s"
                 % ("Release (-O2)" if self.release else "Debug (-Og)"), CYAN)

    def _sync_config_button(self):
        if self.release:
            self.b_cfg.label.configure(text="RELEASE", fg=BG, bg=GREEN)
            self.b_cfg.accent = GREEN
        else:
            self.b_cfg.label.configure(text="DEBUG", fg=DIM, bg=PANEL_HI)
            self.b_cfg.accent = DIM

    def show_hardware(self, key):
        for w in self.hw.winfo_children():
            w.destroy()
        t = TARGETS[key]
        rows = [
            ("resolution", "%d x %d" % (t.width, t.height)),
            ("ram", "%d KB" % (t.ram_bytes // 1024)),
            ("vram", "%d KB" % (t.vram_bytes // 1024)),
            ("max texture", "%d px" % t.max_texture),
            ("color", ", ".join("%db" % d for d in t.color_depths)),
            ("fpu", "yes" if t.has_fpu else "no / fixed 20.12"),
            ("output", t.executable),
        ]
        for k, v in rows:
            field(self.hw, k, v, FG if key == "ps1" else DIM)

    def refresh_projects(self):
        want = self.selected_project() or self.settings.get("project")
        self.projects = find_projects(self.repo)
        self.plist.delete(0, "end")
        for p in self.projects:
            self.plist.insert("end", "  " + os.path.relpath(p, self.repo))
        if not self.projects:
            self.set_status("no projects found -- press NEW...", AMBER)
            return
        idx = self.projects.index(want) if want in self.projects else 0
        self.plist.selection_clear(0, "end")
        self.plist.selection_set(idx)
        self.plist.see(idx)
        self.on_select()

    def selected_project(self):
        sel = self.plist.curselection()
        if not sel or sel[0] >= len(self.projects):
            return None
        return self.projects[sel[0]]

    def on_select(self):
        p = self.selected_project()
        if p:
            self.set_status(os.path.relpath(p, self.repo))
        self.sync_editor()

    def sync_editor(self):
        """Keep the SCRIPT tab showing the selected project's script.

        Without this the editor keeps whatever was opened first, so switching
        projects in the list leaves you editing the previous game's logic --
        which is a good way to build one project while reading another.
        """
        p = self.selected_project()
        if not p:
            self.editor.clear("no project selected")
            return

        path = os.path.join(p, "script.ncs")
        if self.editor.path == path:
            return

        if self.editor.is_dirty() and self.editor.path:
            self.editor.save()
            self.log("saved %s before switching project."
                     % os.path.basename(self.editor.path), DIM)

        if not os.path.isfile(path):
            self.editor.clear("%s has no script.ncs"
                              % os.path.basename(p))
            return

        err = self.editor.load(path)
        if err:
            self.log("could not open %s: %s" % (path, err), RED)

    # ---- open buttons ---------------------------------------------------

    def open_script(self):
        """script.ncs -- the game logic, for projects that have one.

        It opens in the SCRIPT tab rather than in whatever Windows associates
        with .ncs, which is nothing. Editing the game in the same window that
        shows the build output and the console's TTY is the whole point.
        """
        p = self.selected_project()
        if not p:
            return
        path = os.path.join(p, "script.ncs")
        if not os.path.isfile(path):
            self.log("this project has no script.ncs.", AMBER)
            self.log("create one with:  ncc new <name> -t game", DIM)
            return

        self.sync_editor()
        if self.editor.path != path:
            return
        self.show_tab("script")
        self.set_status("editing %s" % os.path.relpath(path, self.repo), CYAN)

    def save_script(self):
        if not self.editor.path:
            return False
        if self.editor.save():
            self.set_status("saved %s" % os.path.basename(self.editor.path),
                            GREEN)
            return True
        self.log("could not write %s" % self.editor.path, RED)
        return False

    def save_and_run(self):
        """F5 from inside the editor: save first, then the usual build+run."""
        if self.editor.path:
            self.save_script()
        self.run_ncc("run")

    def open_scene_json(self):
        p = self.selected_project()
        if not p:
            return
        path = os.path.join(p, "scene.json")
        if not os.path.isfile(path):
            self.log("this project has no scene.json (its geometry is in C).",
                     AMBER)
            return
        reveal(path)

    def open_main(self):
        p = self.selected_project()
        if not p:
            return
        main_c = os.path.join(p, "src", "main.c")
        if not reveal(main_c):
            self.log(f"could not open {main_c}", RED)

    def open_folder(self):
        p = self.selected_project()
        if p:
            reveal(p)

    def open_output(self):
        p = self.selected_project()
        if not p:
            return
        d, _ = tc.build_dir_for(p, "Release" if self.release else "Debug")
        if os.path.isdir(d):
            reveal(d)
        else:
            self.log("no build output yet -- build first.", AMBER)

    def open_godot(self):
        """Open this project's Godot frontend, if it has one."""
        p = self.selected_project()
        if not p:
            self.log("no project selected.", RED)
            return

        proj = os.path.join(p, "godot", "project.godot")
        if not os.path.isfile(proj):
            self.log("this project has no Godot frontend.", AMBER)
            self.log("create one with:  ncc new <name> -t data", DIM)
            return

        godot = tc.find_godot()
        if not godot:
            self.log("Godot not found. Install it with:", RED)
            self.log("  winget install GodotEngine.GodotEngine", DIM)
            return

        self.log("opening %s in Godot" % os.path.relpath(proj, self.repo), CYAN)
        self.log("arrange the scene, press 'Export to NC', then F5 here.", DIM)
        try:
            # cwd is the godot folder, never the project root, so the editor
            # does not hold a lock on the project directory.
            subprocess.Popen([godot, "--editor", "--path",
                              os.path.join(p, "godot")],
                             cwd=os.path.join(p, "godot"))
        except OSError as exc:
            self.log("could not launch Godot: %s" % exc, RED)

    # ---- console --------------------------------------------------------

    def _target_pane(self):
        return self.tty if self.active_tab == "tty" else self.text

    def clear_log(self):
        w = self._target_pane()
        w.configure(state="normal")
        w.delete("1.0", "end")
        w.configure(state="disabled")

    def log(self, line, color=None, widget=None):
        self._write(widget or self.text, [(line, color)])

    def _write(self, widget, items):
        """Append many lines in one pass.

        Toggling widget state and calling see() per line is what makes a Tk
        console crawl during a noisy build, so both happen once per batch.
        """
        if not items:
            return
        widget.configure(state="normal")
        for line, color in items:
            tag = {AMBER: "amber", GREEN: "green", RED: "red",
                   CYAN: "cyan", DIM: "dim"}.get(color, "fg")
            widget.insert("end", line.rstrip() + "\n", tag)

        # Trim from the top so the widget cannot grow without bound.
        excess = int(widget.index("end-1c").split(".")[0]) - MAX_LOG_LINES
        if excess > 0:
            widget.delete("1.0", "%d.0" % (excess + 1))

        if self.autoscroll.get():
            widget.see("end")
        widget.configure(state="disabled")

    def _classify(self, line):
        low = line.lower()
        if line.lstrip().startswith("[X]") or "PROBLEMS" in line:
            return RED
        if line.lstrip().startswith("[!]") or "WARNINGS" in line:
            return AMBER
        if "fix:" in low:
            return CYAN
        if "[missing]" in low or "error" in low or "failed" in low:
            return RED
        if "[ok]" in low or "  ok  " in low or "complete" in low:
            return GREEN
        if "[warn]" in low or "warning" in low or "note:" in low:
            return AMBER
        if line.startswith("  ") and "->" in line:
            return DIM
        return None

    # The transpiler says: ncc: script.ncs -- line 23: ...   and ncc check
    # repeats it in its problem list. Both are worth catching.
    SCRIPT_ERROR_RE = re.compile(r"script\.ncs\D*?line (\d+)", re.I)

    def _catch_script_error(self, line):
        """Turn a compiler complaint into a caret on the offending line.

        The transpiler already reports "script.ncs: line 42: ...". Reading that,
        switching windows and counting down to line 42 by hand is the part worth
        removing.
        """
        m = self.SCRIPT_ERROR_RE.search(line)
        if not m:
            return
        p = self.selected_project()
        if not p:
            return
        path = os.path.join(p, "script.ncs")
        if not os.path.isfile(path):
            return
        if self.editor.path != path and not self.editor.is_dirty():
            self.editor.load(path)
        if self.editor.path != path:
            return
        lineno = int(m.group(1))
        self.root.after(60, lambda: self._goto_error(lineno))

    def _goto_error(self, lineno):
        self.show_tab("script")
        self.editor.show_error(lineno)

    def _drain(self):
        """Pump subprocess output from the worker thread into the console."""
        batch = []
        try:
            for _ in range(DRAIN_BUDGET):
                item = self.q.get_nowait()
                if item is None:
                    self.running = False
                    self.proc = None
                    self.set_buttons(True)
                    if self.failed and self.explain_on_fail:
                        # A failed build is exactly when someone wants to know
                        # what is too big, so run the checker without being
                        # asked.
                        self.explain_on_fail = False
                        self.root.after(50, self.explain_failure)
                elif isinstance(item, tuple):
                    self.set_status(item[0], item[1])
                else:
                    batch.append((item, self._classify(item)))
                    self._catch_script_error(item)
        except queue.Empty:
            pass
        if batch:
            self._write(self.text, batch)
        self.root.after(60, self._drain)

    def _poll_tty(self):
        """Tail DuckStation's log for the PS1's own printf output.

        With no debugger on the console, TTY is the main way a homebrew program
        can tell you anything, so it gets its own pane.
        """
        try:
            d = tc.duckstation_data_dir()
            path = os.path.join(d, "duckstation.log") if d else None
            if path and os.path.isfile(path):
                size = os.path.getsize(path)
                if size < self._tty_pos:      # log was rotated or truncated
                    self._tty_pos = 0
                if size > self._tty_pos:
                    with open(path, encoding="utf-8", errors="replace") as fh:
                        fh.seek(self._tty_pos)
                        chunk = fh.read()
                        self._tty_pos = fh.tell()
                    lines = [ln.split("I/TTY:", 1)[1].strip()
                             for ln in chunk.splitlines() if "I/TTY:" in ln]
                    if lines:
                        self._write(self.tty, [(ln, GREEN) for ln in lines])
        except OSError:
            pass
        self.root.after(1000, self._poll_tty)

    def set_buttons(self, on):
        for b in (self.b_run, self.b_build, self.b_clean, self.b_doc):
            b.set_enabled(on)
        self.b_stop.set_enabled(not on)

    # ---- running ncc ----------------------------------------------------

    def stop_running(self):
        if not self.running or not self.proc:
            return
        self.log("stopping...", AMBER)
        try:
            self.proc.terminate()
        except OSError:
            pass

    def _spawn(self, args, done_msg, explain_on_fail=False):
        env = os.environ.copy()
        env["PYTHONPATH"] = (os.path.join(self.repo, "tools", "ncc") + os.pathsep +
                             env.get("PYTHONPATH", ""))
        env["PYTHONUNBUFFERED"] = "1"

        self.explain_on_fail = explain_on_fail

        def worker():
            code = -1
            try:
                p = subprocess.Popen(
                    [sys.executable, "-m", "ncc"] + args,
                    cwd=self.repo, env=env, stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT, text=True, bufsize=1,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                self.proc = p
                for line in p.stdout:
                    self.q.put(line)
                code = p.wait()
            except Exception as exc:  # noqa: BLE001 - surfaced in the console
                self.q.put("ncc failed to start: %s" % exc)
            self.failed = code != 0 and code > 0
            if code == 0:
                self.q.put((done_msg, GREEN))
            elif code < 0:
                self.q.put(("%s -- stopped" % done_msg, AMBER))
            else:
                self.q.put(("%s -- FAILED (exit %d)" % (done_msg, code), RED))
            self.q.put(None)

        self.running = True
        self.set_buttons(False)
        threading.Thread(target=worker, daemon=True).start()

    def run_ncc(self, cmd):
        if self.running:
            return
        if self.target.get() == "ps2" and cmd in ("build", "run"):
            self.log("PS2 has no backend yet. Switch to PS1.", RED)
            return
        p = self.selected_project()
        if not p:
            self.log("no project selected.", RED)
            return
        self.show_tab("console")
        rel = os.path.relpath(p, self.repo)
        argv = [cmd, p]
        if self.release and cmd in ("build", "run"):
            argv.append("--release")
        shown = " ".join(["ncc", cmd, rel] + (["--release"] if len(argv) > 2 else []))
        self.log("")
        self.log("> " + shown, CYAN)
        self.set_status("%s %s ..." % (cmd, rel), AMBER)
        self._spawn(argv, "%s %s" % (cmd, rel),
                    explain_on_fail=cmd in ("build", "run"))

    def explain_failure(self):
        p = self.selected_project()
        if not p or self.running:
            return
        self.log("")
        self.log("--- checking what went wrong ---", AMBER)
        self._spawn(["check", p], "check")

    def check_project(self):
        if self.running:
            return
        p = self.selected_project()
        if not p:
            self.log("no project selected.", RED)
            return
        self.show_tab("console")
        self.log("")
        self.log("> ncc check %s" % os.path.relpath(p, self.repo), CYAN)
        self._spawn(["check", p], "check")

    def check_toolchain(self):
        if self.running:
            return
        self.show_tab("console")
        self.log("")
        self.log("> ncc doctor", CYAN)
        self._spawn(["doctor", "--target", self.target.get()], "doctor")
        self.tcstat.configure(text="toolchain: checking", fg=AMBER)
        self.root.after(300, self._update_toolchain_badge)

    def _update_toolchain_badge(self):
        if self.running:
            self.root.after(300, self._update_toolchain_badge)
            return
        ok = tc.locate("mipsel-none-elf-gcc")[0] and tc.locate("cmake")[0]
        if ok and tc.find_openbios():
            self.tcstat.configure(text="toolchain: OK", fg=GREEN)
        elif ok:
            self.tcstat.configure(text="toolchain: OK / no BIOS", fg=AMBER)
        else:
            self.tcstat.configure(text="toolchain: INCOMPLETE", fg=RED)

    # ---- new project ----------------------------------------------------

    def new_project(self):
        if self.running:
            return
        templates = list_templates()
        if not templates:
            self.log("no templates found.", RED)
            return

        win = tk.Toplevel(self.root)
        win.title("New project")
        win.configure(bg=BG)
        win.transient(self.root)
        win.resizable(False, False)
        win.grab_set()

        g = group(win, "new project", GREEN)
        g.pack(padx=10, pady=10)

        tk.Label(g.body, text="name", bg=PANEL, fg=DIM, font=MONO_SM,
                 anchor="w").pack(fill="x", padx=8, pady=(8, 2))
        wrap = tk.Frame(g.body, bg=BORDER)
        wrap.pack(fill="x", padx=8)
        entry = tk.Entry(wrap, bg=SUNKEN, fg=FG, font=MONO, bd=0,
                         highlightthickness=0, insertbackground=AMBER, width=42)
        entry.pack(fill="x", padx=1, pady=1, ipady=4, ipadx=4)
        entry.insert(0, "mygame")
        entry.focus_set()
        entry.select_range(0, "end")

        tk.Label(g.body, text="template", bg=PANEL, fg=DIM, font=MONO_SM,
                 anchor="w").pack(fill="x", padx=8, pady=(10, 2))

        chosen = tk.StringVar(value=DEFAULT_TEMPLATE)
        detail = tk.Label(g.body, text="", bg=PANEL, fg=DIM, font=MONO_SM,
                          anchor="w", justify="left", wraplength=380)

        rows = {}

        def select(name):
            chosen.set(name)
            for n, (frame, title, desc) in rows.items():
                on = n == name
                frame.configure(bg=PANEL_HI if on else PANEL)
                title.configure(bg=PANEL_HI if on else PANEL,
                                fg=AMBER if on else FG)
                desc.configure(bg=PANEL_HI if on else PANEL,
                               fg=FG if on else DIM)
            meta = next(t for t in templates if t["name"] == name)
            detail.configure(text=meta.get("detail", ""))

        for t in templates:
            f = tk.Frame(g.body, bg=PANEL, cursor="hand2")
            f.pack(fill="x", padx=8, pady=1)
            title = tk.Label(f, text=" %-9s %s" % (t["name"], t["title"]),
                             bg=PANEL, fg=FG, font=MONO_SM, anchor="w")
            title.pack(fill="x")
            desc = tk.Label(f, text="   " + t.get("description", ""), bg=PANEL,
                            fg=DIM, font=MONO_SM, anchor="w")
            desc.pack(fill="x")
            rows[t["name"]] = (f, title, desc)
            for w in (f, title, desc):
                w.bind("<Button-1>", lambda _e, n=t["name"]: select(n))

        detail.pack(fill="x", padx=8, pady=(8, 0))
        tk.Label(g.body, text="created under examples/", bg=PANEL, fg=DIM,
                 font=MONO_SM, anchor="w").pack(fill="x", padx=8, pady=(8, 0))

        select(DEFAULT_TEMPLATE)

        def create():
            name = entry.get().strip()
            if not name:
                return
            dest = os.path.join(self.repo, "examples", name)
            if os.path.exists(dest) and os.listdir(dest):
                self.log("examples/%s already exists and is not empty." % name, RED)
                win.destroy()
                return
            win.destroy()
            self.show_tab("console")
            self.log("")
            self.log("> ncc new %s -t %s" % (name, chosen.get()), CYAN)
            self._spawn(["new", name, dest, "-t", chosen.get()], "new %s" % name)
            self._pending_select = dest
            self.root.after(400, self._refresh_when_idle)

        row = tk.Frame(g.body, bg=PANEL)
        row.pack(fill="x", padx=8, pady=8)
        Button(row, "CREATE", create, GREEN, width=10).pack(side="left")
        Button(row, "CANCEL", win.destroy, DIM, width=10).pack(side="left", padx=4)
        entry.bind("<Return>", lambda _: create())
        win.bind("<Escape>", lambda _: win.destroy())

    def _refresh_when_idle(self):
        """Rescan once `ncc new` has actually finished, rather than on a timer."""
        if self.running:
            self.root.after(200, self._refresh_when_idle)
            return
        dest = getattr(self, "_pending_select", None)
        self.refresh_projects()
        if dest and dest in self.projects:
            i = self.projects.index(dest)
            self.plist.selection_clear(0, "end")
            self.plist.selection_set(i)
            self.plist.see(i)
            self.on_select()
        self._pending_select = None

    # ---- shutdown -------------------------------------------------------

    def on_close(self):
        if self.running and self.proc:
            try:
                self.proc.terminate()
            except OSError:
                pass
        self.settings.update({
            "geometry": self.root.geometry(),
            "target": self.target.get(),
            "project": self.selected_project() or "",
            "autoscroll": bool(self.autoscroll.get()),
            "release": self.release,
        })
        save_settings(self.settings)
        self.root.destroy()


def main():
    root = tk.Tk()
    Studio(root)
    root.mainloop()


if __name__ == "__main__":
    main()
