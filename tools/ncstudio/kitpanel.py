"""Project-local action recipes. Export is explicit; authored scripts stay intact."""
import json
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox
from theme import BG, FG, AMBER, CYAN, Button
from ncc.build import project_meta


class KitPanel(tk.Frame):
    ACTIONS = {
        'Change room': 'goto_scene',
        'Show pooled sprite': 'sprite_show',
        'Hide pooled sprite': 'sprite_hide',
        'Play sound': 'play_sound',
        'Screen shake': 'shake',
    }

    def __init__(self, parent):
        super().__init__(parent, bg=BG)
        self.group = self
        self.project = None
        self.rows = []
        self.note = tk.Label(self, bg=BG, fg=FG, anchor='w', wraplength=650)
        self.note.pack(fill='x', padx=8, pady=8)
        bar = tk.Frame(self, bg=BG); bar.pack(fill='x')
        self.action = ttk.Combobox(bar, values=list(self.ACTIONS), state='readonly')
        self.action.current(0); self.action.pack(side='left', padx=8)
        self.value = tk.Spinbox(bar, from_=0, to=65535, width=8)
        self.value.pack(side='left')
        Button(bar, 'ADD', self.add, CYAN).pack(side='left', padx=8)
        self.list = tk.Listbox(self, bg=BG, fg=FG, selectbackground=AMBER)
        self.list.pack(fill='both', expand=True, padx=8, pady=8)
        self.list.bind('<ButtonPress-1>', self.drag_start)
        self.list.bind('<ButtonRelease-1>', self.drag_end)
        footer = tk.Frame(self, bg=BG); footer.pack(fill='x')
        Button(footer, 'REMOVE', self.remove, CYAN).pack(side='left')
        Button(footer, 'SAVE KIT', self.save, CYAN).pack(side='left', padx=8)
        Button(footer, 'EXPORT PS1 RECIPE', self.export, AMBER).pack(side='left')

    def load(self, project):
        if project == self.project: return
        self.project = project; self.rows = []
        if not project:
            self.note.configure(text='Select a project.'); self.refresh(); return
        self.target = project_meta(project)['target']
        path = Path(project)/'action-kit.json'
        try:
            if path.exists():
                doc = json.loads(path.read_text())
                if doc.get('target') != self.target:
                    raise ValueError('Kit target does not match this project.')
                for row in doc['actions']:
                    if row['action'] not in self.ACTIONS or type(row['value']) is not int or row['value'] < 0:
                        raise ValueError('Invalid action recipe.')
                self.rows = doc['actions']
        except (OSError, ValueError, KeyError) as exc:
            messagebox.showerror('Kit', str(exc), parent=self)
        self.note.configure(text=self.target.upper() + ' action recipe — drag rows to reorder. '
            'Values are existing room/sprite/sound indices or shake strength. '
            'Save is project-local. PS1 export creates a function to call from your script; '
            'it is not automatically wired to events. PS2 execution is not implemented yet.')
        self.refresh()

    def refresh(self):
        self.list.delete(0, 'end')
        for row in self.rows: self.list.insert('end', '%s: %s' % (row['action'], row['value']))

    def add(self):
        if not self.project: return
        try:
            value = int(self.value.get())
            if value < 0: raise ValueError()
        except ValueError:
            messagebox.showerror('Kit', 'Use a non-negative integer.', parent=self); return
        self.rows.append(dict(action=self.action.get(), value=value)); self.refresh(); self.save()

    def remove(self):
        selected = self.list.curselection()
        if selected: self.rows.pop(selected[0]); self.refresh(); self.save()

    def drag_start(self, event): self.drag_index = self.list.nearest(event.y)

    def drag_end(self, event):
        old = getattr(self, 'drag_index', -1); new = self.list.nearest(event.y)
        if 0 <= old < len(self.rows) and 0 <= new < len(self.rows):
            self.rows.insert(new, self.rows.pop(old)); self.refresh(); self.save()

    def save(self):
        if not self.project: return
        path = Path(self.project)/'action-kit.json'
        temporary = path.with_suffix('.json.tmp')
        temporary.write_text(json.dumps(dict(version=1, target=self.target, actions=self.rows), indent=2)+'\n')
        temporary.replace(path)

    def export(self):
        if not self.project: return
        if self.target != 'ps1':
            messagebox.showinfo('Unsupported', 'PS2 visual-action execution is not available. No PS1 code was exported.', parent=self); return
        body = ['func nc_kit_action():']
        body += ['    %s(%d)' % (self.ACTIONS[r['action']], r['value']) for r in self.rows] or ['    pass']
        self.clipboard_clear(); self.clipboard_append('\n'.join(body)+'\n')
        messagebox.showinfo('Recipe copied', 'Paste into script.ncs and call nc_kit_action() from the desired event. Check indices against your room. Existing scripts were not modified.', parent=self)
