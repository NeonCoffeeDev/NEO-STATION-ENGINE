"""Overall GameFlow map and the contents of each executable state."""
import json
from pathlib import Path
import tkinter as tk
from tkinter import messagebox
from flowpanel import FlowPanel
from ncc import flowkits
from theme import BG,PANEL,SUNKEN,FG,DIM,CYAN,GREEN,AMBER,UI_BOLD,Button

class StructurePanel(FlowPanel):
    filename='game-structure.json'
    def __init__(self,parent,on_events=None,on_scene=None,on_stage=None):
        super().__init__(parent);self.on_events=on_events;self.on_scene=on_scene;self.on_stage=on_stage
        self.canvas.bind('<Double-Button-1>',lambda e:self.open_state())
        self.detail=tk.Frame(self,bg=BG)
        head=tk.Frame(self.detail,bg=PANEL);head.pack(fill='x')
        Button(head,'< GAMEFLOW',self.close_state,CYAN).pack(side='left',padx=5,pady=5)
        self.detail_title=tk.Label(head,text='',bg=PANEL,fg=AMBER,font=UI_BOLD,anchor='w');self.detail_title.pack(side='left',fill='x',expand=True,padx=8)
        Button(head,'OPEN EVENTS',self.open_events,GREEN).pack(side='right',padx=5,pady=5)
        body=tk.PanedWindow(self.detail,orient='vertical',bg='#2e3639',sashwidth=6,bd=0);body.pack(fill='both',expand=True,padx=5,pady=5)
        scene_box=tk.Frame(body,bg=BG);event_box=tk.Frame(body,bg=BG);body.add(scene_box,minsize=130);body.add(event_box,minsize=180)
        tk.Label(scene_box,text='SCENES USED BY THIS GAMEFLOW STATE',bg=BG,fg=CYAN,font=UI_BOLD,anchor='w').pack(fill='x')
        self.scene_list=tk.Listbox(scene_box,bg=SUNKEN,fg=FG,selectbackground=AMBER,selectforeground=BG,bd=0,highlightthickness=0,exportselection=False)
        self.scene_list.pack(fill='both',expand=True,pady=4);self.scene_list.bind('<Double-Button-1>',lambda _e:self.open_scene())
        Button(scene_box,'OPEN SELECTED SCENE',self.open_scene,CYAN).pack(anchor='w')
        tk.Label(event_box,text='EVENTS AND EXECUTION ACTIONS',bg=BG,fg=CYAN,font=UI_BOLD,anchor='w').pack(fill='x')
        self.event_list=tk.Listbox(event_box,bg=SUNKEN,fg=FG,selectbackground=AMBER,selectforeground=BG,bd=0,highlightthickness=0,exportselection=False)
        self.event_list.pack(fill='both',expand=True,pady=4)
        tk.Label(event_box,text='This is a readable state summary. OPEN EVENTS enters the editable execution graph.',bg=BG,fg=DIM,anchor='w').pack(fill='x')
        self.detail_stage=None;self.detail_scenes=[]
    def pick(self,event):
        super().pick(event)
        stage=next((n for n in self.nodes if n['id']==self.selected),None)
        if stage and self.on_stage:self.on_stage(stage)
    def _hide_graph(self):
        for widget in (self.topbar,self.kitbar,self.note,self.horizontal,self.scroll,self.canvas):widget.pack_forget()
    def _show_graph(self):
        self.topbar.pack(fill='x');self.kitbar.pack(fill='x');self.note.pack(fill='x')
        self.horizontal.pack(side='bottom',fill='x');self.scroll.pack(side='right',fill='y');self.canvas.pack(fill='both',expand=True)
    def open_state(self):
        stage=next((n for n in self.nodes if n['id']==self.selected),None)
        if not stage or not self.project:return
        self.detail_stage=stage;self.detail_scenes=list(stage.get('scenes',[]));self.scene_list.delete(0,'end');self.event_list.delete(0,'end')
        self.detail_title.configure(text='%s  /  %s'%(stage.get('kind','STATE'),stage.get('value','')))
        labels=self._scene_labels()
        for i,reference in enumerate(self.detail_scenes):self.scene_list.insert('end','%02d  %s'%(i+1,labels.get(reference,reference)))
        try:
            path=Path(self.project)/'event-flow.json';doc=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'nodes':[],'edges':[]}
            nodes=[n for n in doc.get('nodes',[]) if n.get('section_id')==stage['id']];incoming={n['id']:0 for n in nodes}
            for a,b in doc.get('edges',[]):
                if b in incoming:incoming[b]+=1
            for node in nodes:
                prefix='EVENT' if incoming[node['id']]==0 else '  ACTION'
                self.event_list.insert('end','%-8s  %-20s  %s'%(prefix,node.get('kind',''),node.get('value','')))
            if not nodes:self.event_list.insert('end','(No events assigned yet — OPEN EVENTS to add one)')
        except (OSError,ValueError,KeyError,TypeError) as exc:self.event_list.insert('end','Cannot read events: '+str(exc))
        if self.on_stage:self.on_stage(stage)
        self._hide_graph();self.detail.pack(fill='both',expand=True)
    def _scene_labels(self):
        labels={}
        try:
            root=Path(self.project)
            if (root/'screens.json').exists():
                screens=json.loads((root/'screens.json').read_text(encoding='utf-8')).get('screens',{})
                labels.update(('screen:'+key,'2D SCREEN  /  '+value.get('name',key)) for key,value in screens.items())
            if (root/'world3d.json').exists():labels['world3d']='3D WORLD  /  Main World'
            if (root/'vn.json').exists():
                for scene in json.loads((root/'vn.json').read_text(encoding='utf-8')).get('kit',{}).get('scenes',[]):labels['vn:'+str(scene.get('id',''))]='VN SCENE  /  '+str(scene.get('id',''))
        except (OSError,ValueError,TypeError):pass
        return labels
    def close_state(self):
        self.detail.pack_forget();self._show_graph();self.draw()
    def open_scene(self):
        selected=self.scene_list.curselection()
        if selected and self.detail_stage and self.on_scene:self.on_scene(self.detail_stage,self.detail_scenes[selected[0]])
    def open_events(self):
        if self.detail_stage and self.project and self.on_events:self.on_events(self.detail_stage)
    def load(self,project):
        super().load(project)
        self.kind['values']=['Initialize','Splash','Intro','Title','Menu','Load room','Play','Results','Ending']
        self.kind.current(0)
        self.kit_choice['values']=['Project learning map'];self.kit_choice.current(0)
        self.note.configure(text='One graph shows the overall GameFlow. Double-click a box to open its state workspace with assigned scenes and complete event/action summary.')
        self.detail.pack_forget();self._show_graph()
    def enable(self):
        messagebox.showinfo('GameFlow','Double-click a GameFlow box to inspect its scenes and events. Open Events from that workspace when you want to edit logic.',parent=self)
    def save(self):
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
