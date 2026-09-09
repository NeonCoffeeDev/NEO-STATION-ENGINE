"""Overall game maps, intentionally separate from executable event graphs."""
import json
from pathlib import Path
from tkinter import messagebox
from flowpanel import FlowPanel
from ncc import flowkits
from boxevents import BoxEventsPanel

class StructurePanel(FlowPanel):
    filename='game-structure.json'
    def __init__(self,parent,on_open=None):
        super().__init__(parent);self.on_open=on_open
        self.events = BoxEventsPanel(self)
        self.events.pack(fill='both', expand=True)
        self.canvas.configure(height=180)
        self.canvas.bind('<Double-Button-1>',lambda e:self.open_events())
    def open_events(self):
        stage=next((n for n in self.nodes if n['id']==self.selected),None)
        if stage and self.project:self.events.open_box(self.project,stage,self.nodes)
        else:
            self.events.stage=None;self.events.nodes=[];self.events.edges=[];self.events.draw()
            self.events.note.configure(text='Select a GAME FLOW box to edit its events.')
    def pick(self,event):
        super().pick(event)
        self.open_events()
    def load(self,project):
        if self.project != project:
            self.events.stage=None
            self.events.load(project)
            self.events.nodes=[];self.events.edges=[];self.events.draw()
        super().load(project)
        self.kind['values']=['Initialize','Splash','Intro','Menu','Load room','Play','Results','Ending']
        self.kind.current(0)
        self.kit_choice['values']=['Project learning map'];self.kit_choice.current(0)
        self.note.configure(text='Select a box: its complete event canvas appears below. Add On start entry actions and Go to Flow Box transitions there. Map arrows are reference lines; executable transitions live in the events.')
    def enable(self):
        self.events.enable() if self.events.stage else messagebox.showinfo('Game flow','Select a box and add its events first.',parent=self)
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
