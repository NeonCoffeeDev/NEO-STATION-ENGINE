"""Editable top-down PS2 layout; not a console renderer."""
import json
from pathlib import Path
import tkinter as tk
from tkinter import simpledialog, messagebox
from theme import BG, FG, CYAN, AMBER, Button
from ncc.build import project_meta
from ncc import roomlayout

class ViewportPanel(tk.Frame):
    def __init__(self,parent):
        super().__init__(parent,bg=BG);self.group=self;self.project=None;self.doc=None;self.selected=None;self.drafts={}
        bar=tk.Frame(self,bg=BG);bar.pack(fill='x')
        Button(bar,'SAVE LAYOUT',self.save,CYAN).pack(side='left')
        Button(bar,'RELOAD',lambda:self.load(self.project,force=True),CYAN).pack(side='left')
        Button(bar,'CAMERA ANGLES',self.cameras,AMBER).pack(side='left')
        self.note=tk.Label(self,bg=BG,fg=FG,anchor='w');self.note.pack(fill='x')
        self.canvas=tk.Canvas(self,bg='#10171b',highlightthickness=0)
        self.canvas.pack(fill='both',expand=True)
        self.canvas.bind('<Configure>',lambda e:self.draw())
        self.canvas.bind('<Button-1>',self.pick);self.canvas.bind('<B1-Motion>',self.drag)
        self.canvas.bind('<ButtonRelease-1>',lambda e:self.draw())
    def load(self,project,force=False):
        if self.project==project and not force:return
        if self.project and self.doc and not force:
            self.drafts[self.project]=(self.doc,self.original)
        if force:self.drafts.pop(project,None)
        self.project=project;self.doc=None;self.selected=None
        if project and project_meta(project).get('event_adapter')=='fixed_room_v1':
            try:
                self.doc=roomlayout.load(project);p=Path(project)/'room-layout.json'
                self.original=p.read_text() if p.exists() else None
                if project in self.drafts:self.doc,self.original=self.drafts[project]
            except (OSError,ValueError,KeyError,TypeError) as e:messagebox.showerror('Viewport',str(e),parent=self)
        self.note.configure(text='Top-down authoring: drag player, key or door; SAVE then BUILD. Camera angles affect the game, not this view.' if self.doc else 'This viewport currently edits PS2 Fixed Camera Room projects. Use ROOM for PS1/VN layouts.')
        self.draw()
    def mapping(self):
        w=self.canvas.winfo_width();h=self.canvas.winfo_height()
        return w/2,h/2,max(1,min((w-100)/7,(h-100)/5))
    def draw(self):
        c=self.canvas;c.delete('all')
        if not self.doc:return
        cx,cy,scale=self.mapping()
        for x in range(-3,4):c.create_line(cx+x*scale,cy-2*scale,cx+x*scale,cy+2*scale,fill='#2c3d45')
        for z in range(-2,3):c.create_line(cx-3*scale,cy-z*scale,cx+3*scale,cy-z*scale,fill='#2c3d45')
        c.create_text(12,15,anchor='w',text='X →     Z ↑     Room limits: X ±3 / Z ±2',fill=FG)
        for name,(x,z) in self.doc['objects'].items():
            px,py=cx+x*scale,cy-z*scale
            c.create_rectangle(px-12,py-12,px+12,py+12,fill=AMBER if name==self.selected else CYAN,tags=name)
            c.create_text(px,py+25,text='%s (%.2f, %.2f)'%(name,x,z),fill=FG,tags=name)
    def pick(self,e):
        tags=self.canvas.gettags('current')
        self.selected=next((tag for tag in tags if self.doc and tag in self.doc['objects']),None);self.draw()
    def drag(self,e):
        if not self.doc or not self.selected:return
        cx,cy,scale=self.mapping();maxx,maxz=(2,1.2) if self.selected=='door' else (3,2)
        self.doc['objects'][self.selected]=[round(max(-maxx,min(maxx,(e.x-cx)/scale)),2),round(max(-maxz,min(maxz,(cy-e.y)/scale)),2)]
        self.draw();self.note.configure(text='Unsaved layout: SAVE LAYOUT before building or switching projects.')
    def save(self):
        if not self.doc:return
        try:
            roomlayout.validate(self.doc);p=Path(self.project)/'room-layout.json'
            if (p.read_text() if p.exists() else None)!=self.original:raise ValueError('Layout changed outside this view. Reload before saving.')
            text=json.dumps(self.doc,indent=2)+'\n';temp=p.with_suffix('.json.tmp');temp.write_text(text);temp.replace(p);self.original=text
            self.note.configure(text='Saved. Build to apply object positions and camera angles.')
        except (OSError,ValueError) as e:messagebox.showerror('Save layout',str(e),parent=self)
    def cameras(self):
        if not self.doc:return
        value=simpledialog.askstring('Camera angles','Three yaw angles in radians (-3.1416..3.1416), separated by commas:',initialvalue=', '.join(map(str,self.doc['camera_yaw'])),parent=self)
        if value is None:return
        old=self.doc['camera_yaw']
        try:
            self.doc['camera_yaw']=[float(v) for v in value.split(',')];roomlayout.validate(self.doc)
        except (ValueError,TypeError):
            self.doc['camera_yaw']=old;messagebox.showerror('Camera','Enter three finite angles in range.',parent=self);return
        self.note.configure(text='Unsaved camera settings: SAVE LAYOUT to apply on next build.')
