"""Editable top-down PS2 layout; not a console renderer."""
import json
import copy
import math
from pathlib import Path
import tkinter as tk
from tkinter import simpledialog, messagebox, ttk
from theme import BG, FG, CYAN, AMBER, Button
from ncc.build import project_meta
from ncc import roomlayout

class ViewportPanel(tk.Frame):
    def __init__(self,parent):
        super().__init__(parent,bg=BG);self.group=self;self.project=None;self.doc=None;self.selected=None;self.drafts={}
        self.history=[];self.zoom=1.0
        bar=tk.Frame(self,bg=BG);bar.pack(fill='x')
        Button(bar,'SAVE LAYOUT',self.save,CYAN).pack(side='left')
        Button(bar,'RELOAD',lambda:self.load(self.project,force=True),CYAN).pack(side='left')
        Button(bar,'CAMERA ANGLES',self.cameras,AMBER).pack(side='left')
        Button(bar,'UNDO',self.undo,CYAN).pack(side='left')
        Button(bar,'FIT',self.fit,CYAN).pack(side='left')
        Button(bar,'POSITION',self.position,CYAN).pack(side='left')
        self.object_choice=ttk.Combobox(bar,state='readonly',width=10,values=['player','key','door'])
        self.object_choice.pack(side='left')
        self.object_choice.bind('<<ComboboxSelected>>',lambda e:self.select_object())
        self.snap=tk.BooleanVar(value=True)
        tk.Checkbutton(bar,text='Snap 0.25',variable=self.snap,bg=BG,fg=FG,selectcolor=BG).pack(side='left')
        self.note=tk.Label(self,bg=BG,fg=FG,anchor='w');self.note.pack(fill='x')
        self.canvas=tk.Canvas(self,bg='#10171b',highlightthickness=0)
        self.canvas.pack(fill='both',expand=True)
        self.canvas.bind('<Configure>',lambda e:self.draw())
        self.canvas.bind('<Button-1>',self.pick);self.canvas.bind('<B1-Motion>',self.drag)
        self.canvas.bind('<ButtonRelease-1>',lambda e:self.draw())
        self.canvas.bind('<MouseWheel>',self.wheel)
    def load(self,project,force=False):
        if self.project==project and not force:return
        if self.project and self.doc and not force:
            self.drafts[self.project]=(self.doc,self.original)
        if force and self.doc and self.original is not None and json.loads(self.original)!=self.doc:
            if not messagebox.askyesno('Reload layout','Discard unsaved layout edits and reload from disk?',parent=self):return
        if force:self.drafts.pop(project,None)
        self.project=project;self.doc=None;self.selected=None
        self.history=[];self.zoom=1.0
        self.object_choice.set('')
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
        return w/2,h/2,max(1,min((w-100)/7,(h-100)/5))*self.zoom
    def draw(self):
        c=self.canvas;c.delete('all')
        if not self.doc:return
        cx,cy,scale=self.mapping()
        for x in range(-3,4):c.create_line(cx+x*scale,cy-2*scale,cx+x*scale,cy+2*scale,fill='#2c3d45')
        for z in range(-2,3):c.create_line(cx-3*scale,cy-z*scale,cx+3*scale,cy-z*scale,fill='#2c3d45')
        c.create_text(12,15,anchor='w',text='X →     Z ↑     Room limits: X ±3 / Z ±2',fill=FG)
        for i,yaw in enumerate(self.doc['camera_yaw']):
            dx,dz=math.sin(yaw),math.cos(yaw)
            c.create_line(cx-dx*scale*2,cy+dz*scale*2,cx,cy,arrow='last',fill=['#80a6ff','#cc80ff','#80ffb0'][i],dash=(4,3))
            c.create_text(cx-dx*scale*2,cy+dz*scale*2+12,text='Camera %d'%i,fill=FG)
        for name,(x,z) in self.doc['objects'].items():
            px,py=cx+x*scale,cy-z*scale
            c.create_rectangle(px-12,py-12,px+12,py+12,fill=AMBER if name==self.selected else CYAN,tags=name)
            c.create_text(px,py+25,text='%s (%.2f, %.2f)'%(name,x,z),fill=FG,tags=name)
    def pick(self,e):
        tags=self.canvas.gettags('current')
        self.selected=next((tag for tag in tags if self.doc and tag in self.doc['objects']),None);self.draw()
        self.object_choice.set(self.selected or '')
        if self.selected:self.checkpoint()
    def drag(self,e):
        if not self.doc or not self.selected:return
        cx,cy,scale=self.mapping();maxx,maxz=(2,1.2) if self.selected=='door' else (3,2)
        x,z=(e.x-cx)/scale,(cy-e.y)/scale
        if self.snap.get():x,z=round(x*4)/4,round(z*4)/4
        self.doc['objects'][self.selected]=[round(max(-maxx,min(maxx,x)),2),round(max(-maxz,min(maxz,z)),2)]
        self.draw();self.note.configure(text='Unsaved layout: SAVE LAYOUT before building or switching projects.')
    def save(self):
        if not self.doc:return True
        try:
            roomlayout.validate(self.doc);p=Path(self.project)/'room-layout.json'
            if (p.read_text() if p.exists() else None)!=self.original:raise ValueError('Layout changed outside this view. Reload before saving.')
            text=json.dumps(self.doc,indent=2)+'\n';temp=p.with_suffix('.json.tmp');temp.write_text(text);temp.replace(p);self.original=text
            self.note.configure(text='Saved. Build to apply object positions and camera angles.')
            return True
        except (OSError,ValueError) as e:
            messagebox.showerror('Save layout',str(e),parent=self)
            return False
    def cameras(self):
        if not self.doc:return
        value=simpledialog.askstring('Camera angles','Three yaw angles in radians (-3.1416..3.1416), separated by commas:',initialvalue=', '.join(map(str,self.doc['camera_yaw'])),parent=self)
        if value is None:return
        self.checkpoint()
        old=self.doc['camera_yaw']
        try:
            self.doc['camera_yaw']=[float(v) for v in value.split(',')];roomlayout.validate(self.doc)
        except (ValueError,TypeError):
            self.doc['camera_yaw']=old;messagebox.showerror('Camera','Enter three finite angles in range.',parent=self);return
        self.note.configure(text='Unsaved camera settings: SAVE LAYOUT to apply on next build.')

    def checkpoint(self):
        self.history.append(copy.deepcopy(self.doc));self.history=self.history[-40:]
    def undo(self):
        if self.history:
            self.doc=self.history.pop();self.draw()
            self.note.configure(text='Undo applied. Save or Build to apply the layout.')
    def fit(self):
        self.zoom=1.0;self.draw()
    def wheel(self,event):
        self.zoom=max(.5,min(4,self.zoom*(1.15 if event.delta>0 else 1/1.15)));self.draw()
    def position(self):
        if not self.selected or not self.doc:return
        value=simpledialog.askstring('Object position','X, Z coordinates:',initialvalue=', '.join(map(str,self.doc['objects'][self.selected])),parent=self)
        if value is None:return
        candidate=copy.deepcopy(self.doc)
        try:
            candidate['objects'][self.selected]=[float(v) for v in value.split(',')];roomlayout.validate(candidate)
        except (ValueError,TypeError):
            messagebox.showerror('Position','Coordinates must be inside room bounds; door X ±2 / Z ±1.2, others X ±3 / Z ±2.',parent=self);return
        self.checkpoint();self.doc=candidate;self.draw()
        self.note.configure(text='Position changed. Save or Build to apply.')

    def save_pending(self):
        """Persist project drafts without overwriting external edits."""
        pending=dict(self.drafts)
        if self.project and self.doc:pending[self.project]=(self.doc,self.original)
        for project,(doc,original) in pending.items():
            if original is not None and json.loads(original)==doc:continue
            p=Path(project)/'room-layout.json'
            try:
                roomlayout.validate(doc)
                if (p.read_text() if p.exists() else None)!=original:raise ValueError('External layout changes: '+project)
                text=json.dumps(doc,indent=2)+'\n';tmp=p.with_suffix('.json.tmp');tmp.write_text(text);tmp.replace(p)
                self.drafts[project]=(doc,text)
                if project==self.project:self.original=text
            except (OSError,ValueError) as e:
                messagebox.showerror('Layout not saved',str(e),parent=self);return False
        return True

    def select_object(self):
        if self.doc:
            self.selected=self.object_choice.get()
            self.draw()
