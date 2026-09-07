"""The SCENE tab: what a project contains, in the order the console sees it.

Until there is a viewport inside the manager, this is the closest thing to one.
It shows the two lists that actually decide what a Neon Coffee game looks like
-- the assets, and the objects in each scene -- and lets you reorder and nudge
them without opening scene.json.

Order is not cosmetic here, which is the whole reason this exists:

  * A scene's index is what `goto_scene(n)` means. Moving a scene renumbers it,
    and any script that jumps to a number is now jumping somewhere else.
  * A sprite's index is its draw order, reversed: sprite 0 ends up on top. So
    "move up" in this list means "draw in front", which is backwards from what
    a layers panel usually implies, and saying so is cheaper than letting
    someone find out.

Everything is written back to scene.json. Nothing is applied to a running
console -- rebuild to see it.
"""

import json
import os
import tkinter as tk

from theme import (AMBER, BG, BORDER, CYAN, DIM, FG, GREEN, MONO, MONO_SM,
                   PANEL, PANEL_HI, RED, SUNKEN, UI, UI_BOLD, Button, group)


class ScenePanel(tk.Frame):
    """Assets, scenes and objects for one project."""

    def __init__(self, parent, on_log=None, on_add=None):
        super().__init__(parent, bg=BG)
        self.on_log = on_log or (lambda *_a, **_k: None)
        self.on_add = on_add or (lambda _kind: None)

        self.project = None
        self.doc = None
        self.dirty = False

        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True)

        left = tk.Frame(body, bg=BG, width=250)
        left.pack(side="left", fill="y", padx=(0, 6))
        left.pack_propagate(False)
        self._build_assets(left)

        right = tk.Frame(body, bg=BG)
        right.pack(side="left", fill="both", expand=True)
        self._build_scenes(right)
        self._build_objects(right)

        self._show_placeholder("no project selected")

    # ---- construction ---------------------------------------------------

    def _listbox(self, parent, height):
        wrap = tk.Frame(parent, bg=BORDER)
        wrap.pack(fill="both", expand=True, padx=6, pady=(6, 0))
        lb = tk.Listbox(wrap, height=height, bg=SUNKEN, fg=FG, font=MONO_SM,
                        selectbackground=AMBER, selectforeground=BG,
                        highlightthickness=0, bd=0, activestyle="none",
                        exportselection=False)
        lb.pack(fill="both", expand=True, padx=1, pady=1)
        return lb

    def _build_assets(self, parent):
        g = group(parent, "assets", CYAN)
        g.pack(fill="both", expand=True)

        tk.Label(g.body, text=" TEXTURES", bg=PANEL, fg=DIM, font=UI_BOLD,
                 anchor="w").pack(fill="x", padx=6, pady=(4, 0))
        self.lb_tex = self._listbox(g.body, 5)

        tk.Label(g.body, text=" SOUNDS", bg=PANEL, fg=DIM, font=UI_BOLD,
                 anchor="w").pack(fill="x", padx=6, pady=(6, 0))
        self.lb_snd = self._listbox(g.body, 4)

        tk.Label(g.body, text=" MUSIC", bg=PANEL, fg=DIM, font=UI_BOLD,
                 anchor="w").pack(fill="x", padx=6, pady=(6, 0))
        self.lb_mus = self._listbox(g.body, 3)

        row = tk.Frame(g.body, bg=PANEL)
        row.pack(fill="x", padx=6, pady=6)
        Button(row, "+TEX", lambda: self.on_add("texture"), AMBER,
               width=7).pack(side="left")
        Button(row, "+SND", lambda: self.on_add("sound"), AMBER,
               width=7).pack(side="left", padx=4)
        Button(row, "+MUS", lambda: self.on_add("music"), AMBER,
               width=7).pack(side="left")

    def _build_scenes(self, parent):
        g = group(parent, "scenes -- index is what goto_scene() means", CYAN)
        g.pack(fill="x", pady=(0, 6))

        self.lb_scene = self._listbox(g.body, 4)
        self.lb_scene.bind("<<ListboxSelect>>", lambda _e: self._refresh_objects())

        row = tk.Frame(g.body, bg=PANEL)
        row.pack(fill="x", padx=6, pady=6)
        Button(row, "MOVE UP", lambda: self._move_scene(-1), CYAN,
               width=10).pack(side="left")
        Button(row, "MOVE DOWN", lambda: self._move_scene(1), CYAN,
               width=11).pack(side="left", padx=4)

    def _build_objects(self, parent):
        g = group(parent, "objects -- first in the list draws on top", CYAN)
        g.pack(fill="both", expand=True)

        self.lb_obj = self._listbox(g.body, 10)
        self.lb_obj.bind("<<ListboxSelect>>", lambda _e: self._sync_fields())

        row = tk.Frame(g.body, bg=PANEL)
        row.pack(fill="x", padx=6, pady=(6, 0))
        Button(row, "FRONT", lambda: self._move_object(-1), CYAN,
               width=8).pack(side="left")
        Button(row, "BACK", lambda: self._move_object(1), CYAN,
               width=8).pack(side="left", padx=4)

        tk.Label(row, text="  nudge", bg=PANEL, fg=DIM, font=UI).pack(side="left")
        self.step = tk.IntVar(value=8)
        for n in (1, 8, 16):
            tk.Radiobutton(row, text=str(n), variable=self.step, value=n,
                           bg=PANEL, fg=DIM, selectcolor=SUNKEN, font=UI,
                           activebackground=PANEL, activeforeground=FG,
                           bd=0, highlightthickness=0).pack(side="left")

        pad = tk.Frame(g.body, bg=PANEL)
        pad.pack(fill="x", padx=6, pady=(4, 0))
        Button(pad, "LEFT", lambda: self._nudge(-1, 0), AMBER,
               width=7).pack(side="left")
        Button(pad, "RIGHT", lambda: self._nudge(1, 0), AMBER,
               width=7).pack(side="left", padx=4)
        Button(pad, "UP", lambda: self._nudge(0, -1), AMBER,
               width=7).pack(side="left")
        Button(pad, "DOWN", lambda: self._nudge(0, 1), AMBER,
               width=7).pack(side="left", padx=4)

        self.pos = tk.Label(pad, text="", bg=PANEL, fg=CYAN, font=MONO_SM)
        self.pos.pack(side="left", padx=8)

        foot = tk.Frame(g.body, bg=PANEL)
        foot.pack(fill="x", padx=6, pady=6)
        self.b_save = Button(foot, "SAVE scene.json", self.save, GREEN)
        self.b_save.pack(side="left")
        Button(foot, "RELOAD", lambda: self.load(self.project, force=True), DIM,
               width=10).pack(side="left", padx=4)
        self.note = tk.Label(foot, text="", bg=PANEL, fg=DIM, font=UI,
                             anchor="w")
        self.note.pack(side="left", padx=8, fill="x", expand=True)

    # ---- loading --------------------------------------------------------

    def _show_placeholder(self, why):
        for lb in (self.lb_tex, self.lb_snd, self.lb_mus, self.lb_scene,
                   self.lb_obj):
            lb.delete(0, "end")
        self.lb_scene.insert("end", "  " + why)
        self.note.configure(text="")
        self.pos.configure(text="")

    def load(self, project, force=False):
        if project == self.project and not force:
            return
        self.project = project
        self.doc = None
        self.dirty = False

        if not project:
            self._show_placeholder("no project selected")
            return

        path = os.path.join(project, "scene.json")
        if not os.path.isfile(path):
            # A PS2 project, or a PS1 one whose content is in C. Neither is a
            # failure; it just has nothing for this panel to show.
            self._show_placeholder("%s has no scene.json"
                                   % os.path.basename(project))
            return

        try:
            with open(path, encoding="utf-8") as fh:
                self.doc = json.load(fh)
        except (OSError, ValueError) as exc:
            self._show_placeholder("scene.json is unreadable: %s" % exc)
            return

        self._refresh_all()

    def _scenes(self):
        if not self.doc:
            return []
        return self.doc.get("scenes") or [self.doc]

    def _refresh_all(self):
        self._refresh_assets()
        self._refresh_scenes()
        self._refresh_objects()
        self._mark()

    def _refresh_assets(self):
        self.lb_tex.delete(0, "end")
        for t in self.doc.get("textures", []):
            self.lb_tex.insert("end", "  %s" % t.get("name", "?"))
        if not self.doc.get("textures"):
            self.lb_tex.insert("end", "  (none)")

        self.lb_snd.delete(0, "end")
        for i, s in enumerate(self.doc.get("sounds", [])):
            # The index is the argument play_sound() takes, so show it.
            self.lb_snd.insert("end", "  %d  %s" % (i, s.get("name", "?")))
        if not self.doc.get("sounds"):
            self.lb_snd.insert("end", "  (none)")

        self.lb_mus.delete(0, "end")
        for i, m in enumerate(self.doc.get("music", [])):
            # Track 1 is the game data, so the first song is play_music(2).
            self.lb_mus.insert("end", "  %d  %s" % (i + 2, os.path.basename(m)))
        if not self.doc.get("music"):
            self.lb_mus.insert("end", "  (none)")

    def _refresh_scenes(self):
        keep = self._selected(self.lb_scene)
        self.lb_scene.delete(0, "end")
        for i, sc in enumerate(self._scenes()):
            n_spr = len(sc.get("sprites", []))
            n_obj = len(sc.get("instances", []))
            self.lb_scene.insert(
                "end", "  scene %d   %2d sprite(s)  %2d object(s)"
                % (i, n_spr, n_obj))
        if self.lb_scene.size():
            self.lb_scene.selection_set(min(keep if keep is not None else 0,
                                            self.lb_scene.size() - 1))

    def _current_scene(self):
        i = self._selected(self.lb_scene)
        scenes = self._scenes()
        if i is None or i >= len(scenes):
            return None
        return scenes[i]

    def _items(self):
        """Sprites first, then 3D instances -- the order the runtime draws."""
        sc = self._current_scene()
        if sc is None:
            return []
        return sc.get("sprites", [])

    def _refresh_objects(self):
        keep = self._selected(self.lb_obj)
        self.lb_obj.delete(0, "end")
        for i, sp in enumerate(self._items()):
            self.lb_obj.insert(
                "end", "  %2d  %-10s %4d,%-4d %3dx%-3d%s"
                % (i, sp.get("texture", "?"), sp.get("x", 0), sp.get("y", 0),
                   sp.get("w", 0), sp.get("h", 0),
                   "  solid" if sp.get("solid") else
                   ("  fixed" if sp.get("fixed") else "")))
        if self.lb_obj.size() and keep is not None:
            self.lb_obj.selection_set(min(keep, self.lb_obj.size() - 1))
        self._sync_fields()

    @staticmethod
    def _selected(lb):
        sel = lb.curselection()
        return sel[0] if sel else None

    def _sync_fields(self):
        i = self._selected(self.lb_obj)
        items = self._items()
        if i is None or i >= len(items):
            self.pos.configure(text="")
            return
        sp = items[i]
        self.pos.configure(text="x %d  y %d" % (sp.get("x", 0), sp.get("y", 0)))

    # ---- editing --------------------------------------------------------

    def _mark(self, dirty=False):
        self.dirty = dirty
        self.note.configure(
            text="unsaved -- SAVE then rebuild" if dirty else "",
            fg=AMBER if dirty else DIM)

    def _move_scene(self, delta):
        scenes = self._scenes()
        i = self._selected(self.lb_scene)
        if i is None or not (0 <= i + delta < len(scenes)):
            return
        if "scenes" not in (self.doc or {}):
            self.on_log("this project has a single scene; there is nothing to "
                        "reorder.", DIM)
            return

        scenes[i], scenes[i + delta] = scenes[i + delta], scenes[i]
        self._refresh_scenes()
        self.lb_scene.selection_clear(0, "end")
        self.lb_scene.selection_set(i + delta)
        self._refresh_objects()
        self._mark(True)
        self.on_log("scene %d and %d swapped -- goto_scene() numbers changed "
                    "with them." % (i, i + delta), AMBER)

    def _move_object(self, delta):
        items = self._items()
        i = self._selected(self.lb_obj)
        if i is None or not (0 <= i + delta < len(items)):
            return
        items[i], items[i + delta] = items[i + delta], items[i]
        self._refresh_objects()
        self.lb_obj.selection_clear(0, "end")
        self.lb_obj.selection_set(i + delta)
        self._mark(True)
        # Scripts address sprites by index, so this is not a pure view change.
        self.on_log("sprite %d and %d swapped -- any script using those indices "
                    "now addresses the other one." % (i, i + delta), AMBER)

    def _nudge(self, dx, dy):
        items = self._items()
        i = self._selected(self.lb_obj)
        if i is None or i >= len(items):
            return
        step = self.step.get()
        sp = items[i]
        sp["x"] = int(sp.get("x", 0)) + dx * step
        sp["y"] = int(sp.get("y", 0)) + dy * step
        self._refresh_objects()
        self.lb_obj.selection_clear(0, "end")
        self.lb_obj.selection_set(i)
        self._mark(True)

    def save(self):
        if not (self.project and self.doc):
            return False
        path = os.path.join(self.project, "scene.json")
        try:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(self.doc, fh, indent=2)
                fh.write("\n")
        except OSError as exc:
            self.on_log("could not write scene.json: %s" % exc, RED)
            return False
        self._mark(False)
        self.on_log("saved scene.json -- rebuild to see it.", GREEN)
        return True
