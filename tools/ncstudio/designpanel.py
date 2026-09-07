"""Form-based authoring for the PS2 VN prototype."""
import json
import os
from pathlib import Path
import tkinter as tk
from tkinter import messagebox
from theme import BG, FG, DIM, AMBER, CYAN, SUNKEN, MONO_SM, Button
from ncc.vn import validate


class DesignPanel(tk.Frame):
    def __init__(self, parent, on_log, on_godot=None):
        super().__init__(parent, bg=BG)
        self.group = self
        self.project = None
        self.stamp = None
        self.on_log = on_log
        self.drafts = {}
        self.fields = {}
        self.note = tk.Label(self, bg=BG, fg=CYAN, anchor='w')
        self.note.pack(fill='x', padx=8, pady=6)
        for key, label in [('title', 'Title'), ('subtitle', 'Subtitle'),
                           ('logo_scale_x', 'Logo width % (50–200; 110 compensates approximately for 4:3 display)')]:
            tk.Label(self, text=label, bg=BG, fg=FG, anchor='w').pack(fill='x', padx=8)
            field = tk.Entry(self, bg=SUNKEN, fg=FG, insertbackground=AMBER)
            field.pack(fill='x', padx=8, pady=3)
            self.fields[key] = field
        for key in ('story', 'about'):
            tk.Label(self, text=key.upper() + ' — one dialogue line per row; 32 characters max',
                     bg=BG, fg=DIM, anchor='w').pack(fill='x', padx=8)
            field = tk.Text(self, height=5, bg=SUNKEN, fg=FG, insertbackground=AMBER,
                            font=MONO_SM, wrap='none', undo=True)
            field.pack(fill='both', expand=True, padx=8, pady=3)
            self.fields[key] = field
        bar = tk.Frame(self, bg=BG)
        bar.pack(fill='x', padx=8, pady=6)
        Button(bar, 'SAVE DESIGN', self.save, AMBER).pack(side='left')
        Button(bar, 'OPEN PROJECT', self.open_project, CYAN).pack(side='left', padx=8)
        if on_godot:
            Button(bar, 'EDIT VN IN GODOT', on_godot, CYAN).pack(side='left', padx=8)
        self.assets = tk.Label(self, text='', bg=BG, fg=DIM, anchor='w', justify='left')
        self.assets.pack(fill='x', padx=8, pady=4)

    def values(self):
        return {key: field.get('1.0', 'end-1c').split('\n') if isinstance(field, tk.Text)
                else field.get() for key, field in self.fields.items()}

    @staticmethod
    def _stamp(path):
        """Modification time of vn.json, or None when there is no file.

        Godot writes vn.json behind Studio's back -- that is the whole point of
        the export button -- so "have I already loaded this project?" is the
        wrong question to cache on. The right one is "is what I am showing older
        than what is on disk?"
        """
        try:
            return path.stat().st_mtime_ns if path and path.exists() else None
        except OSError:
            return None

    def load(self, project, force=False):
        path = Path(project) / 'vn.json' if project else None
        stamp = self._stamp(path)
        if project == self.project and stamp == self.stamp and not force:
            return
        external = project == self.project and stamp != self.stamp
        if self.project and not external:
            self.drafts[self.project] = self.values()
        self.project = project
        self.stamp = stamp
        doc = {}
        try:
            if path and path.exists():
                doc = json.loads(path.read_text())
                draft = self.drafts.get(project)
                if external:
                    # Godot just wrote this. A draft taken before that write is
                    # older than the file, so keeping it would quietly discard
                    # the export -- which is exactly the bug this replaced.
                    self.drafts.pop(project, None)
                    self.on_log('DESIGN reloaded: vn.json changed outside Studio.')
                elif draft:
                    doc = dict(doc, **draft)
        except (OSError, ValueError) as exc:
            self.on_log(str(exc))
        for key, field in self.fields.items():
            field.configure(state='normal')
            if isinstance(field, tk.Text):
                field.delete('1.0', 'end')
                field.insert('1.0', '\n'.join(doc.get(key, [])))
            else:
                field.delete(0, 'end')
                value = doc.get(key, '')
                if key == 'logo_scale_x' and isinstance(value, float) and value.is_integer():
                    value = int(value)
                field.insert(0, str(value))
            if doc.get('kit') and key == 'story':
                field.configure(state='disabled')
            if not doc:
                field.configure(state='disabled')
        self.note.configure(text='PS2 VN: TITLE → MENU → STORY / ABOUT. Save, then F7 to build.' if doc
                            else 'Select a PS2 VN project. For PS1 layout use SCENE / Godot.')
        if doc.get('kit'):
            self.note.configure(text='VN kit: edit dialogue/characters/scenes in Godot. This panel edits title, logo and About.')
        files = list((Path(project) / 'src').glob('*_data.c')) if project else []
        report = ['Embedded assets (included in ELF): ' + ', '.join(p.name for p in files)]
        kit = doc.get('kit')
        if kit:
            # The cast, spelled out. Without this the only way to answer "did my
            # export actually arrive?" was to reopen Godot, which is how a
            # silently-ignored node went unnoticed for a whole session.
            for label, rows, art in (('Characters', kit.get('characters', []), 'portrait'),
                                     ('Scenes', kit.get('scenes', []), 'background')):
                shown = ['%s <%s>' % (row.get('id', '?'),
                                      Path(row[art]).name if row.get(art) else 'no image')
                         for row in rows]
                report.append('%s (%d): %s' % (label, len(rows), ', '.join(shown) or 'none'))
            report.append('Dialogue entries: %d' % len(kit.get('dialogue', [])))
        self.assets.configure(text='\n'.join(report))

    def save(self):
        if not self.project or not (Path(self.project) / 'vn.json').exists():
            return False
        try:
            doc = self.values()
            doc['logo_scale_x'] = int(doc['logo_scale_x'])
            validate(doc)
            path = Path(self.project) / 'vn.json'
            existing = json.loads(path.read_text())
            existing.update(doc)
            doc = existing
            temp = path.with_suffix('.json.tmp')
            temp.write_text(json.dumps(doc, indent=2) + '\n')
            temp.replace(path)
            self.drafts.pop(self.project, None)
            self.stamp = self._stamp(path)
            self.on_log('Design saved. Build (F7) to include changes in the PS2 ELF.')
            return True
        except (OSError, ValueError) as exc:
            messagebox.showerror('Design needs attention', str(exc), parent=self)
            return False

    def open_project(self):
        if self.project:
            os.startfile(self.project)
