"""Event canvas owned by the selected GAME FLOW box; UI extension boundary."""
import copy
import json
from pathlib import Path
from tkinter import messagebox
from flowpanel import FlowPanel
from theme import Button, CYAN

class BoxEventsPanel(FlowPanel):
    def __init__(self, parent):
        super().__init__(parent)
        self.stage = None
        self.stages = []
        self.entry = None
        Button(self, 'MAKE SELECTED BOX THE ENTRY', self.make_entry, CYAN).pack(fill='x')

    def open_box(self, project, stage, stages):
        self.project = None
        super().load(project)
        self.stage = copy.deepcopy(stage)
        self.stages = copy.deepcopy(stages)
        path = Path(project) / self.filename
        self.original = path.read_text(encoding='utf-8') if path.exists() else None
        doc = json.loads(self.original) if self.original else {}
        default = next((s['id'] for s in stages if s['kind']=='Play'), stage['id'])
        self.entry = doc.get('entry', default)
        valid = {s['id'] for s in stages}
        for node in self.nodes:
            if doc.get('version', 1) < 2:
                node['section_id'] = default  # Legacy groups never had runtime ownership.
                self.enabled = False
        self.section_id = stage['id']
        self.focus_roots = []
        values = list(self.kind['values'])
        if self.target == 'ps1' or 'Set camera' in values or 'Set colour' in values or 'Show main menu' in values:
            self.kind['values'] = values + ['On exit','Go to Flow Box']
        self.note.configure(text='BOX %d / %s: all owned events. On start = enter box. Transition destinations: %s. Entry: %s. Changes require ENABLE.' % (stage['id'], stage.get('value', stage['kind']), ', '.join('%s=%s'%(s['id'],s.get('value',s['kind'])) for s in stages), self.entry))
        self.draw()

    def visible_ids(self):
        return {n['id'] for n in self.nodes if n.get('section_id') == self.section_id}

    def show_all(self):
        self.draw()  # A box canvas never leaks another box's events.

    def make_entry(self):
        if not self.stage or self.readonly:return
        self.entry = self.stage['id']
        self.enabled = False
        self.save()
        self.note.configure(text='Entry box set to %s. ENABLE to validate the entire game flow.' % self.entry)

    def save(self):
        if not self.project or self.readonly or not self.stage:return
        path = Path(self.project) / self.filename
        current = path.read_text(encoding='utf-8') if path.exists() else None
        if current != self.original:
            self.readonly = True
            messagebox.showerror('Events changed externally', 'Re-select the box to reload before editing. External changes were preserved.', parent=self)
            return
        doc = dict(version=2, target=self.target, status='enabled' if self.enabled else 'draft',
                   entry=self.entry, stages=[dict(id=s['id'], name=s.get('value', s['kind'])) for s in self.stages],
                   nodes=self.nodes, edges=self.edges)
        text = json.dumps(doc, indent=2) + '\n'
        temp = path.with_suffix('.json.tmp')
        temp.write_text(text, encoding='utf-8');temp.replace(path)
        self.original = text
