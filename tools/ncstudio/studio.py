"""NC Studio -- the Neon Coffee build environment.

A front end for `ncc`. Everything it does is also available from the command line;
this exists so the edit/build/run loop and the hardware budgets are visible at once.

Tkinter, deliberately: it ships with Python, so the GUI adds no dependency to a
project whose whole premise is a self-contained toolchain.
"""

import os
import queue
import subprocess
import sys
import threading
import tkinter as tk

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.join(_HERE, "..", "ncc"))

from theme import (AMBER, BG, BORDER, CYAN, DIM, FG, GREEN, MONO, MONO_SM, PANEL,
                   PANEL_HI, RED, SUNKEN, UI, UI_BOLD, Button, field, group)

from ncc import toolchain as tc
from ncc.targets import TARGETS


BANNER_TITLE = "NEON COFFEE ENGINE  ::  NC STUDIO"
BANNER_SUB = "PlayStation 1 / PlayStation 2 homebrew build environment"


def find_projects(root):
    """Any directory holding a CMakeLists.txt, at the root or under examples/."""
    found = []
    for base in (root, os.path.join(root, "examples")):
        if not os.path.isdir(base):
            continue
        for name in sorted(os.listdir(base)):
            p = os.path.join(base, name)
            if os.path.isdir(p) and os.path.isfile(os.path.join(p, "CMakeLists.txt")):
                found.append(p)
    return found


class Studio:
    def __init__(self, root):
        self.root = root
        self.repo = tc.project_root()
        self.q = queue.Queue()
        self.running = False
        self.projects = []

        root.title("NC Studio")
        root.configure(bg=BG)
        root.geometry("1040x660")
        root.minsize(880, 560)

        self._build_titlebar()

        main = tk.Frame(root, bg=BG)
        main.pack(fill="both", expand=True, padx=8, pady=(0, 6))

        left = tk.Frame(main, bg=BG, width=290)
        left.pack(side="left", fill="y", padx=(0, 8))
        left.pack_propagate(False)

        self._build_projects(left)
        self._build_target(left)
        self._build_actions(left)
        self._build_hardware(left)
        self._build_console(main)
        self._build_statusbar()

        self.refresh_projects()
        self.set_target("ps1")
        self.log(f"repo   {self.repo}", CYAN)
        self.log("ready. select a project and press BUILD + RUN.", DIM)
        self.check_toolchain()

        self.root.after(60, self._drain)

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
            highlightthickness=0, bd=0, activestyle="none")
        self.plist.pack(fill="x", padx=1, pady=1)
        self.plist.bind("<<ListboxSelect>>", lambda _: self.on_select())

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

    def _build_actions(self, parent):
        g = group(parent, "actions", CYAN)
        g.pack(fill="x", pady=(0, 6))
        body = tk.Frame(g.body, bg=PANEL)
        body.pack(fill="x", padx=6, pady=6)

        self.b_run = Button(body, "BUILD  +  RUN", lambda: self.run_ncc("run"), GREEN)
        self.b_run.pack(fill="x", pady=(0, 4))

        row = tk.Frame(body, bg=PANEL)
        row.pack(fill="x")
        self.b_build = Button(row, "BUILD", lambda: self.run_ncc("build"), AMBER,
                              width=9)
        self.b_build.pack(side="left")
        self.b_clean = Button(row, "CLEAN", lambda: self.run_ncc("clean"), DIM,
                              width=9)
        self.b_clean.pack(side="left", padx=4)
        self.b_doc = Button(row, "DOCTOR", self.check_toolchain, CYAN, width=9)
        self.b_doc.pack(side="left")

    def _build_hardware(self, parent):
        g = group(parent, "hardware profile", CYAN)
        g.pack(fill="both", expand=True)
        self.hw = tk.Frame(g.body, bg=PANEL)
        self.hw.pack(fill="both", expand=True, pady=6)

    def _build_console(self, parent):
        g = group(parent, "console", CYAN)
        g.pack(side="left", fill="both", expand=True)

        wrap = tk.Frame(g.body, bg=BORDER)
        wrap.pack(fill="both", expand=True, padx=6, pady=6)

        self.text = tk.Text(wrap, bg=SUNKEN, fg=FG, font=MONO, wrap="none",
                            highlightthickness=0, bd=0, padx=8, pady=6,
                            insertbackground=AMBER)
        sb = tk.Scrollbar(wrap, command=self.text.yview, bg=PANEL,
                          troughcolor=SUNKEN, bd=0, highlightthickness=0, width=12)
        self.text.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y", padx=(0, 1), pady=1)
        self.text.pack(side="left", fill="both", expand=True, padx=(1, 0), pady=1)

        for name, color in (("fg", FG), ("dim", DIM), ("amber", AMBER),
                            ("green", GREEN), ("red", RED), ("cyan", CYAN)):
            self.text.tag_configure(name, foreground=color)
        self.text.configure(state="disabled")

    def _build_statusbar(self):
        bar = tk.Frame(self.root, bg=PANEL_HI, height=22)
        bar.pack(fill="x", side="bottom")
        self.status = tk.Label(bar, text="ready", bg=PANEL_HI, fg=DIM,
                               font=MONO_SM, anchor="w", padx=8)
        self.status.pack(side="left", fill="x", expand=True)
        self.tcstat = tk.Label(bar, text="toolchain: ?", bg=PANEL_HI, fg=DIM,
                               font=MONO_SM, anchor="e", padx=8)
        self.tcstat.pack(side="right")

    # ---- state ----------------------------------------------------------

    def set_status(self, msg, color=DIM):
        self.status.configure(text=msg, fg=color)

    def set_target(self, key):
        self.target.set(key)
        for k, b in self.tbuttons.items():
            b.label.configure(fg=BG if k == key else AMBER,
                              bg=AMBER if k == key else PANEL_HI)
        self.show_hardware(key)
        if key == "ps2":
            self.log("PS2 backend is not implemented yet -- roadmap M6.", AMBER)

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
        self.projects = find_projects(self.repo)
        self.plist.delete(0, "end")
        for p in self.projects:
            self.plist.insert("end", "  " + os.path.relpath(p, self.repo))
        if self.projects:
            self.plist.selection_set(0)
            self.on_select()
        else:
            self.set_status("no projects found -- press NEW...", AMBER)

    def selected_project(self):
        sel = self.plist.curselection()
        if not sel:
            return None
        return self.projects[sel[0]]

    def on_select(self):
        p = self.selected_project()
        if p:
            self.set_status(os.path.relpath(p, self.repo))

    # ---- console --------------------------------------------------------

    def log(self, line, color=None):
        tag = {AMBER: "amber", GREEN: "green", RED: "red",
               CYAN: "cyan", DIM: "dim"}.get(color, "fg")
        self.text.configure(state="normal")
        self.text.insert("end", line.rstrip() + "\n", tag)
        self.text.see("end")
        self.text.configure(state="disabled")

    def _classify(self, line):
        low = line.lower()
        if "[missing]" in low or "error" in low or "failed" in low:
            return RED
        if "[ok]" in low or "  ok  " in low or "complete" in low:
            return GREEN
        if "[warn]" in low or "warning" in low or "note:" in low:
            return AMBER
        if line.startswith("  ") and "->" in line:
            return DIM
        return None

    def _drain(self):
        """Pump subprocess output from the worker thread into the Text widget."""
        try:
            while True:
                item = self.q.get_nowait()
                if item is None:
                    self.running = False
                    self.set_buttons(True)
                elif isinstance(item, tuple):
                    self.set_status(item[0], item[1])
                else:
                    self.log(item, self._classify(item))
        except queue.Empty:
            pass
        self.root.after(60, self._drain)

    def set_buttons(self, on):
        for b in (self.b_run, self.b_build, self.b_clean, self.b_doc):
            b.set_enabled(on)

    # ---- running ncc ----------------------------------------------------

    def _spawn(self, args, done_msg):
        env = os.environ.copy()
        env["PYTHONPATH"] = (os.path.join(self.repo, "tools", "ncc") + os.pathsep +
                             env.get("PYTHONPATH", ""))
        env["PYTHONUNBUFFERED"] = "1"

        def worker():
            code = -1
            try:
                p = subprocess.Popen(
                    [sys.executable, "-m", "ncc"] + args,
                    cwd=self.repo, env=env, stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT, text=True, bufsize=1,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                for line in p.stdout:
                    self.q.put(line)
                code = p.wait()
            except Exception as exc:  # noqa: BLE001 - surfaced in the console
                self.q.put("ncc failed to start: %s" % exc)
            if code == 0:
                self.q.put((done_msg, GREEN))
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
        rel = os.path.relpath(p, self.repo)
        self.log("")
        self.log("> ncc %s %s" % (cmd, rel), CYAN)
        self.set_status("%s %s ..." % (cmd, rel), AMBER)
        self._spawn([cmd, p], "%s %s" % (cmd, rel))

    def check_toolchain(self):
        if self.running:
            return
        self.log("")
        self.log("> ncc doctor", CYAN)
        self._spawn(["doctor", "--target", self.target.get()], "doctor")
        self.tcstat.configure(text="toolchain: checking", fg=AMBER)

        def later():
            if self.running:
                self.root.after(300, later)
                return
            ok = tc.locate("mipsel-none-elf-gcc")[0] and tc.locate("cmake")[0]
            bios = tc.find_openbios()
            if ok and bios:
                self.tcstat.configure(text="toolchain: OK", fg=GREEN)
            elif ok:
                self.tcstat.configure(text="toolchain: OK / no BIOS", fg=AMBER)
            else:
                self.tcstat.configure(text="toolchain: INCOMPLETE", fg=RED)

        self.root.after(300, later)

    def new_project(self):
        if self.running:
            return
        win = tk.Toplevel(self.root)
        win.title("New project")
        win.configure(bg=BG)
        win.transient(self.root)
        win.resizable(False, False)

        g = group(win, "new project", GREEN)
        g.pack(padx=10, pady=10)
        tk.Label(g.body, text="name", bg=PANEL, fg=DIM, font=MONO_SM,
                 anchor="w").pack(fill="x", padx=8, pady=(8, 2))
        wrap = tk.Frame(g.body, bg=BORDER)
        wrap.pack(fill="x", padx=8)
        entry = tk.Entry(wrap, bg=SUNKEN, fg=FG, font=MONO, bd=0,
                         highlightthickness=0, insertbackground=AMBER, width=30)
        entry.pack(fill="x", padx=1, pady=1, ipady=4, ipadx=4)
        entry.insert(0, "mygame")
        entry.focus_set()
        entry.select_range(0, "end")

        tk.Label(g.body, text="created under examples/", bg=PANEL, fg=DIM,
                 font=MONO_SM, anchor="w").pack(fill="x", padx=8, pady=(4, 0))

        def create():
            name = entry.get().strip()
            if not name:
                return
            dest = os.path.join(self.repo, "examples", name)
            win.destroy()
            self.log("")
            self.log("> ncc new %s" % name, CYAN)
            self._spawn(["new", name, dest], "new %s" % name)
            self.root.after(1500, self.refresh_projects)

        row = tk.Frame(g.body, bg=PANEL)
        row.pack(fill="x", padx=8, pady=8)
        Button(row, "CREATE", create, GREEN, width=10).pack(side="left")
        Button(row, "CANCEL", win.destroy, DIM, width=10).pack(side="left", padx=4)
        entry.bind("<Return>", lambda _: create())


def main():
    root = tk.Tk()
    Studio(root)
    root.mainloop()


if __name__ == "__main__":
    main()
