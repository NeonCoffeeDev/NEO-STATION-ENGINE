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
from pathlib import Path
from tkinter import filedialog

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.join(_HERE, "..", "ncc"))

from theme import (AMBER, BG, BORDER, CYAN, DIM, FG, GREEN, MONO, MONO_SM, PANEL,
                   PANEL_HI, RED, SUNKEN, UI, UI_BOLD, Button, field, group,
                   style_ttk)
from editor import ScriptEditor
from scenepanel import ScenePanel
from designpanel import DesignPanel
from roompanel import RoomPanel
from kitpanel import KitPanel
from flowpanel import FlowPanel
from assetpanel import AssetPanel
from structurepanel import StructurePanel
from viewportpanel import GamePanel, ViewportPanel
from sidebars import AuthorSidebar, InspectorSidebar, TabStack

from ncc import toolchain as tc
from ncc import assets
from ncc.build import DEFAULT_TEMPLATE, list_templates, project_meta
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

def safe_geometry(root,value):
    """Keep saved multi-monitor coordinates from hiding editor sidebars."""
    match=re.fullmatch(r'(\d+)x(\d+)([+-]\d+)([+-]\d+)',str(value or ''))
    if not match:return '1500x900+40+40'
    width,height,x,y=map(int,match.groups())
    screen_w,screen_h=root.winfo_screenwidth(),root.winfo_screenheight()
    width=max(1180,min(width,screen_w));height=max(700,min(height,screen_h-60))
    x=max(0,min(x,screen_w-width));y=max(0,min(y,screen_h-height-40))
    return '%dx%d+%d+%d'%(width,height,x,y)


def find_projects(root):
    """Any Neon Coffee project, at the root or under examples/.

    A PS1 project is a CMake project and a PS2 project is a Makefile one, so
    nc.json is what identifies both."""
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
            if not os.path.isdir(p):
                continue
            if (os.path.isfile(os.path.join(p, "CMakeLists.txt"))
                    or os.path.isfile(os.path.join(p, "nc.json"))):
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
        self.fullscreen = False
        self.hub_visible = True
        self.windowed_geometry = None
        # Set before anything builds: the project list and the tab strip are
        # both filtered by it.
        self.mode = self.settings.get("mode", "all")
        self.autoscroll = tk.BooleanVar(value=self.settings.get("autoscroll", True))
        self.release = bool(self.settings.get("release", False))

        root.title("NC Studio")
        root.configure(bg=BG)
        root.geometry(safe_geometry(root,self.settings.get("geometry", "1500x900+40+40")))
        root.minsize(1180, 700)
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        style_ttk(root)     # before any ttk widget is built

        self._build_titlebar()
        workspace = tk.Frame(root, bg=PANEL)
        workspace.pack(fill="x", padx=8, pady=(0, 6))
        Button(workspace, "PROJECT HUB", self.toggle_hub, CYAN).pack(side="left")
        Button(workspace, "FULLSCREEN  F11", self.toggle_fullscreen, DIM).pack(side="right")
        self.workspace_name = tk.Label(workspace, text="Select a project", bg=PANEL,
                                       fg=AMBER, font=MONO_SM)
        self.workspace_name.pack(side="left", padx=10)
        root.bind("<F11>", lambda e: self.toggle_fullscreen())
        root.bind("<Escape>", lambda e: self.toggle_fullscreen() if self.fullscreen else None)

        main = tk.PanedWindow(root, orient='horizontal', bg=BORDER, sashwidth=7,
                              sashrelief='raised', bd=0)
        main.pack(fill="both", expand=True, padx=8, pady=(0, 6))

        left = tk.Frame(main, bg=BG, width=270)
        left.pack_propagate(False)
        center = tk.Frame(main, bg=BG)
        right = tk.Frame(main, bg=BG, width=306)
        right.pack_propagate(False)
        main.add(left,minsize=220,width=270,stretch='never')
        main.add(center,minsize=500,stretch='always')
        main.add(right,minsize=250,width=306,stretch='never')

        self.right_tabs = TabStack(right, {"system":"SYSTEM",
                                           "inspector":"COMPONENTS / INSPECTOR"})
        self.right_tabs.pack(fill="both", expand=True)
        system = self.right_tabs.tabs['system'][1]
        inspector_holder = self.right_tabs.tabs['inspector'][1]
        self._build_projects(system)
        self._build_target(system)
        self._build_actions(system)
        self._build_tools(system)
        self._build_assets(system)
        self._build_hardware(system)
        self._build_output(center)
        self.author_sidebar = AuthorSidebar(left, self.open_flow_from_sidebar,
                                            self.select_from_hierarchy,self.add_ready_object)
        self.author_sidebar.pack(fill="both", expand=True)
        self.inspector = InspectorSidebar(inspector_holder, self.apply_inspector, self.choose_sprite_image)
        self.inspector.pack(fill="both", expand=True)
        self.viewport_panel.on_selection = self.on_viewport_selection
        self._build_statusbar()
        self._bind_keys()

        self._sync_config_button()
        self.set_target(self.settings.get("target", "ps1"))
        self.set_mode(self.mode)      # filters the list, then selects into it
        self.log(f"repo   {self.repo}", CYAN)
        self.log("F5 build+run   F7 build   F8 check   F9 doctor   Ctrl+L clear",
                 DIM)
        self.check_toolchain()

        self._tty_pos = 0
        self._data_stamp = None
        self.root.after(60, self._drain)
        self.root.after(1000, self._poll_tty)
        self.root.after(1200, self._poll_project_data)

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
        self.project_hub = g
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
        g = group(parent, "mode", CYAN)
        g.pack(fill="x", pady=(0, 6))
        self.target = tk.StringVar(value="ps1")
        row = tk.Frame(g.body, bg=PANEL)
        row.pack(fill="x", padx=6, pady=6)
        self.tbuttons = {}
        # The mode switch sections the whole window. PS1 and PS2 are different
        # machines with different runtimes, different asset rules and different
        # tools; showing both at once is how you end up editing NCScript for a
        # game that has no script, or reading a PS1 TTY that will never speak.
        for key, label in (("all", "ALL"), ("ps1", "PS1"), ("ps2", "PS2")):
            b = Button(row, label, lambda k=key: self.set_mode(k), AMBER, width=6)
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
        Button(body, "PROJECT WALKTHROUGH", self.open_walkthrough, CYAN).pack(fill="x", pady=(4, 0))

    def _build_assets(self, parent):
        g = group(parent, "add asset", CYAN)
        g.pack(fill="x", pady=(0, 6))
        body = tk.Frame(g.body, bg=PANEL)
        body.pack(fill="x", padx=6, pady=6)

        hint = tk.Label(body, text="Copied in and registered in scene.json.",
                        bg=PANEL, fg=DIM, font=UI, anchor="w")
        hint.pack(fill="x", pady=(0, 4))

        row = tk.Frame(body, bg=PANEL)
        row.pack(fill="x")
        Button(row, "TEXTURE", lambda: self.add_asset("texture"), AMBER,
               width=9).pack(side="left")
        Button(row, "SOUND", lambda: self.add_asset("sound"), AMBER,
               width=8).pack(side="left", padx=4)
        Button(row, "MUSIC", lambda: self.add_asset("music"), AMBER,
               width=8).pack(side="left")

    def add_asset(self, kind):
        """Pick a file and add it, reporting refusals in the console.

        The checks run here rather than at build time. Being told a 512x512 PNG
        is too big when you add it, with the limit and the reason, is worth more
        than being told twenty minutes later in a build log.
        """
        from tkinter import filedialog

        p = self.selected_project()
        if not p:
            self.log("no project selected.", RED)
            return
        if project_meta(p)["target"] != "ps1":
            self.log("assets are a PS1 runtime feature; a PS2 project owns its "
                     "own main.c.", AMBER)
            return

        types = {"texture": [("PNG image", "*.png")],
                 "sound": [("WAV audio", "*.wav")],
                 "music": [("WAV audio", "*.wav")]}[kind]
        path = filedialog.askopenfilename(
            title="Add a %s to %s" % (kind, os.path.basename(p)),
            filetypes=types + [("All files", "*.*")])
        if not path:
            return

        self.show_tab("console")
        self.log("")
        self.log("> ncc add %s %s" % (kind, os.path.basename(path)), CYAN)
        try:
            name, rel = assets.add(p, kind, path)
        except Exception as exc:
            for line in str(exc).split(chr(10)):
                self.log("  " + line.strip(), RED)
            self.set_status("%s rejected" % kind, RED)
            return

        self.log("  added %s '%s' -> %s" % (kind, name, rel), GREEN)
        got = assets.listing(p)
        if kind == "sound":
            self.log("  play it with:  play_sound(%d)" % (len(got["sounds"]) - 1),
                     DIM)
        elif kind == "music":
            self.log("  play it with:  play_music(%d)" % (len(got["music"]) + 1),
                     DIM)
        else:
            self.log("  use it with:  \"texture\": \"%s\"" % name, DIM)
        self.set_status("added %s '%s'" % (kind, name), GREEN)
        if getattr(self, "scene_panel", None):
            self.scene_panel.load(p, force=True)

    def _build_hardware(self, parent):
        g = group(parent, "hardware profile", CYAN)
        g.pack(fill="both", expand=True)
        self.hw = tk.Frame(g.body, bg=PANEL)
        self.hw.pack(fill="both", expand=True, pady=6)

    def _build_output(self, parent):
        outer = tk.Frame(parent, bg=BG)
        outer.pack(side="left", fill="both", expand=True)

        split = tk.PanedWindow(outer, orient="vertical", bg=BORDER, sashwidth=7)
        split.pack(fill="both", expand=True)
        top = tk.Frame(split, bg=BG)
        bottom = tk.Frame(split, bg=BG)
        split.add(top, minsize=180, stretch="always")
        split.add(bottom, minsize=140, height=240)
        topstrip = tk.Frame(top, bg=BG)
        topstrip.pack(fill="x")
        self.main_panes = tk.Frame(top, bg=BG)
        self.main_panes.pack(fill="both", expand=True)
        # Custom tab strip. ttk.Notebook cannot be themed convincingly on Windows.
        strip = tk.Frame(bottom, bg=BG)
        strip.pack(fill="x")
        self.tabs = {}
        for key in self.TAB_ORDER:
            lb = tk.Label(topstrip if key in ("room", "flow", "structure", "viewport", "game") else strip, text="  %s  " % self.TAB_LABELS[key], bg=PANEL,
                          fg=DIM, font=UI_BOLD, pady=4, cursor="hand2")
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

        self.panes = tk.Frame(bottom, bg=BG)
        self.panes.pack(fill="both", expand=True)

        self.text = self._make_pane()
        self.tty = self._make_pane()

        # The script editor is a pane like the others so the build output and
        # the source you are fixing share one window and one keyboard shortcut.
        self.editor = ScriptEditor(self.panes, on_save=self.save_script,
                                   on_run=self.save_and_run)
        self.editor.group = self.editor

        # The scene drawer: assets, scenes in order, and the objects in each.
        # Until there is a viewport in the manager this is the closest thing to
        # one, and it is where draw order and asset indices are visible at all.
        self.scene_panel = ScenePanel(self.panes, on_log=self.log,
                                      on_add=self.add_asset)
        self.scene_panel.group = self.scene_panel
        self.design_panel = DesignPanel(self.panes, self.log, self.open_godot)
        self.room_panel = RoomPanel(self.main_panes, self.log)
        self.flow_panel = FlowPanel(self.main_panes)
        self.flow_panel.on_back = lambda: self.show_tab("structure")
        self.structure_panel = StructurePanel(self.main_panes,self.open_stage_events)
        self.viewport_panel = ViewportPanel(self.main_panes)
        self.game_panel = GamePanel(self.main_panes,self.viewport_panel)
        self.asset_panel = AssetPanel(self.panes)
        self.kit_panel = KitPanel(self.panes)

        self.show_tab("console")
        self.show_tab("viewport")

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
        self.root.bind("<Escape>", lambda _: self.toggle_fullscreen()
                       if self.fullscreen else self.stop_running())

    # ---- tabs -----------------------------------------------------------

    def show_tab(self, key):
        self.active_tab = key
        for k, lb in self.tabs.items():
            if (k in ("room", "flow", "structure", "viewport", "game")) != (key in ("room", "flow", "structure", "viewport", "game")):
                continue
            on = k == key
            lb.configure(bg=PANEL_HI if on else PANEL, fg=AMBER if on else DIM)
        for k, w in (("console", self.text), ("tty", self.tty),
                     ("script", self.editor), ("layers", self.scene_panel), ("design", self.design_panel), ("room", self.room_panel), ("kits", self.kit_panel), ("flow", self.flow_panel), ("assets", self.asset_panel), ("structure", self.structure_panel), ("viewport", self.viewport_panel), ("game", self.game_panel)):
            if (k in ("room", "flow", "structure", "viewport", "game")) != (key in ("room", "flow", "structure", "viewport", "game")):
                continue
            if k == key:
                w.group.pack(fill="both", expand=True)
            else:
                w.group.pack_forget()
        if key == "structure":
            self.structure_panel.load(self.selected_project())
        if key == "viewport":
            self.viewport_panel.load(self.selected_project())
        if key == "game":
            self.game_panel.load(self.selected_project())
        if key == "assets":
            self.asset_panel.load(self.selected_project())
        if key == "flow":
            self.flow_panel.load(self.selected_project())
        if key == "kits":
            self.kit_panel.load(self.selected_project())
        if key == "script":
            self.editor.text.focus_set()
        elif key == "room":
            self.room_panel.load(self.selected_project(), force=not self.room_panel.dirty)
        elif key == "design":
            self.design_panel.load(self.selected_project())
        elif key == "layers":
            self.scene_panel.load(self.selected_project())
        if getattr(self,"author_sidebar",None):self.update_author_context()

    # ---- state ----------------------------------------------------------

    def set_status(self, msg, color=DIM):
        self.status.configure(text=msg, fg=color)

    # Which console each tab belongs to. ROOM and CONSOLE are common ground;
    # everything else is specific to one machine's toolchain.
    TAB_ORDER = ("console", "tty", "script", "layers", "design", "room", "kits", "flow", "assets", "structure", "viewport", "game")
    TAB_LABELS = {"console": "CONSOLE", "tty": "PS1 TTY", "script": "SCRIPT",
                  "layers": "LAYERS", "design": "DESIGN", "room": "GAMEOBJECT", "kits": "KITS", "flow": "EVENTS", "assets": "ASSETS", "structure": "GAME FLOW", "viewport": "SCENE", "game": "GAME"}
    TAB_TARGETS = {"console": ("ps1", "ps2"), "tty": ("ps1",), "script": ("ps1",),
                   "layers": ("ps1",), "design": ("ps2",), "room": ("ps1", "ps2"), "kits": ("ps1", "ps2"), "flow": ("ps1", "ps2"), "assets": ("ps1", "ps2"), "structure": ("ps1", "ps2"), "viewport": ("ps1", "ps2"), "game": ("ps1", "ps2")}

    def set_mode(self, key):
        """Filter the manager down to one console, or open it up to both.

        This only changes what you can see and reach. The build target still
        comes from the selected project, so a project can never be built for the
        wrong machine because a button was left on the wrong setting.
        """
        self.mode = key if key in ("all", "ps1", "ps2") else "all"
        self.settings["mode"] = self.mode
        save_settings(self.settings)
        for k, b in self.tbuttons.items():
            on = k == self.mode
            b.label.configure(fg=BG if on else AMBER,
                              bg=AMBER if on else PANEL_HI)
        self.refresh_projects()
        self._sync_tabs()

    def effective_target(self):
        """The console the window is currently about."""
        if self.mode in ("ps1", "ps2"):
            return self.mode
        return self.target.get()

    def _sync_tabs(self):
        """Show only the tabs that mean something for this console."""
        target = self.effective_target()
        visible = [k for k in self.TAB_ORDER
                   if target in self.TAB_TARGETS.get(k, ("ps1", "ps2"))]
        for key in self.TAB_ORDER:
            self.tabs[key].pack_forget()
        for key in visible:
            self.tabs[key].pack(side="left", padx=(0, 2))
        if getattr(self, "active_tab", None) not in visible and visible:
            self.show_tab(visible[0])

    def set_target(self, key, from_project=False):
        if key not in TARGETS:
            key = "ps1"
        changed = self.target.get() != key
        self.target.set(key)
        self.show_hardware(key)
        self._sync_tabs()
        self._sync_target_buttons(key)
        if key == "ps2" and (changed or not from_project):
            self.log("PlayStation 2: builds a real .elf. The NC runtime itself "
                     "is still PS1-only -- roadmap M6.", AMBER)
            self.log("  run it from a USB stick on a FreeMcBoot console; PCSX2 "
                     "needs a BIOS you dump yourself.", DIM)
        elif key not in self.BUILDABLE and (changed or not from_project):
            self.log("%s: no backend yet -- roadmap M6." % TARGETS[key].name,
                     AMBER)

    # Targets ncc can actually build today. PS2 joined this list when the
    # toolchain landed; the list exists so the manager never has to guess.
    BUILDABLE = ("ps1", "ps2")

    def _sync_target_buttons(self, key):
        """Grey out what cannot work for this target.

        A BUILD button that always fails is worse than one that is visibly
        unavailable: the first looks like a bug in your project.
        """
        buildable = key in self.BUILDABLE
        for b in (self.b_run, self.b_build, self.b_doc):
            b.set_enabled(buildable and not self.running)

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
        found = find_projects(self.repo)
        self.projects = [p for p in found
                         if self.mode == "all"
                         or project_meta(p)["target"] == self.mode]
        self.plist.delete(0, "end")
        for p in self.projects:
            # Tag the machine. With two targets in one list, which console a
            # project is for stops being obvious from its name alone.
            tag = project_meta(p)["target"].upper()
            self.plist.insert("end", "  %-5s %s"
                              % (tag, os.path.relpath(p, self.repo)))
        if not self.projects:
            self.set_status("no %s projects -- press NEW... or switch to ALL"
                            % self.mode.upper() if self.mode != "all"
                            else "no projects found -- press NEW...", AMBER)
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
        self.workspace_name.configure(text=(os.path.basename(p) + "  /  " +
            project_meta(p)["target"].upper()) if p else "Select a project")
        if p:
            self.set_status(os.path.relpath(p, self.repo))
            # A project knows what machine it is for. Selecting it should
            # reconfigure the whole window around that -- the target, the
            # hardware budgets, and whether building is even possible -- rather
            # than leave PS1 selected while you edit a PS2 game.
            self.set_target(project_meta(p)["target"], from_project=True)
        self.kit_panel.load(p)
        self.flow_panel.load(p)
        self.asset_panel.load(p)
        self.structure_panel.load(p)
        self.viewport_panel.load(p)
        self.author_sidebar.load(p)
        self.sync_editor()
        if getattr(self, "room_panel", None):
            self.room_panel.load(p)
        if getattr(self, "design_panel", None):
            self.design_panel.load(p)
        if getattr(self, "scene_panel", None):
            self.scene_panel.load(p)
        self.update_author_context()

    def open_flow_from_sidebar(self,node_id):
        self.show_tab('structure')
        self.structure_panel.selected=node_id
        self.structure_panel.draw();self.structure_panel.open_events()

    def update_author_context(self):
        if not getattr(self,'author_sidebar',None):return
        if self.active_tab in ('viewport','game') and self.viewport_panel.world:
            self.author_sidebar.set_scene_hierarchy('SCENE / '+os.path.basename(self.selected_project()),self.viewport_panel.world,self.viewport_panel.index())
            self.author_sidebar.stack.show('hierarchy')
        elif self.active_tab=='room' and getattr(self.room_panel,'objects',None):
            names=list(self.room_panel.objects.get(0,'end'))
            self.author_sidebar.set_hierarchy('GAMEOBJECT CONTENTS',[{'key':'room:'+str(i),'name':name,'space':'local'} for i,name in enumerate(names)])
            self.author_sidebar.stack.show('hierarchy')
        else:
            self.author_sidebar.set_hierarchy(self.TAB_LABELS.get(self.active_tab,'PROJECT'),[])
            if self.active_tab=='structure':self.author_sidebar.stack.show('flow')

    def select_from_hierarchy(self,key):
        if isinstance(key,tuple) and key and key[0] in ('screen','screen_object'):
            screen_key=key[1];world=self.viewport_panel.world
            if not world:return
            world.active_screen=screen_key;self.show_tab('viewport');self.viewport_panel.plane.set('2D')
            if key[0]=='screen_object':self.viewport_panel.selected=key[2]
            else:self.viewport_panel.selected=None
            self.viewport_panel.draw();self.inspector.show_record(self.viewport_panel.record());return
        if isinstance(key,tuple) and key and key[0]=='scene':
            room=key[1];self.show_tab('viewport');self.viewport_panel.room.current(room);self.viewport_panel.change_room();self.update_author_context();return
        if isinstance(key,tuple) and key and key[0]=='object':
            room,key=key[1],key[2];self.show_tab('viewport');self.viewport_panel.room.current(room);self.viewport_panel.change_room()
        if key and key.startswith('room:'):
            index=int(key.split(':')[1]);self.room_panel.objects.selection_clear(0,'end');self.room_panel.objects.selection_set(index);self.room_panel.objects.event_generate('<<ListboxSelect>>');return
        if self.viewport_panel.world and key:
            self.viewport_panel.selected=key
            if key.startswith('camera:'):self.viewport_panel.active_camera=int(key.split(':')[1])
            self.viewport_panel.draw();self.inspector.show_record(self.viewport_panel.record());self.right_tabs.show('inspector')

    def on_viewport_selection(self,record):
        self.inspector.show_record(record)
        self.right_tabs.show('inspector')
        self.update_author_context()

    def add_ready_object(self,kind,screen_position=None):
        world=self.viewport_panel.world
        if not world:return
        if screen_position:
            widget=self.root.winfo_containing(*screen_position)
            if widget is not self.viewport_panel.canvas:return
        try:
            world.active_screen=None;self.viewport_panel.checkpoint();room=self.viewport_panel.index()
            if world.kind=='lab3d_v1' and kind in ('Empty GameObject','3D Mesh','Solid Object'):
                base={'Empty GameObject':'object','3D Mesh':'mesh','Solid Object':'solid'}[kind];name=base;number=1
                while name in world.doc['objects']:number+=1;name=base+str(number)
                if len(world.doc['objects'])>=16:raise ValueError('PS2 3D Lab currently supports 16 runtime objects.')
                world.doc['objects'][name]=list(self.viewport_panel.editor_camera['target']);world.doc['rotations'][name]=[0,0,0];world.doc['scales'][name]=[1,1,1]
                textures=list((world.root/'textures').glob('*.png'))
                if kind=='3D Mesh' and textures:world.doc.setdefault('materials',{})[name]={'texture':textures[0].relative_to(world.root).as_posix()}
                self.viewport_panel.selected='o:'+name
            elif world.kind=='ps1' and kind=='2D Sprite':
                textures=world.doc.get('textures',[])
                if not textures:raise ValueError('Add a texture before creating a Sprite2D.')
                sprites=world.scenes()[room].setdefault('sprites',[]);sprites.append({'name':'Sprite '+str(len(sprites)+1),'x':152,'y':112,'w':16,'h':16,'texture':textures[0]['name']});self.viewport_panel.selected='s:'+str(len(sprites)-1)
            elif kind=='Trigger' and self.viewport_panel.record():self.viewport_panel.add_trigger();return
            else:raise ValueError('%s is available as a GameObject definition, but this project adapter cannot instantiate it yet.'%kind)
            world.validate();self.viewport_panel.draw();self.update_author_context();self.inspector.show_record(self.viewport_panel.record());self.right_tabs.show('inspector')
        except (ValueError,KeyError,TypeError) as exc:
            self.viewport_panel.undo();messagebox.showerror('Ready GameObject',str(exc),parent=self.root)

    @staticmethod
    def _numbers(text,count):
        values=[float(value.strip()) for value in text.split(',') if value.strip()]
        if len(values)!=count:raise ValueError('%d comma-separated values required.'%count)
        return values

    def apply_inspector(self,record,values):
        world=self.viewport_panel.world
        if not world or record.get('readonly'):return
        try:
            self.viewport_panel.checkpoint();key=record['key']
            if values['position']:world.move(self.viewport_panel.index(),key,self._numbers(values['position'],len(record['pos'])))
            if values['rotation'] or values['scale']:
                rotation=self._numbers(values['rotation'],3) if values['rotation'] else record.get('rot',[0,0,0])
                scale=self._numbers(values['scale'],3) if values['scale'] else record.get('scale',[1,1,1])
                world.set_transform(key,rotation,scale)
            if values['material'] and values['material']!=record.get('material',{}).get('texture',''):world.set_material(key,values['material'])
            if key.startswith('u:') and world.active_screen:
                obj=world.screens['screens'][world.active_screen]['objects'][int(key[2:])]
                if values['image']:obj['texture']=values['image'];obj['type']='sprite2d'
                if values['layer']:obj['layer']=int(values['layer'])
                if values['text'] or obj.get('type') in ('text','button'):obj['text']=values['text']
                if values['visible']!='':obj['visible']=values['visible'].lower() not in ('0','false','off','no')
                if values['size']:
                    size=self._numbers(values['size'],2);obj['rect'][2:]=list(map(int,size))
            truth=lambda value:value.lower() not in ('0','false','off','no')
            world.set_common(key,{'isActive':truth(values['isActive']),'visible':truth(values['visible']),'tag':values['tag'],'state':values['state'] or 'default','persistent':truth(values['persistent'])})
            if key.startswith('camera:') and world.kind=='fixed_room_v1':
                camera=world.doc['cameras'][int(key.split(':')[1])]
                if values['target']:camera['target']=self._numbers(values['target'],3)
                if values['fov']:camera['fov']=float(values['fov'])
            elif key=='camera' and world.kind=='lab3d_v1':
                if values['target']:world.doc['camera']['target']=self._numbers(values['target'],3)
                if values['fov']:world.doc['camera']['fov']=float(values['fov'])
            name=values['name']
            if name and name!=record.get('name'):
                if key.startswith('u:') and world.active_screen:
                    world.screens['screens'][world.active_screen]['objects'][int(key[2:])]['name']=name
                else:world.doc.setdefault('editor_names',{})[key]=name
            world.validate();self.viewport_panel.save();self.viewport_panel.draw();self.update_author_context();self.inspector.show_record(self.viewport_panel.record())
            self.set_status('GameObject properties saved',GREEN)
        except (ValueError,TypeError,OSError) as exc:
            self.viewport_panel.undo();messagebox.showerror('Inspector',str(exc),parent=self.root)

    def choose_sprite_image(self,record,entry):
        world=self.viewport_panel.world
        if not world or not record.get('key','').startswith('u:'):return
        source=filedialog.askopenfilename(parent=self.root,title='Choose Sprite2D PNG',filetypes=[('PNG image','*.png')])
        if not source:return
        try:
            from PIL import Image
            with Image.open(source) as image:
                limit=256 if world.target=='ps1' else 512
                if image.width>limit or image.height>limit:raise ValueError('%s Sprite2D images must fit within %dx%d.'%(world.target.upper(),limit,limit))
            folder=world.root/'textures'/'ui';folder.mkdir(parents=True,exist_ok=True)
            destination=folder/Path(source).name
            if Path(source).resolve()!=destination.resolve():
                import shutil;shutil.copy2(source,destination)
            relative=destination.relative_to(world.root).as_posix()
            entry.configure(state='normal');entry.delete(0,'end');entry.insert(0,relative)
            self.set_status('Sprite image selected; Apply to save it.',CYAN)
        except (OSError,ValueError) as exc:messagebox.showerror('Sprite2D image',str(exc),parent=self.root)

    def toggle_hub(self):
        self.hub_visible = not self.hub_visible
        if self.hub_visible:
            siblings = self.project_hub.master.pack_slaves()
            opts = {"before": siblings[0]} if siblings else {}
            self.project_hub.pack(fill="x", pady=(0, 6), **opts)
        else:
            self.project_hub.pack_forget()

    def toggle_fullscreen(self):
        if not self.fullscreen:
            self.windowed_geometry = self.root.geometry()
            self.root.attributes("-fullscreen", True)
        else:
            self.root.attributes("-fullscreen", False)
            if self.windowed_geometry:
                self.root.geometry(self.windowed_geometry)
        self.fullscreen = not self.fullscreen

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

    def open_stage_events(self,stage):
        self.flow_panel.load(self.selected_project())
        nodes=self.flow_panel.nodes
        # Existing graphs have no stage groups: expose boot at Initialize and
        # gameplay roots at the first Play stage, without inventing runtime scope.
        explicit=[n['id'] for n in nodes if n.get('section_id')==stage['id']]
        first_play=next((n['id'] for n in self.structure_panel.nodes if n['kind']=='Play'),None)
        roots=explicit
        if stage['kind']=='Initialize':
            roots += [n['id'] for n in nodes if n['kind']=='On start' and n.get('section_id') is None]
        elif stage['id']==first_play:
            roots += [n['id'] for n in nodes if n.get('section_id') is None and (n['kind'].startswith('On ') or n['kind'] in ('After frames','Every frames')) and n['kind']!='On start']
        self.show_tab('flow');self.flow_panel.focus_stage(stage,roots)
    def open_walkthrough(self):
        project = self.selected_project()
        if not project:return
        path = os.path.join(project, "WORKFLOW.md")
        try:
            with open(path, encoding="utf-8") as source:content=source.read()
        except OSError:
            content="This project has no WORKFLOW.md yet. Existing projects are preserved; new templates include their walkthrough."
        win=tk.Toplevel(self.root);win.title(os.path.basename(project)+" — Walkthrough")
        win.geometry("780x600");win.configure(bg=BG)
        text=tk.Text(win,bg=BG,fg=FG,insertbackground=AMBER,wrap="word",font=MONO_SM,padx=16,pady=16)
        scroll=tk.Scrollbar(win,command=text.yview);scroll.pack(side="right",fill="y")
        text.configure(yscrollcommand=scroll.set);text.pack(fill="both",expand=True)
        text.insert("1.0",content);text.configure(state="disabled")


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

        self.kit_panel.load(p)
        self.flow_panel.load(p)
        self.asset_panel.load(p)
        self.structure_panel.load(p)
        self.viewport_panel.load(p)
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

    def _poll_project_data(self):
        """Notice when Godot rewrites the selected project's scene or VN data.

        Godot exports by replacing vn.json / scene.json on disk. Studio has no
        way of being told, so it watches the file: the alternative is what used
        to happen, where an export succeeded, Studio kept showing its own older
        copy, and the two silently disagreed until something overwrote the other.
        """
        project = self.selected_project()
        stamp = None
        try:
            if project:
                for name in ("vn.json", "scene.json"):
                    path = os.path.join(project, name)
                    if os.path.isfile(path):
                        stamp = (project, name, os.stat(path).st_mtime_ns)
                        break
        except OSError:
            stamp = None
        if stamp != self._data_stamp:
            first = self._data_stamp is None or self._data_stamp[0] != project
            self._data_stamp = stamp
            if stamp and not first:
                # Unsaved room edits are the user's, not Godot's: say so rather
                # than throwing either side away.
                if self.room_panel.dirty:
                    self.log("%s changed on disk, but ROOM has unsaved edits. "
                             "Save or RELOAD to choose which wins." % stamp[1],
                             AMBER)
                else:
                    self.room_panel.load(project, force=True)
                    self.log("%s reloaded from disk (Godot export)." % stamp[1],
                             CYAN)
                self.design_panel.load(project)
                self.scene_panel.load(project, force=True)
        self.root.after(1200, self._poll_project_data)

    def set_buttons(self, on):
        # Whether a build is running and whether this target can build at all
        # are two different reasons to be unavailable; both have to hold.
        buildable = self.target.get() in self.BUILDABLE
        for b in (self.b_run, self.b_build, self.b_doc):
            b.set_enabled(on and buildable)
        self.b_clean.set_enabled(on)
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
        p = self.selected_project()
        if not p:
            self.log("no project selected.", RED)
            return
        if cmd in ("build", "run") and not self.viewport_panel.save_pending():
            return
        if cmd in ("build", "run") and self.room_panel.dirty:
            self.room_panel.save()
            if self.room_panel.dirty:
                return
        self.show_tab("console")
        if cmd in ("build", "run") and os.path.isfile(os.path.join(p, "vn.json")):
            self.design_panel.load(p)
            if not self.design_panel.save():
                self.show_tab("design")
                return
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
        if self.target.get() == "ps2":
            ok = bool(tc.ps2_cc() and tc.find_make())
            self.tcstat.configure(
                text=("toolchain: PS2 OK" if ok else "toolchain: PS2 INCOMPLETE"),
                fg=GREEN if ok else RED)
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
        if self.mode in ("ps1", "ps2"):
            templates = [t for t in templates
                         if t.get("target", "ps1") == self.mode]
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

        initial = next((t["name"] for t in templates
                        if t["name"] == DEFAULT_TEMPLATE), templates[0]["name"])
        chosen = tk.StringVar(value=initial)
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

        select(initial)

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
        if not self.viewport_panel.save_pending():
            return
        if self.running and self.proc:
            try:
                self.proc.terminate()
            except OSError:
                pass
        self.settings.update({
            "geometry": self.windowed_geometry if self.fullscreen else self.root.geometry(),
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
