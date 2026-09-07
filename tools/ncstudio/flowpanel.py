"""Console-scoped visual flow drafts; deliberately not an execution backend."""
import json
from pathlib import Path
import tkinter as tk
from tkinter import ttk, simpledialog, messagebox
from theme import BG, FG, CYAN, AMBER, Button
from ncc.build import project_meta
from ncc import eventflow, ncscript

class FlowPanel(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent, bg=BG)
        self.group=self; self.project=None; self.nodes=[]; self.edges=[]
        self.selected=None; self.source=None; self.readonly=False
        bar=tk.Frame(self,bg=BG); bar.pack(fill='x')
        self.kind=ttk.Combobox(bar,state='readonly',values=['On start','On button','Change room','Show pooled object','Hide object','Play effect','Run kit'])
        self.kind.current(0); self.kind.pack(side='left')
        for label, fn in [('ADD NODE',self.add),('CONNECT',self.connect),('EDIT',self.edit),('DELETE',self.delete),('SAVE',self.save),('ENABLE PS1',self.enable),('DRAFT',self.disable)]:
            Button(bar,label,fn,CYAN).pack(side='left',padx=2)
        self.note=tk.Label(self,bg=BG,fg=AMBER,anchor='w',wraplength=850)
        self.note.pack(fill='x')
        self.canvas=tk.Canvas(self,bg='#10171b',highlightthickness=0)
        self.canvas.pack(fill='both',expand=True)
        self.canvas.bind('<Button-1>',self.pick)
        self.canvas.bind('<B1-Motion>',self.drag)
        self.canvas.bind('<ButtonRelease-1>',lambda e:self.save())
        self.canvas.bind('<Double-Button-1>',lambda e:self.edit())

    def load(self,project):
        if self.project==project:return
        self.enabled=False
        self.project=project; self.nodes=[];self.edges=[];self.selected=None;self.source=None;self.readonly=False
        if project:
            self.target=project_meta(project)['target']; p=Path(project)/'event-flow.json'
            try:
                if p.exists():
                    d=json.loads(p.read_text())
                    if d.get('target')!=self.target:raise ValueError('Flow target mismatch; file left untouched.')
                    self.nodes=d['nodes'];self.edges=d['edges'];self.enabled=d.get('status')=='enabled'
                    ids={n['id'] for n in self.nodes}
                    if len(ids)!=len(self.nodes) or any(a not in ids or b not in ids for a,b in self.edges):raise ValueError('Invalid node links')
            except (ValueError,KeyError,TypeError,OSError) as e:
                self.nodes=[];self.edges=[];self.readonly=True
                messagebox.showerror('Flow',str(e),parent=self)
        self.note.configure(text='Flow DRAFT — not executed by builds yet. Drag nodes; CONNECT then click source and destination. Double-click to edit. Saved per project and console.')
        self.draw()

    def draw(self):
        c=self.canvas;c.delete('all');byid={n['id']:n for n in self.nodes}
        for a,b in self.edges:
            if a in byid and b in byid:
                x,y=byid[a],byid[b];c.create_line(x['x']+160,x['y']+30,y['x'],y['y']+30,arrow='last',fill=CYAN,width=2)
        for n in self.nodes:
            tag='node:'+str(n['id']);x=n['x'];y=n['y']
            c.create_rectangle(x,y,x+160,y+60,fill='#233139',outline=AMBER if n['id']==self.selected else CYAN,tags=tag)
            c.create_text(x+8,y+16,text=n['kind'],anchor='w',fill=CYAN,tags=tag)
            c.create_text(x+8,y+42,text=n.get('value',''),anchor='w',fill=FG,width=145,tags=tag)

    def add(self):
        if not self.project or self.readonly:return
        i=max([n['id'] for n in self.nodes],default=0)+1
        self.nodes.append(dict(id=i,kind=self.kind.get(),value='',x=30+(len(self.nodes)%3)*190,y=30+(len(self.nodes)//3)*90));self.draw();self.save()

    def pick(self,e):
        tags=self.canvas.gettags('current'); self.selected=next((int(t[5:]) for t in tags if t.startswith('node:')),None)
        if self.source is not None and self.selected is not None:
            if self.source==-1:self.source=self.selected
            else:
                edge=[self.source,self.selected]
                if edge[0]!=edge[1] and edge not in self.edges:self.edges.append(edge)
                self.source=None;self.save()
        self.last=(e.x,e.y);self.draw()

    def drag(self,e):
        if self.readonly:return
        for n in self.nodes:
            if n['id']==self.selected:
                n['x']=max(0,n['x']+e.x-self.last[0]);n['y']=max(0,n['y']+e.y-self.last[1])
        self.last=(e.x,e.y);self.draw()

    def connect(self):
        if not self.readonly:self.source=-1

    def edit(self):
        if self.readonly:return
        for n in self.nodes:
            if n['id']==self.selected:
                v=simpledialog.askstring(n['kind'],'Reference / parameter (draft):',initialvalue=n.get('value',''),parent=self)
                if v is not None:n['value']=v;self.draw();self.save()

    def delete(self):
        if self.readonly:return
        self.nodes=[n for n in self.nodes if n['id']!=self.selected]
        self.edges=[e for e in self.edges if self.selected not in e];self.selected=None;self.draw();self.save()

    def save(self):
        if not self.project or self.readonly:return
        p=Path(self.project)/'event-flow.json';tmp=p.with_suffix('.json.tmp')
        tmp.write_text(json.dumps(dict(version=1,target=self.target,status='enabled' if getattr(self,'enabled',False) else 'draft',nodes=self.nodes,edges=self.edges),indent=2)+'\n');tmp.replace(p)

    def disable(self):
        self.enabled=False;self.save()

    def enable(self):
        if not self.project or self.readonly:return
        self.enabled=True;self.save()
        try:
            script=Path(self.project)/'script.ncs'
            source=script.read_text() if script.exists() else ''
            ncscript.compile_source(eventflow.compose(self.project,self.target,source))
        except (ValueError,KeyError,TypeError,ncscript.ScriptError) as exc:
            self.enabled=False;self.save()
            messagebox.showerror('Cannot enable flow',str(exc),parent=self);return
        messagebox.showinfo('Flow enabled','Events will run on the next PS1 build. Authored script was not changed.',parent=self)
