"""Overall game maps, intentionally separate from executable event graphs."""
import json
from pathlib import Path
from tkinter import messagebox
from flowpanel import FlowPanel
from ncc import flowkits

class StructurePanel(FlowPanel):
    filename='game-structure.json'
    def __init__(self,parent,on_open=None):
        super().__init__(parent);self.on_open=on_open
        self.canvas.bind('<Double-Button-1>',lambda e:self.open_events())
    def open_events(self):
        stage=next((n for n in self.nodes if n['id']==self.selected),None)
        if stage and self.project and self.on_open:self.on_open(stage)
    def load(self,project):
        super().load(project)
        self.kind['values']=['Initialize','Splash','Intro','Title','Menu','Load room','Play','Results','Ending']
        self.kind.current(0)
        self.kit_choice['values']=['Project learning map'];self.kit_choice.current(0)
        self.note.configure(text='One graph shows the overall GameFlow. Double-click a box to open that state\'s Events graph, GameObjects, and execution actions.')
    def enable(self):
        messagebox.showinfo('GameFlow','Double-click a GameFlow box to open and enable its Events graph.',parent=self)
    def save(self):
        self.enabled=False
        super().save()
    def insert_kit(self):
        if not self.project or self.readonly:return
        root=Path(self.project);rooms=[]
        try:
            if (root/'vn.json').exists():
                d=json.loads((root/'vn.json').read_text());rooms=[str(s.get('id','')) for s in d.get('kit',{}).get('scenes',[])]
            elif (root/'scene.json').exists():
                d=json.loads((root/'scene.json').read_text());rooms=[str(s.get('name') or s.get('id') or i) for i,s in enumerate(d.get('scenes',[d]))]
        except (OSError,ValueError,TypeError) as e:
            messagebox.showerror('Project rooms',str(e),parent=self);return
        recipe=[('Initialize','Target services'),('Splash','Disclaimer (planned)'),('Menu','Main menu (planned)')]
        for room in rooms:recipe += [('Load room',room),('Play',room)]
        if not rooms:recipe += [('Play',root.name)]
        recipe += [('Results','Outcome (planned)'),('Ending','Return / restart (planned)')]
        flowkits.insert(self.nodes,self.edges,recipe);self.save();self.draw()
