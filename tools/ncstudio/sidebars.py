"""Project-aware authoring and inspector sidebars shared by every target."""
import json
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox
from theme import BG,PANEL,PANEL_HI,SUNKEN,FG,DIM,CYAN,GREEN,AMBER,RED,UI_BOLD,Button
from ncc.build import project_meta
from ncc.componenttypes import COMPONENTS,ready_for

SYSTEM_TYPES=('Camera','Movement','Interaction','Inventory','Dialogue','Audio','FX','Save Data','Transitions','UI Menu + HUD')

class TabStack(tk.Frame):
    def __init__(self,parent,tabs):
        super().__init__(parent,bg=BG);self.buttons={};self.active=None;self.tabs={}
        bar=tk.Frame(self,bg=BG);bar.pack(fill='x')
        for key,title in tabs.items():
            frame=tk.Frame(self,bg=BG);self.tabs[key]=(title,frame)
            label=tk.Label(bar,text='  '+title+'  ',bg=PANEL,fg=DIM,font=UI_BOLD,pady=4,cursor='hand2')
            label.pack(side='left',padx=(0,2));label.bind('<Button-1>',lambda _e,k=key:self.show(k));self.buttons[key]=label
        self.show(next(iter(tabs)))
    def show(self,key):
        self.active=key
        for name,(_title,frame) in self.tabs.items():
            frame.pack(fill='both',expand=True) if name==key else frame.pack_forget()
            self.buttons[name].configure(bg=PANEL_HI if name==key else PANEL,fg=AMBER if name==key else DIM)

class AuthorSidebar(tk.Frame):
    def __init__(self,parent,on_flow,on_hierarchy,on_ready):
        super().__init__(parent,bg=BG);self.project=None;self.on_flow=on_flow;self.on_hierarchy=on_hierarchy;self.on_ready=on_ready
        self.stack=TabStack(self,{'flow':'GAMEFLOW','systems':'GAME SYSTEMS','hierarchy':'HIERARCHY','ready':'READY OBJECTS'});self.stack.pack(fill='both',expand=True)
        self.flow=self.stack.tabs['flow'][1];self.systems=self.stack.tabs['systems'][1];self.hierarchy=self.stack.tabs['hierarchy'][1];self.ready=self.stack.tabs['ready'][1]
        self.flow_list=self._list(self.flow);self.flow_list.bind('<Double-Button-1>',self.open_flow)
        tk.Label(self.flow,text='Double-click a state to open its executable events.',bg=BG,fg=DIM,wraplength=235,justify='left').pack(fill='x',padx=6,pady=5)
        row=tk.Frame(self.systems,bg=BG);row.pack(fill='x',padx=5,pady=5)
        self.system_choice=ttk.Combobox(row,state='readonly',values=SYSTEM_TYPES,width=17);self.system_choice.current(0);self.system_choice.pack(side='left')
        Button(row,'ADD',self.add_system,CYAN,width=6).pack(side='right')
        self.system_list=self._list(self.systems);self.system_list.bind('<<ListboxSelect>>',self.select_system)
        self.enabled=tk.BooleanVar(value=True)
        tk.Checkbutton(self.systems,text='Active in this project',variable=self.enabled,bg=BG,fg=FG,selectcolor=SUNKEN).pack(anchor='w',padx=6)
        tk.Label(self.systems,text='Modifiers (key=value, comma separated)',bg=BG,fg=DIM).pack(anchor='w',padx=6)
        self.modifiers=ttk.Entry(self.systems);self.modifiers.pack(fill='x',padx=6,pady=4)
        buttons=tk.Frame(self.systems,bg=BG);buttons.pack(fill='x',padx=5)
        Button(buttons,'APPLY',self.apply_system,AMBER).pack(side='left');Button(buttons,'REMOVE',self.remove_system,RED).pack(side='right')
        tk.Label(self.systems,text='Systems activate reusable kits. Their implementation remains target-specific.',bg=BG,fg=DIM,wraplength=235,justify='left').pack(fill='x',padx=6,pady=8)
        self.hierarchy_list=self._list(self.hierarchy);self.hierarchy_list.bind('<<ListboxSelect>>',self.pick_hierarchy)
        self.context=tk.Label(self.hierarchy,text='No active project',bg=BG,fg=DIM,anchor='w');self.context.pack(fill='x',padx=6,pady=5)
        self.ready_list=self._list(self.ready);self.ready_list.bind('<Double-Button-1>',self.add_ready);self.ready_list.bind('<ButtonRelease-1>',self.drop_ready)
        Button(self.ready,'+  ADD GAMEOBJECT',self.add_ready,CYAN).pack(fill='x',padx=5,pady=(0,4))
        tk.Label(self.ready,text='Double-click, or drag toward SCENE, to create at the editor focus. Object types are filtered for the active console.',bg=BG,fg=DIM,wraplength=235,justify='left').pack(fill='x',padx=6,pady=6)
        self.flow_nodes=[];self.system_rows=[];self.hierarchy_keys=[]
    @staticmethod
    def _list(parent):
        box=tk.Listbox(parent,bg=SUNKEN,fg=FG,selectbackground=AMBER,selectforeground=BG,exportselection=False,bd=0,highlightthickness=0)
        box.pack(fill='both',expand=True,padx=5,pady=5);return box
    def load(self,project):
        self.project=project;self.refresh_flow();self.refresh_systems();self.refresh_ready()
    def refresh_ready(self):
        self.ready_list.delete(0,'end');self.ready_rows=[]
        if not self.project:return
        target=project_meta(self.project)['target']
        for name,parts in ready_for(target).items():
            self.ready_rows.append(name);icons=' '.join(COMPONENTS[p]['icon'] for p in parts)
            self.ready_list.insert('end','[%s]  %s'%(icons,name))
        if self.ready_rows:self.ready_list.selection_set(0)
    def add_ready(self,_event=None):
        sel=self.ready_list.curselection()
        if sel:self.on_ready(self.ready_rows[sel[0]],None)
    def drop_ready(self,event):
        sel=self.ready_list.curselection()
        if sel:self.on_ready(self.ready_rows[sel[0]],(event.x_root,event.y_root))
    def refresh_flow(self):
        self.flow_list.delete(0,'end');self.flow_nodes=[]
        if not self.project:return
        try:
            path=Path(self.project)/'game-structure.json';doc=json.loads(path.read_text()) if path.exists() else {'nodes':[]}
            self.flow_nodes=doc.get('nodes',[])
            for i,node in enumerate(self.flow_nodes):
                arrow='  -> ' if i else '     '
                self.flow_list.insert('end','%02d%s%s  %s'%(i+1,arrow,node.get('kind','State'),node.get('value','')))
        except (OSError,ValueError):self.flow_list.insert('end','Invalid game-structure.json')
    def open_flow(self,_event=None):
        sel=self.flow_list.curselection()
        if sel and sel[0]<len(self.flow_nodes):self.on_flow(self.flow_nodes[sel[0]].get('id'))
    def _systems_path(self):return Path(self.project)/'game-systems.json'
    def refresh_systems(self):
        self.system_list.delete(0,'end');self.system_rows=[]
        if not self.project:return
        try:
            path=self._systems_path();doc=json.loads(path.read_text()) if path.exists() else {}
            if doc and doc.get('target')!=project_meta(self.project)['target']:raise ValueError('System target mismatch')
            self.system_rows=doc.get('systems',[])
        except (OSError,ValueError) as exc:messagebox.showerror('Game systems',str(exc),parent=self);return
        if not self.system_rows:self.system_rows=[{'kit':name,'active':False,'modifiers':{}} for name in SYSTEM_TYPES]
        for row in self.system_rows:self.system_list.insert('end',('[ON]  ' if row.get('active',True) else '[OFF] ')+row['kit'])
    def save_systems(self):
        if not self.project:return
        target=project_meta(self.project)['target'];path=self._systems_path();temp=path.with_suffix('.json.tmp')
        temp.write_text(json.dumps({'version':1,'target':target,'systems':self.system_rows},indent=2)+'\n');temp.replace(path);self.refresh_systems()
    def add_system(self):
        name=self.system_choice.get()
        if self.project and name and not any(r['kit']==name for r in self.system_rows):self.system_rows.append({'kit':name,'active':True,'modifiers':{}});self.save_systems()
    def select_system(self,_event=None):
        sel=self.system_list.curselection()
        if not sel:return
        row=self.system_rows[sel[0]];self.enabled.set(row.get('active',True));self.modifiers.delete(0,'end');self.modifiers.insert(0,', '.join('%s=%s'%item for item in row.get('modifiers',{}).items()))
    def apply_system(self):
        sel=self.system_list.curselection()
        if not sel:return
        try:
            mods={}
            for part in filter(None,(p.strip() for p in self.modifiers.get().split(','))):
                key,value=part.split('=',1);mods[key.strip()]=value.strip()
            self.system_rows[sel[0]].update(active=bool(self.enabled.get()),modifiers=mods);self.save_systems()
        except ValueError:messagebox.showerror('Modifiers','Use key=value pairs separated by commas.',parent=self)
    def remove_system(self):
        sel=self.system_list.curselection()
        if sel:self.system_rows.pop(sel[0]);self.save_systems()
    def set_hierarchy(self,title,records):
        self.context.configure(text=title);self.hierarchy_list.delete(0,'end');self.hierarchy_keys=[]
        for row in records:
            self.hierarchy_keys.append(row.get('key'));kind=row.get('component') or row.get('space','object')
            self.hierarchy_list.insert('end','%s  [%s]'%(row.get('name',row.get('key','Object')),kind))
    def set_scene_hierarchy(self,title,world,active_room=0):
        self.context.configure(text=title);self.hierarchy_list.delete(0,'end');self.hierarchy_keys=[]
        active=world.active_screen;world.active_screen=None
        try:
            for screen_key,screen in world.screens.get('screens',{}).items():
                label=screen.get('name',screen_key.replace('_',' ').title())
                self.hierarchy_keys.append(('screen',screen_key));self.hierarchy_list.insert('end','  SCREEN  '+label)
                for index,obj in enumerate(screen.get('objects',[])):
                    self.hierarchy_keys.append(('screen_object',screen_key,'u:'+str(index)))
                    self.hierarchy_list.insert('end','    + '+obj.get('name','UI Object '+str(index)))
            for room,scene in enumerate(world.scenes()):
                name=scene.get('name',scene.get('title',scene.get('id','Scene %d'%room)))
                self.hierarchy_keys.append(('scene',room));self.hierarchy_list.insert('end',('> ' if room==active_room else '  ')+'SCENE %d  %s'%(room,name))
                for record in world.records(room):
                    if record['key'].startswith('t:'):prefix='    [TRIGGER] '
                    elif record.get('component'):prefix='      - '
                    else:prefix='    + '
                    self.hierarchy_keys.append(('object',room,record['key']))
                    self.hierarchy_list.insert('end',prefix+record.get('name',record['key']))
        finally:world.active_screen=active
    def pick_hierarchy(self,_event=None):
        sel=self.hierarchy_list.curselection()
        if sel:self.on_hierarchy(self.hierarchy_keys[sel[0]])

class InspectorSidebar(tk.Frame):
    FIELDS=('name','isActive','visible','tag','state','persistent','position','rotation','scale','size','text','target','fov','image','layer','material','sound','volume','loop','autoplay','spatial','radius')
    def __init__(self,parent,on_apply,on_choose_image=None,on_add_component=None,on_remove_component=None,on_script=None):
        super().__init__(parent,bg=BG);self.on_apply=on_apply;self.on_choose_image=on_choose_image;self.on_add_component=on_add_component;self.on_remove_component=on_remove_component;self.on_script=on_script;self.record=None;self.entries={}
        canvas=tk.Canvas(self,bg=BG,highlightthickness=0,bd=0);scroll=tk.Scrollbar(self,command=canvas.yview,width=11)
        scroll.pack(side='right',fill='y');canvas.pack(side='left',fill='both',expand=True);canvas.configure(yscrollcommand=scroll.set)
        body=tk.Frame(canvas,bg=BG);window=canvas.create_window((0,0),window=body,anchor='nw')
        body.bind('<Configure>',lambda _e:canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>',lambda e:canvas.itemconfigure(window,width=e.width))
        def wheel(event):
            widget=self.winfo_containing(event.x_root,event.y_root)
            while widget is not None:
                if widget is self:canvas.yview_scroll(-1*int(event.delta/120),'units');return 'break'
                widget=getattr(widget,'master',None)
        canvas.bind_all('<MouseWheel>',wheel,add='+')
        self.title=tk.Label(body,text='No GameObject selected',bg=BG,fg=AMBER,font=UI_BOLD,anchor='w');self.title.pack(fill='x',padx=7,pady=7)
        for key in self.FIELDS:
            row=tk.Frame(body,bg=BG);row.pack(fill='x',padx=6,pady=2)
            tk.Label(row,text=key.upper(),bg=BG,fg=DIM,width=10,anchor='w').pack(side='left')
            entry=ttk.Entry(row);entry.pack(side='left',fill='x',expand=True);self.entries[key]=entry
        self.meta=tk.Label(body,bg=BG,fg=DIM,justify='left',anchor='nw',wraplength=270);self.meta.pack(fill='x',padx=7,pady=7)
        tk.Label(body,text='ATTACHED COMPONENTS',bg=BG,fg=CYAN,font=UI_BOLD,anchor='w').pack(fill='x',padx=7,pady=(8,2))
        self.attached=tk.Listbox(body,height=5,bg=SUNKEN,fg=FG,selectbackground=AMBER,selectforeground=BG,exportselection=False,bd=0,highlightthickness=0)
        self.attached.pack(fill='x',padx=7);self.attached.bind('<<ListboxSelect>>',self.select_attached)
        addrow=tk.Frame(body,bg=BG);addrow.pack(fill='x',padx=7,pady=4)
        self.component=ttk.Combobox(addrow,state='readonly',values=list(COMPONENTS));self.component.pack(side='left',fill='x',expand=True);self.component.bind('<<ComboboxSelected>>',self.show_component)
        Button(addrow,'+ ADD',self.add_component,CYAN,width=7).pack(side='right',padx=(4,0))
        self.component_help=tk.Label(body,bg=SUNKEN,fg=FG,justify='left',anchor='nw',wraplength=270);self.component_help.pack(fill='x',padx=7,pady=5)
        actions=tk.Frame(body,bg=BG);actions.pack(fill='x',padx=6)
        Button(actions,'OPEN / CREATE NC-CODE',self.open_script,GREEN).pack(side='left',fill='x',expand=True)
        Button(actions,'REMOVE',self.remove_component,RED,width=7).pack(side='right',padx=(4,0))
        Button(body,'CHOOSE SPRITE IMAGE',self.choose_image,CYAN).pack(fill='x',padx=6,pady=(3,0))
        Button(body,'APPLY EXPOSED PROPERTIES',self.apply,AMBER).pack(fill='x',padx=6,pady=5)
    def choose_image(self):
        if self.record and self.on_choose_image:self.on_choose_image(self.record,self.entries['image'])
    def set_target(self,target):
        self.target=target
        self.component['values']=[name for name,info in COMPONENTS.items() if target in info['targets']]
    def show_component(self,_event=None):
        info=COMPONENTS.get(self.component.get())
        if not info:self.component_help.configure(text='');return
        code='\n'.join(info['code']) or '(native component; callable events pending)'
        self.component_help.configure(text='Modifiers: '+', '.join(info['fields'])+'\n\nNC-CODE:\n'+code)
    def select_attached(self,_event=None):
        sel=self.attached.curselection()
        if sel:self.component.set(self.attached.get(sel[0]));self.show_component()
    def add_component(self):
        if self.record and self.component.get() and self.on_add_component:self.on_add_component(self.record,self.component.get())
    def remove_component(self):
        sel=self.attached.curselection()
        if self.record and sel and self.on_remove_component:self.on_remove_component(self.record,self.attached.get(sel[0]))
    def open_script(self):
        if self.record and self.on_script:self.on_script(self.record)
    def show_record(self,record):
        self.record=record
        for entry in self.entries.values():entry.delete(0,'end')
        self.attached.delete(0,'end')
        if not record:self.title.configure(text='No GameObject selected');self.meta.configure(text='Select an instance in SCENE or HIERARCHY.');return
        self.title.configure(text=record.get('name',record.get('key','GameObject')))
        values={'name':record.get('name',''),'isActive':record.get('isActive',True),'visible':record.get('visible',True),'tag':record.get('tag',''),'state':record.get('state','default'),'persistent':record.get('persistent',False),'position':record.get('pos',[]),'rotation':record.get('rot',[]),'scale':record.get('scale',[]),'size':record.get('size',[]),'text':record.get('text',''),'target':record.get('target',[]),'fov':record.get('fov',''),'image':record.get('image',''),'layer':record.get('layer',''),'material':record.get('material',{}).get('texture',''),'sound':record.get('sound',''),'volume':record.get('volume',''),'loop':record.get('loop',''),'autoplay':record.get('autoplay',''),'spatial':record.get('spatial',''),'radius':record.get('radius','')}
        for key,value in values.items():
            editable=key in ('name','position') or key in record or (key=='material' and 'material' in record)
            self.entries[key].configure(state='normal');self.entries[key].insert(0,', '.join(map(str,value)) if isinstance(value,list) else str(value));self.entries[key].configure(state='normal' if editable and not record.get('readonly') else 'disabled')
        self.meta.configure(text='Key: %s\nSpace: %s\nComponent: %s'%(record.get('key'),record.get('space'),record.get('component') or 'GameObject instance'))
        for name in record.get('components',[]):self.attached.insert('end',name)
        suggested=record.get('component') or ('Sprite2D' if record.get('space')=='2d' else 'Mesh3D')
        if suggested in COMPONENTS:self.component.set(suggested);self.show_component()
    def apply(self):
        if self.record:self.on_apply(self.record,{key:entry.get().strip() for key,entry in self.entries.items()})
