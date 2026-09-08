"""Console-scoped visual flow drafts; deliberately not an execution backend."""
import json
import copy
from pathlib import Path
import tkinter as tk
from tkinter import ttk, simpledialog, messagebox
from theme import BG, FG, CYAN, AMBER, Button
from nodeparams import HELP, MoveDialog, VariableDialog
from ncc.build import project_meta
from ncc import eventflow, ncscript, ps2flow, flowkits

class FlowPanel(tk.Frame):
    filename = "event-flow.json"
    def __init__(self, parent):
        super().__init__(parent, bg=BG)
        self.group=self; self.project=None; self.nodes=[]; self.edges=[]
        self.selected=None; self.source=None; self.readonly=False
        self.history=[];self.focus_roots=None;self.section_id=None;self.enabled=False
        bar=tk.Frame(self,bg=BG); bar.pack(fill='x')
        self.kind=ttk.Combobox(bar,state='readonly',values=['On start','On button','Change room','Show pooled object','Hide object','Play effect','Run kit'])
        self.kind.current(0); self.kind.pack(side='left')
        for label, fn in [('ADD NODE',self.add),('CONNECT',self.connect),('EDIT',self.edit),('DELETE',self.delete),('UNLINK',self.unlink),('SAVE',self.save),('ENABLE',self.enable),('DRAFT',self.disable)]:
            Button(bar,label,fn,CYAN).pack(side='left',padx=2)
        kitbar=tk.Frame(self,bg=BG);kitbar.pack(fill='x')
        self.kit_choice=ttk.Combobox(kitbar,state='readonly',width=34)
        self.kit_choice.pack(side='left')
        Button(kitbar,'INSERT KIT',self.insert_kit,CYAN).pack(side='left',padx=4)
        Button(kitbar,'DUPLICATE',self.duplicate,CYAN).pack(side='left',padx=2)
        Button(kitbar,'UNDO',self.undo,CYAN).pack(side='left',padx=2)
        Button(kitbar,'ALL EVENTS',self.show_all,CYAN).pack(side='left',padx=2)
        Button(kitbar,'GAME FLOW',lambda:getattr(self,'on_back',lambda:None)(),CYAN).pack(side='left',padx=2)
        self.note=tk.Label(self,bg=BG,fg=AMBER,anchor='w',wraplength=850)
        self.note.pack(fill='x')
        self.canvas=tk.Canvas(self,bg='#10171b',highlightthickness=0)
        scroll=tk.Scrollbar(self,command=self.canvas.yview)
        scroll.pack(side='right',fill='y')
        self.canvas.configure(yscrollcommand=scroll.set)
        self.canvas.pack(fill='both',expand=True)
        self.canvas.bind('<Button-1>',self.pick)
        self.canvas.bind('<B1-Motion>',self.drag)
        self.canvas.bind('<ButtonRelease-1>',lambda e:self.save())
        self.canvas.bind('<Double-Button-1>',lambda e:self.edit())

    def load(self,project):
        if self.project==project:return
        self.history=[];self.focus_roots=None;self.section_id=None
        self.kit_choice.set('');self.kit_choice['values']=[]
        self.enabled=False
        self.project=project; self.nodes=[];self.edges=[];self.selected=None;self.source=None;self.readonly=False
        if project:
            self.target=project_meta(project)['target']; p=Path(project)/self.filename
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
        if project:
            meta=project_meta(project)
            self.kit_choice['values']=list(flowkits.available(meta))
            if self.kit_choice['values']:self.kit_choice.current(0)
            if self.target=='ps1':
                kinds=['On start','On button','Change room','Show pooled object','Hide object','Play effect']
            elif meta.get('event_adapter')=='fixed_room_v1':
                kinds=['On start','On button','On zone','On arrival','After frames','Every frames','Once','Cooldown','Move to','Set variable','Add variable','If equal','If at least','Repeat','Stop movement','Set camera','Interact','Reset game']
            else:
                kinds=['On start','On button']
            self.kind['values']=kinds;self.kind.current(0)
        self.note.configure(text='ENABLE validates this project adapter. Drag nodes; CONNECT then click source and destination. Set camera: 0..2; On zone: 0..1. Scroll for more nodes.')
        self.draw()

    def draw(self):
        self.canvas.configure(scrollregion=(0,0,1500,max([n.get('y',0)+150 for n in self.nodes],default=700)))
        c=self.canvas;c.delete('all');byid={n['id']:n for n in self.nodes}
        visible=self.visible_ids()
        for a,b in self.edges:
            if a in visible and b in visible and a in byid and b in byid:
                x,y=byid[a],byid[b];c.create_line(x['x']+160,x['y']+30,y['x'],y['y']+30,arrow='last',fill=CYAN,width=2)
        for n in self.nodes:
            if n['id'] not in visible:continue
            tag='node:'+str(n['id']);x=n['x'];y=n['y']
            c.create_rectangle(x,y,x+160,y+60,fill='#233139',outline=AMBER if n['id']==self.selected else CYAN,tags=tag)
            c.create_text(x+8,y+16,text=n['kind'],anchor='w',fill=CYAN,tags=tag)
            c.create_text(x+8,y+42,text=n.get('value',''),anchor='w',fill=FG,width=145,tags=tag)

    def add(self):
        if not self.project or self.readonly:return
        self.checkpoint()
        i=max([n['id'] for n in self.nodes],default=0)+1
        self.nodes.append(dict(id=i,kind=self.kind.get(),value='',x=30+(len(self.nodes)%3)*190,y=30+(len(self.nodes)//3)*90,section_id=self.section_id))
        if self.focus_roots is not None:self.focus_roots.append(i)
        self.enabled=False;self.draw();self.save()

    def pick(self,e):
        self.checkpoint()
        tags=self.canvas.gettags('current'); self.selected=next((int(t[5:]) for t in tags if t.startswith('node:')),None)
        if self.source is not None and self.selected is not None:
            if self.source==-1:
                self.source=self.selected
                self.note.configure(text='Now click the destination node.')
            else:
                edge=[self.source,self.selected]
                if edge[0]!=edge[1] and edge not in self.edges:self.edges.append(edge);self.enabled=False
                self.source=None;self.save()
        if self.selected is not None and self.source is None:
            n=next(n for n in self.nodes if n['id']==self.selected)
            self.note.configure(text=HELP.get(n['kind'],'Double-click to edit this node.') + ('  [ENABLED]' if self.enabled else '  [DRAFT]'))
        self.last=(self.canvas.canvasx(e.x),self.canvas.canvasy(e.y));self.draw()

    def drag(self,e):
        if self.readonly:return
        for n in self.nodes:
            if n['id']==self.selected:
                n['x']=max(0,n['x']+self.canvas.canvasx(e.x)-self.last[0]);n['y']=max(0,n['y']+self.canvas.canvasy(e.y)-self.last[1])
        self.last=(self.canvas.canvasx(e.x),self.canvas.canvasy(e.y));self.draw()

    def connect(self):
        if not self.readonly:
            self.source=-1
            self.note.configure(text='CONNECT: click the source node, then the destination. UNLINK removes connections from the selected node.')

    def edit(self):
        if self.readonly:return
        for n in self.nodes:
            if n['id']==self.selected:
                if n['kind']=='Move to':v=MoveDialog(self,n.get('value','')).result
                elif n['kind'] in ('Set variable','Add variable','If equal','If at least'):v=VariableDialog(self,n['kind'],n.get('value','')).result
                else:v=simpledialog.askstring(n['kind'],HELP.get(n['kind'],'Existing project object index:'),initialvalue=n.get('value',''),parent=self)
                if v is not None:self.checkpoint();n['value']=v;self.enabled=False;self.draw();self.save()

    def delete(self):
        if self.readonly:return
        self.checkpoint();self.enabled=False
        self.nodes=[n for n in self.nodes if n['id']!=self.selected]
        self.edges=[e for e in self.edges if self.selected not in e];self.selected=None;self.draw();self.save()

    def save(self):
        if not self.project or self.readonly:return
        p=Path(self.project)/self.filename;tmp=p.with_suffix('.json.tmp')
        tmp.write_text(json.dumps(dict(version=1,target=self.target,status='enabled' if getattr(self,'enabled',False) else 'draft',nodes=self.nodes,edges=self.edges),indent=2)+'\n');tmp.replace(p)

    def disable(self):
        self.enabled=False;self.save()

    def enable(self):
        if not self.project or self.readonly:return
        self.enabled=True;self.save()
        try:
            script=Path(self.project)/'script.ncs'
            source=script.read_text() if script.exists() else ''
            if self.target=='ps2':ps2flow.compile_project(self.project)
            else:ncscript.compile_source(eventflow.compose(self.project,self.target,source))
        except (ValueError,KeyError,TypeError,ncscript.ScriptError) as exc:
            self.enabled=False;self.save()
            messagebox.showerror('Cannot enable flow',str(exc),parent=self);return
        messagebox.showinfo('Flow enabled','Events will run on the next build for this project. Authored script was not changed.',parent=self)

    def insert_kit(self):
        if not self.project or self.readonly:return
        recipe=flowkits.available(project_meta(self.project)).get(self.kit_choice.get())
        if not recipe:return
        self.checkpoint()
        added=flowkits.insert(self.nodes,self.edges,recipe)
        for n in self.nodes:
            if n['id'] in added:n['section_id']=self.section_id
        if self.focus_roots is not None:self.focus_roots.extend(added)
        self.enabled=False
        self.save();self.draw();self.canvas.yview_moveto(1.0)
        self.note.configure(text='Kit inserted as a DRAFT. Edit parameters and check for duplicate input handlers, then ENABLE. Existing nodes are preserved.')

    def unlink(self):
        if self.readonly or self.selected is None:return
        self.checkpoint()
        self.edges=[e for e in self.edges if self.selected not in e]
        self.enabled=False;self.draw();self.save()
        self.note.configure(text='Selected node disconnected. Reconnect and ENABLE when ready.')

    def checkpoint(self):
        self.history.append(copy.deepcopy((self.nodes,self.edges,self.enabled)))
        self.history=self.history[-40:]
    def undo(self):
        if not self.history or self.readonly:return
        self.nodes,self.edges,self.enabled=self.history.pop()
        self.draw();self.save()
    def duplicate(self):
        if self.readonly or self.selected is None:return
        original=next((n for n in self.nodes if n['id']==self.selected),None)
        if not original:return
        self.checkpoint();node=copy.deepcopy(original)
        node['id']=max(n['id'] for n in self.nodes)+1;node['x']+=35;node['y']+=80
        self.nodes.append(node);self.selected=node['id'];self.enabled=False
        if self.focus_roots is not None:self.focus_roots.append(node['id'])
        self.draw();self.save()
        self.note.configure(text='Node duplicated without connections. Reconnect and ENABLE when ready.')
    def visible_ids(self):
        if self.focus_roots is None:return {n['id'] for n in self.nodes}
        visible=set(self.focus_roots)
        visible.update(n['id'] for n in self.nodes if n.get('section_id')==self.section_id)
        while True:
            expanded=visible|{b for a,b in self.edges if a in visible}
            if expanded==visible:return visible
            visible=expanded
    def show_all(self):
        self.focus_roots=None;self.section_id=None;self.draw()
        self.note.configure(text='All project events. Stage groupings organize editing; execution remains global until state routing is implemented.')
    def focus_stage(self,stage,roots):
        self.section_id=stage['id'];self.focus_roots=list(roots);self.draw();self.canvas.yview_moveto(0)
        self.note.configure(text='GAME FLOW / '+stage['kind']+' / '+stage.get('value','')+' — editing group only; events still execute globally. ALL EVENTS restores the full graph.')
