"""Native 2D/orthographic 3D scene authoring, shared across console adapters."""
import copy
import json
import math
import shutil
from PIL import Image, ImageTk
from pathlib import Path
import tkinter as tk
from tkinter import ttk, simpledialog, messagebox, filedialog
from theme import BG,FG,CYAN,AMBER,Button
from ncc.viewportdata import World

class ViewportPanel(tk.Frame):
    def __init__(self,parent):
        super().__init__(parent,bg=BG);self.group=self;self.project=None;self.world=None;self.drafts={};self.history=[];self.selected=None;self.zoom=1.;self.dragging=None
        self.editor_camera={'yaw':.65,'pitch':-.42,'distance':12.0,'target':[0.0,0.0,0.0]}
        self.game_mode=False
        self.output_mode=False
        self.texture_cache={}
        self.interactive=False
        self.draw_job=None
        self.camera_drag=None
        bar=tk.Frame(self,bg=BG);bar.pack(fill='x')
        self.stage=ttk.Combobox(bar,state='readonly',width=28);self.stage.pack(side='left');self.stage.bind('<<ComboboxSelected>>',lambda e:self.change_stage())
        self.room=ttk.Combobox(bar,state='readonly',width=24);self.room.pack(side='left');self.room.bind('<<ComboboxSelected>>',lambda e:self.change_room())
        self.plane=ttk.Combobox(bar,state='readonly',width=13,values=['2D','PERSPECTIVE','XY','XZ','YZ']);self.plane.current(0);self.plane.pack(side='left');self.plane.bind('<<ComboboxSelected>>',lambda e:self.fit())
        self.tool=ttk.Combobox(bar,state='readonly',width=10,values=['MOVE','ROTATE','SCALE']);self.tool.set('MOVE');self.tool.pack(side='left')
        self.axis=ttk.Combobox(bar,state='readonly',width=5,values=['X','Y','Z']);self.axis.set('X');self.axis.pack(side='left')
        for title,fn in [('SAVE',self.save),('RELOAD',self.reload),('UNDO',self.undo),('FIT',self.fit)]:Button(bar,title,fn,CYAN).pack(side='left')
        self.snap=tk.BooleanVar(value=True);tk.Checkbutton(bar,text='Snap',variable=self.snap,bg=BG,fg=FG,selectcolor=BG).pack(side='left')
        body=tk.Frame(self,bg=BG);body.pack(fill='both',expand=True)
        side=tk.Frame(body,bg=BG,width=210);side.pack(side='left',fill='y')
        self.objects=tk.Listbox(side,bg='#10171b',fg=FG,exportselection=False,width=28);self.objects.pack(fill='both',expand=True);self.objects.bind('<<ListboxSelect>>',self.select)
        for title,fn in [('POSITION',self.position),('CAMERA',self.cameras),('RENAME',self.rename),('TRANSFORM',self.properties),('MATERIAL / TEXTURE',self.material),('DUPLICATE OBJECT',self.duplicate),('ADD TRIGGER',self.add_trigger),('TRIGGER BOUNDS',self.bounds),('DELETE TRIGGER',self.delete_trigger)]:Button(side,title,fn,CYAN).pack(fill='x')
        self.canvas=tk.Canvas(body,bg='#10171b',highlightthickness=0);self.canvas.pack(side='left',fill='both',expand=True)
        self.canvas.bind('<Configure>',lambda e:self.request_draw());self.canvas.bind('<Button-1>',self.pick);self.canvas.bind('<B1-Motion>',self.drag);self.canvas.bind('<ButtonRelease-1>',self.end_object_drag);self.canvas.bind('<MouseWheel>',self.wheel)
        self.canvas.bind('<Button-3>',self.camera_press)
        self.canvas.bind('<B3-Motion>',self.camera_orbit)
        self.canvas.bind('<ButtonRelease-3>',self.end_camera_drag)
        self.canvas.bind('<Button-2>',self.camera_press)
        self.canvas.bind('<B2-Motion>',self.camera_pan)
        self.canvas.bind('<ButtonRelease-2>',self.end_camera_drag)
        self.note=tk.Label(self,bg=BG,fg=AMBER,anchor='w',wraplength=950);self.note.pack(fill='x')
        self.photos=[]

    def load(self,project,force=False):
        if project==self.project and not force:
            if self.world and not self.dirty():
                if self.world.path.read_text(encoding='utf-8')!=self.world.original or (self.world.trigger_path.read_text(encoding='utf-8') if self.world.trigger_path.exists() else None)!=self.world.trigger_original or (self.world.screen_path.read_text(encoding='utf-8') if self.world.screen_path.exists() else None)!=self.world.screen_original or (self.world.world3d_path.read_text(encoding='utf-8') if self.world.world3d_path.exists() else None)!=self.world.world3d_original:force=True
            if not force:return
        if self.project and self.world:self.drafts[self.project]=self.world
        self.project=project;self.world=None;self.history=[];self.selected=None;self.room.set('');self.room['values']=[];self.stage.set('');self.stage['values']=[];self.stages=[]
        if project:
            try:
                self.world=World(project) if force or project not in self.drafts else self.drafts[project]
                self.drafts[project]=self.world
                self.room['values']=['%d: %s'%(i,s.get('name',s.get('title',s.get('id','Room')))) for i,s in enumerate(self.world.scenes())]
                self.room.current(0)
                structure=Path(project)/'game-structure.json'
                if structure.exists():
                    self.stages=json.loads(structure.read_text(encoding='utf-8')).get('nodes',[])
                    self.stage['values']=['%s: %s'%(n.get('kind','State'),n.get('value','')) for n in self.stages]
                    if self.stages:self.stage.current(0)
                records=self.world.records(0)
                has_2d=any(r['space']=='2d' for r in records);has_3d=any(r['space']=='3d' for r in records)
                self.plane['values']=(['2D'] if has_2d else [])+(['PERSPECTIVE','XY','XZ','YZ'] if has_3d else [])
                self.plane.set('PERSPECTIVE' if has_3d else '2D')
            except (OSError,ValueError,KeyError,TypeError) as exc:self.note.configure(text=str(exc))
        self.fit()
        if self.world:self.note.configure(text='SCENE editor: place and edit world objects with the free editor camera. The GAME tab renders the placed Main Camera. Select an object, then ADD TRIGGER. SAVE/BUILD applies changes.')

    def dirty(self):
        w=self.world
        return w and (json.loads(w.original)!=w.doc or (json.loads(w.trigger_original) if w.trigger_original else dict(version=1,target=w.target,triggers=[]))!=w.triggers or (json.loads(w.screen_original) if w.screen_original else dict(version=1,target=w.target,screens={}))!=w.screens or (json.loads(w.world3d_original) if w.world3d_original else None)!=w.world3d)
    def reload(self):
        if self.dirty() and not messagebox.askyesno('Reload','Discard unsaved viewport changes?',parent=self):return
        self.load(self.project,True)
    def change_room(self):self.selected=None;self.fit()
    def change_stage(self):
        if not self.world or not self.stages:return
        stage=self.stages[max(0,self.stage.current())]
        screen_key={'Splash':'splash','Menu':'main_menu','Intro':'intro'}.get(stage.get('kind'))
        self.world.active_screen=screen_key if screen_key in self.world.screens.get('screens',{}) else None
        value=str(stage.get('value',''))
        for index,scene in enumerate(self.world.scenes()):
            name=str(scene.get('name',scene.get('title',scene.get('id',''))))
            if name and name==value:
                self.room.current(index);break
        records=self.world.records(self.index());is_2d=any(r['space']=='2d' for r in records)
        self.plane['values']=['2D'] if is_2d else ['PERSPECTIVE','XY','XZ','YZ'];self.plane.set('2D' if is_2d else 'PERSPECTIVE')
        self.selected=None;self.fit()
        self.note.configure(text='%s is selected in GAME FLOW. SCENE and GAME show its assigned project composition.'%stage.get('kind','State'))
    def index(self):return max(0,self.room.current())
    def records(self):return self.world.records(self.index()) if self.world else []
    def axes(self):return {'2D':(0,1),'XY':(0,1),'XZ':(0,2),'YZ':(1,2)}[self.plane.get()]
    def is_perspective(self):return self.plane.get()=='PERSPECTIVE' or self.game_mode
    def visible(self):return [r for r in self.records() if r['space']==('2d' if self.plane.get()=='2D' else '3d')]
    def fit(self):
        self.zoom=1.;rs=self.visible()
        if self.is_perspective():
            objects=[r for r in rs if r['key']!='camera' and not r['key'].startswith('t:')]
            if objects:
                self.editor_camera['target']=[sum(r['pos'][axis] for r in objects)/len(objects) for axis in range(3)]
                span=max([abs(r['pos'][axis]-self.editor_camera['target'][axis]) for r in objects for axis in range(3)]+[2.0])
                self.editor_camera['distance']=max(4.0,span*3.0)
            self.draw();return
        a,b=self.axes()
        if rs:
            xs=[r['pos'][a] for r in rs];ys=[r['pos'][b] for r in rs]
            if self.plane.get()=='2D':xs += [0,640 if self.world.target=='ps2' else 320];ys += [0,448 if self.world.target=='ps2' else 240]
            margin=1 if self.world.target=='ps2' and self.plane.get()!='2D' else 150
            self.extent=(min(xs)-margin,min(ys)-margin,max(xs)+margin,max(ys)+margin)
        else:self.extent=(-3,-2,3,2)
        self.draw()
    def mapping(self):
        x0,y0,x1,y1=getattr(self,'extent',(-3,-2,3,2));w=max(100,self.canvas.winfo_width());h=max(100,self.canvas.winfo_height())
        scale=min((w-40)/max(1,x1-x0),(h-40)/max(1,y1-y0))*self.zoom
        return w/2-(x0+x1)*scale/2,h/2-(y0+y1)*scale/2,scale
    def draw(self):
        self.draw_job=None
        c=self.canvas;c.delete('all');self.photos=[];self.rows=self.visible()
        if not self.interactive:self.objects.delete(0,'end')
        if not self.world:return
        if self.is_perspective():self.draw_perspective();return
        ox,oy,scale=self.mapping();a,b=self.axes()
        if not self.output_mode:
            c.create_line(0,oy,c.winfo_width(),oy,fill='#33434b');c.create_line(ox,0,ox,c.winfo_height(),fill='#33434b')
        if not self.interactive:
            for r in self.rows:self.objects.insert('end',r['key']+' | '+r['name'])
        order=list(enumerate(self.rows))
        if self.world.kind=='ps1' and self.plane.get()=='2D':order.reverse()
        order.sort(key=lambda pair:pair[1]['key'].startswith('t:'))
        for i,r in order:
            if self.output_mode and (r['key'].startswith('t:') or r.get('component')):continue
            x,y=ox+r['pos'][a]*scale,oy+r['pos'][b]*scale
            trigger=r['key'].startswith('t:');flat=r['space']=='2d'
            w,h=r['size'][a]*scale,r['size'][b]*scale
            if not trigger and (not flat or self.world.kind=='pad2d_v1'):x-=max(6,w/2);y-=max(6,h/2)
            w,h=max(12,w),max(12,h)
            color=AMBER if r['key']==self.selected else ('#bd85ff' if trigger else '#ff667f' if r.get('component')=='collision' else '#80ffb0' if r.get('component')=='attachment' else CYAN)
            ui=r.get('ui_type')
            fill='' if trigger else ('#111923' if ui=='panel' else '#29404d' if ui=='button' else '' if ui=='text' else '#23333b')
            outline='' if self.output_mode and ui in ('panel','text') else color
            c.create_rectangle(x,y,x+w,y+h,outline=outline,fill=fill,width=2,tags=('obj',r['key']))
            if flat and not trigger:self.picture(r,x,y,w,h)
            if not flat and r['key'].startswith('m:'):self.mesh_preview(r,ox,oy,scale,a,b,color)
            label=r.get('text') or r['name']
            if r['key'].startswith('u:'):
                c.create_text(x+w/2,y+h/2,text=label,anchor='center',fill=FG,font=('Segoe UI',max(9,min(28,int(h*.35))),'bold'),tags=('obj',r['key']))
            elif not self.output_mode:c.create_text(x+3,y+3,text=label,anchor='nw',fill=FG,tags=('obj',r['key']))
            if r['key']==self.selected and not self.interactive:self.objects.selection_set(i)
        if self.world.kind=='fixed_room_v1':
            for i,yaw in enumerate(self.world.doc['camera_yaw']):
                x=ox-math.sin(yaw)*scale*2;y=oy-math.cos(yaw)*scale*2
                c.create_line(x,y,ox,oy,arrow='last',fill=AMBER,dash=(3,3));c.create_text(x,y,text='Camera '+str(i),fill=FG)
        if not self.output_mode:c.create_text(10,10,anchor='nw',text=self.plane.get()+' authoring view | '+self.world.target.upper(),fill=FG)

    def request_draw(self):
        """Collapse a burst of mouse events into one display refresh."""
        if self.draw_job is None:self.draw_job=self.after(16,self.draw)

    def end_object_drag(self,_event=None):
        self.dragging=None;self.interactive=False;self.draw()

    def end_camera_drag(self,_event=None):
        self.camera_drag=None;self.interactive=False;self.draw()
    def select(self,event=None):
        if self.objects.curselection():self.selected=self.rows[self.objects.curselection()[0]]['key'];self.draw()
    def record(self):return next((r for r in self.records() if r['key']==self.selected),None)
    def checkpoint(self):self.history.append(copy.deepcopy((self.world.doc,self.world.triggers)));self.history=self.history[-40:]
    def pick(self,e):
        tags=self.canvas.gettags('current')
        if len(tags)>1 and tags[0]=='obj':
            self.selected=tags[1];r=self.record()
            if r.get('readonly'):
                self.note.configure(text='This is a GameObject-local component preview. Edit its local offset in the upcoming GameObject editor.')
                self.draw();return
            self.checkpoint();self.dragging=(e.x,e.y,copy.deepcopy(r));self.interactive=True;self.request_draw()
    def drag(self,e):
        if not self.dragging:return
        x,y,start=self.dragging
        if self.is_perspective():
            if start.get('readonly') or not start['key'].startswith(('o:','w:')):return
            axis={'X':0,'Y':1,'Z':2}[self.axis.get()]
            pixels=(e.x-x)-(e.y-y)
            if self.tool.get()=='MOVE':
                pos=list(start['pos']);step=.25 if self.snap.get() else .02
                pos[axis]+=round(pixels/12)*step if self.snap.get() else pixels*step
                self.world.move(self.index(),self.selected,pos)
            elif self.world.kind=='lab3d_v1' or start['key'].startswith('w:'):
                rotation=list(start.get('rot',[0,0,0]));scale3=list(start.get('scale',[1,1,1]))
                if self.tool.get()=='ROTATE':rotation[axis]+=round(pixels/3)*5 if self.snap.get() else pixels*.5
                else:scale3[axis]=max(.05,scale3[axis]+(round(pixels/8)*.1 if self.snap.get() else pixels*.01))
                self.world.set_transform(self.selected,rotation,scale3)
            self.request_draw();return
        _,_,scale=self.mapping();a,b=self.axes();pos=list(start['pos'])
        step=8 if self.plane.get()=='2D' else (.25 if self.world.target=='ps2' else 10)
        pos[a]+=(e.x-x)/scale;pos[b]+=(e.y-y)/scale
        if self.snap.get():pos[a]=round(pos[a]/step)*step;pos[b]=round(pos[b]/step)*step
        self.world.move(self.index(),self.selected,pos);self.request_draw()
    def wheel(self,e):
        if self.is_perspective():self.editor_camera['distance']=max(.5,min(5000,self.editor_camera['distance']*(.88 if e.delta>0 else 1/.88)))
        else:self.zoom=max(.2,min(8,self.zoom*(1.15 if e.delta>0 else 1/1.15)))
        self.request_draw()
    def position(self):
        r=self.record()
        if not r:return
        if r.get('readonly'):
            self.note.configure(text='Collision and attachment offsets belong to the GameObject definition; this world viewport displays them read-only.')
            return
        value=simpledialog.askstring('Position','X,Y for 2D; X,Y,Z for 3D:',initialvalue=', '.join(map(str,r['pos'])),parent=self)
        if value is None:return
        checkpointed=False
        try:
            pos=[float(v) for v in value.split(',')]
            if len(pos)!=len(r['pos']):raise ValueError('Coordinate count mismatch.')
            self.checkpoint();checkpointed=True;self.world.move(self.index(),self.selected,pos);self.world.validate();self.draw()
        except (ValueError,TypeError) as exc:
            if checkpointed:self.undo()
            messagebox.showerror('Position',str(exc),parent=self)
    def rename(self):
        r=self.record()
        if not r:return
        value=simpledialog.askstring('Name','Display name (IDs remain stable):',initialvalue=r['name'],parent=self)
        if not value:return
        self.checkpoint();key=self.selected
        if key.startswith('t:'):next(t for t in self.world.triggers['triggers'] if t['id']==int(key[2:]))['name']=value
        elif key.startswith('u:') and self.world.active_screen:self.world.screens['screens'][self.world.active_screen]['objects'][int(key[2:])]['name']=value
        elif self.world.kind=='ps1' and key[:2] in ('s:','m:'):self.world.scenes()[self.index()]['sprites' if key.startswith('s:') else 'instances'][int(key[2:])]['name']=value
        else:self.world.doc.setdefault('editor_names',{})[key]=value
        self.draw()
    def duplicate(self):
        r=self.record()
        if not r or r['key'].startswith('t:') or r.get('readonly'):return
        key=r['key'];self.checkpoint()
        if self.world.kind=='ps1' and key[:2] in ('s:','m:'):
            rows=self.world.scenes()[self.index()]['sprites' if key.startswith('s:') else 'instances'];clone=copy.deepcopy(rows[int(key[2:])]);clone['name']=r['name']+' copy';rows.append(clone);self.selected=key[:2]+str(len(rows)-1)
        elif self.world.kind=='lab3d_v1':
            objects=self.world.doc['objects'];name='object_'+str(len(objects));
            while name in objects:name+='x'
            if len(objects)>=16:messagebox.showerror('Budget','At most 16 wireframe objects.',parent=self);return
            objects[name]=list(r['pos'])
            self.world.doc['rotations'][name]=list(r.get('rot',[0,0,0]))
            self.world.doc['scales'][name]=list(r.get('scale',[1,1,1]))
            self.selected='o:'+name
        else:self.note.configure(text='This adapter has fixed layout roles. Use ROOM to add VN portrait slots.');return
        self.draw()
    def add_trigger(self):
        r=self.record()
        if not r or r['key'].startswith('t:') or r['key']=='camera' or r.get('readonly'):self.note.configure(text='Select a world object instance for this trigger to track.');return
        if self.world.kind=='fixed_room_v1' and r['key']!='o:player':self.note.configure(text='Select player: fixed-room triggers track player position.');return
        if self.world.kind=='vn' and not r['key'].startswith('p:'):self.note.configure(text='Select a portrait slot: VN triggers use that slot anchor and scene, not a player collider.');return
        ts=self.world.triggers['triggers']
        if len(ts)>=32:messagebox.showerror('Trigger budget','At most 32 triggers.',parent=self);return
        self.checkpoint();i=max([t['id'] for t in ts],default=0)+1
        size=[32]*2 if r['space']=='2d' else ([1]*3 if self.world.target=='ps2' else [200]*3)
        low=list(r['pos']);ts.append(dict(id=i,name='Trigger '+str(i),room=self.index(),subject=r['key'],space=r['space'],min=low,max=[a+b for a,b in zip(low,size)]));self.selected='t:'+str(i);self.draw()
        self.note.configure(text='Trigger %d tracks %s. Drag to place; TRIGGER BOUNDS changes its size. Use On trigger enter/exit with ID %d in a flow box.'%(i,r['key'],i))
    def bounds(self):
        r=self.record()
        if not r or not r['key'].startswith('t:'):return
        t=next(t for t in self.world.triggers['triggers'] if t['id']==int(r['key'][2:]))
        value=simpledialog.askstring('Trigger bounds','Minimum coordinates, then maximum coordinates:',initialvalue=', '.join(map(str,t['min']+t['max'])),parent=self)
        if value is None:return
        checkpointed=False
        try:
            vals=[int(v) if self.world.target=='ps1' else float(v) for v in value.split(',')];n=len(t['min'])
            if len(vals)!=2*n:raise ValueError('Wrong number of bounds.')
            self.checkpoint();checkpointed=True;t['min']=vals[:n];t['max']=vals[n:];self.world.validate();self.draw()
        except (ValueError,TypeError) as exc:
            if checkpointed:self.undo()
            messagebox.showerror('Trigger',str(exc),parent=self)
    def delete_trigger(self):
        if self.selected and self.selected.startswith('t:'):
            self.checkpoint();self.world.triggers['triggers']=[t for t in self.world.triggers['triggers'] if t['id']!=int(self.selected[2:])];self.selected=None;self.draw()
    def undo(self):
        if self.history:self.world.doc,self.world.triggers=self.history.pop();self.draw()
    def save(self):
        if not self.world:return True
        try:self.world.save();self.note.configure(text='Saved source layout and triggers. Build to apply.');return True
        except (OSError,ValueError,KeyError,TypeError) as exc:messagebox.showerror('Viewport save',str(exc),parent=self);return False
    def save_pending(self):
        if self.world:self.drafts[self.project]=self.world
        for world in self.drafts.values():
            try:
                dirty=json.loads(world.original)!=world.doc or (json.loads(world.trigger_original) if world.trigger_original else dict(version=1,target=world.target,triggers=[]))!=world.triggers or (json.loads(world.screen_original) if world.screen_original else dict(version=1,target=world.target,screens={}))!=world.screens or (json.loads(world.world3d_original) if world.world3d_original else None)!=world.world3d
                if dirty:world.save()
            except (OSError,ValueError,KeyError,TypeError) as exc:messagebox.showerror('Viewport save',str(exc),parent=self);return False
        return True

    # ---- perspective workspace -----------------------------------------

    @staticmethod
    def _sub(a,b):return [a[i]-b[i] for i in range(3)]
    @staticmethod
    def _add(a,b):return [a[i]+b[i] for i in range(3)]
    @staticmethod
    def _mul(a,value):return [v*value for v in a]
    @staticmethod
    def _dot(a,b):return sum(a[i]*b[i] for i in range(3))
    @staticmethod
    def _cross(a,b):return [a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]]
    @classmethod
    def _normal(cls,value):
        length=max(1e-9,math.sqrt(cls._dot(value,value)))
        return [v/length for v in value]

    def camera_basis(self):
        """Return position/target/FOV without coupling editor and game cameras."""
        if self.game_mode:
            if self.world.kind=='lab3d_v1':
                camera=self.world.doc['camera']
                return list(camera['pos']),list(camera['target']),float(camera['fov'])
            if self.world.kind=='fixed_room_v1':
                yaw=float(self.world.doc['camera_yaw'][0])
                return [-math.sin(yaw)*10,5,-math.cos(yaw)*10],[0,0,0],55
            if self.world.world3d and self.world.world3d.get('camera'):
                camera=self.world.world3d['camera']
                return list(camera['pos']),list(camera['target']),float(camera.get('fov',55))
            if self.world.kind=='ps1':
                camera=self.world.scenes()[self.index()].get('camera',{})
                pos=list(camera.get('pos',[0,0,0]));rot=camera.get('rot',[0,0,0])
                yaw=float(rot[1])*math.pi/2048
                return pos,[pos[0]+math.sin(yaw),pos[1],pos[2]+math.cos(yaw)],55
        camera=self.editor_camera
        target=list(camera['target']);yaw=camera['yaw'];pitch=camera['pitch'];distance=camera['distance']
        offset=[math.sin(yaw)*math.cos(pitch)*distance,-math.sin(pitch)*distance,-math.cos(yaw)*math.cos(pitch)*distance]
        return self._add(target,offset),target,60

    def projector(self):
        pos,target,fov=self.camera_basis();forward=self._normal(self._sub(target,pos))
        right=self._normal(self._cross(forward,[0,1,0]))
        up=self._normal(self._cross(right,forward))
        width=max(100,self.canvas.winfo_width());height=max(100,self.canvas.winfo_height())
        focal=(height*.5)/math.tan(math.radians(fov)*.5)
        def project(point):
            delta=self._sub(point,pos);depth=self._dot(delta,forward)
            if depth<=.05:return None
            return (width*.5+self._dot(delta,right)*focal/depth,
                    height*.5-self._dot(delta,up)*focal/depth,depth)
        return project

    @staticmethod
    def box_geometry(low,high):
        points=[[high[0] if i&1 else low[0],high[1] if i&2 else low[1],high[2] if i&4 else low[2]] for i in range(8)]
        edges=((0,1),(1,3),(3,2),(2,0),(4,5),(5,7),(7,6),(6,4),(0,4),(1,5),(2,6),(3,7))
        return points,edges

    def geometry(self,record):
        key=record['key']
        if key.startswith('t:'):
            trigger=next(t for t in self.world.triggers['triggers'] if t['id']==int(key[2:]))
            return self.box_geometry(trigger['min'],trigger['max'])
        if self.world.kind=='ps1' and key.startswith('m:'):
            instance=self.world.scenes()[self.index()]['instances'][int(key[2:])]
            meshes=self.world.doc.get('meshes',[]);ref=instance.get('mesh',0)
            mesh=next((m for i,m in enumerate(meshes) if i==ref or m.get('name')==ref),{})
            points=[self.transform_point(v[:3],record['pos'],instance.get('rot',[0,0,0]),[1,1,1],ps1=True) for v in mesh.get('verts',[])]
            edges=set()
            for face in mesh.get('quads',[]):
                for a,b in zip(face,face[1:]+face[:1]):edges.add(tuple(sorted((a,b))))
            return points,sorted(edges)
        if (self.world.kind=='lab3d_v1' and key.startswith('o:')) or key.startswith('w:'):
            points,edges=self.box_geometry([-1,-1,-1],[1,1,1])
            return [self.transform_point(v,record['pos'],record.get('rot',[0,0,0]),record.get('scale',[1,1,1])) for v in points],edges
        half=[max(.05,v*.5) for v in record['size']]
        return self.box_geometry([record['pos'][i]-half[i] for i in range(3)],[record['pos'][i]+half[i] for i in range(3)])

    @staticmethod
    def transform_point(point,position,rotation,scale,ps1=False):
        x,y,z=[point[i]*scale[i] for i in range(3)]
        factor=math.pi/2048 if ps1 else math.pi/180
        ax,ay,az=[v*factor for v in rotation]
        y,z=y*math.cos(ax)-z*math.sin(ax),y*math.sin(ax)+z*math.cos(ax)
        x,z=x*math.cos(ay)+z*math.sin(ay),-x*math.sin(ay)+z*math.cos(ay)
        x,y=x*math.cos(az)-y*math.sin(az),x*math.sin(az)+y*math.cos(az)
        return [x+position[0],y+position[1],z+position[2]]

    def draw_perspective(self):
        c=self.canvas;project=self.projector()
        if not self.interactive:
            for r in self.rows:self.objects.insert('end',r['key']+' | '+r['name'])
        # Editor grid is world XZ; it is never part of the camera output.
        if not self.output_mode:
            for value in range(-10,11):
                for a,b in [([-10,0,value],[10,0,value]),([value,0,-10],[value,0,10])]:
                    pa,pb=project(a),project(b)
                    if pa and pb:c.create_line(pa[0],pa[1],pb[0],pb[1],fill='#263941')
        drawn=[]
        for index,r in enumerate(self.rows):
            if self.output_mode and (r['key'].startswith('t:') or r.get('component') or r['key']=='camera'):continue
            color=AMBER if r['key']==self.selected else ('#bd85ff' if r['key'].startswith('t:') else '#ff667f' if r.get('component')=='collision' else '#80ffb0' if r.get('component')=='attachment' else CYAN)
            points,edges=self.geometry(r);screen=[project(p) for p in points]
            material=r.get('material',{}).get('texture')
            renderable=not r['key'].startswith('t:') and not r.get('component') and r['key']!='camera'
            if renderable and material and len(screen)==8:self.draw_box_surfaces(c,screen,material,r['key'])
            if not self.output_mode or (renderable and not material):
                for a,b in edges:
                    if a<len(screen) and b<len(screen) and screen[a] and screen[b]:
                        c.create_line(screen[a][0],screen[a][1],screen[b][0],screen[b][1],fill=color,width=2,tags=('obj',r['key']))
            origin=project(r['pos'])
            if origin and not self.output_mode:
                x,y,_=origin;c.create_line(x-5,y,x+5,y,fill=AMBER,tags=('obj',r['key']));c.create_line(x,y-5,x,y+5,fill=AMBER,tags=('obj',r['key']))
                c.create_text(x+7,y+7,text=r['name'],anchor='nw',fill=FG,tags=('obj',r['key']))
            if r['key']==self.selected and not self.interactive:self.objects.selection_set(index)
        mode='GAME VIEWPORT / MAIN CAMERA' if self.game_mode else 'SCENE / EDITOR CAMERA (right orbit / middle pan / wheel dolly)'
        if not self.output_mode:c.create_text(10,10,anchor='nw',text=mode+' | '+self.world.target.upper(),fill=FG)

    def draw_box_surfaces(self,canvas,screen,material,key):
        """Draw a cube as filled, depth-sorted faces with sampled texture cells."""
        faces=((0,1,3,2),(4,5,7,6),(0,1,5,4),(2,3,7,6),(0,2,6,4),(1,3,7,5))
        visible=[face for face in faces if all(screen[i] for i in face)]
        visible.sort(key=lambda face:sum(screen[i][2] for i in face)/4,reverse=True)
        image=None
        if material:
            try:
                image=self.texture_cache.get(material)
                if image is None:
                    with Image.open(self.world.root/material) as source:
                        image=source.convert('RGB');image.thumbnail((64,64),Image.Resampling.NEAREST)
                    self.texture_cache[material]=image
            except (OSError,ValueError):image=None
        cells=1 if self.interactive else 4
        for face in visible:
            corners=[screen[i] for i in face]
            if image:
                for v in range(cells):
                    for u in range(cells):
                        points=[self.bilerp(corners,u/cells,v/cells),self.bilerp(corners,(u+1)/cells,v/cells),self.bilerp(corners,(u+1)/cells,(v+1)/cells),self.bilerp(corners,u/cells,(v+1)/cells)]
                        sample=(min(image.width-1,int((u+.5)*image.width/cells)),min(image.height-1,int((v+.5)*image.height/cells)))
                        rgb=image.getpixel(sample);fill='#%02x%02x%02x'%rgb
                        canvas.create_polygon(*[n for p in points for n in p],fill=fill,outline=fill,tags=('obj',key))
            else:
                canvas.create_polygon(*[n for i in face for n in screen[i][:2]],fill='#29404d',outline='',tags=('obj',key))

    @staticmethod
    def bilerp(corners,u,v):
        top=[corners[0][i]*(1-u)+corners[1][i]*u for i in range(2)]
        bottom=[corners[3][i]*(1-u)+corners[2][i]*u for i in range(2)]
        return [top[i]*(1-v)+bottom[i]*v for i in range(2)]

    def material_color(self,relative):
        try:
            with Image.open(self.world.root/relative) as image:
                image.thumbnail((32,32));rgb=image.convert('RGB').resize((1,1)).getpixel((0,0))
            return '#%02x%02x%02x'%rgb
        except (OSError,ValueError):return '#39454d'

    def camera_press(self,event):self.camera_drag=(event.x,event.y,list(self.editor_camera['target']));self.interactive=True
    def camera_orbit(self,event):
        if not self.camera_drag or self.plane.get()!='PERSPECTIVE':return
        x,y,_=self.camera_drag;self.editor_camera['yaw']+=(event.x-x)*.008;self.editor_camera['pitch']=max(-1.45,min(1.45,self.editor_camera['pitch']+(event.y-y)*.008));self.camera_drag=(event.x,event.y,list(self.editor_camera['target']));self.request_draw()
    def camera_pan(self,event):
        if not self.camera_drag or self.plane.get()!='PERSPECTIVE':return
        x,y,start=self.camera_drag;distance=self.editor_camera['distance'];scale=max(.002,distance*.0015)
        yaw=self.editor_camera['yaw'];right=[math.cos(yaw),0,math.sin(yaw)]
        self.editor_camera['target']=[start[i]-right[i]*(event.x-x)*scale for i in range(3)]
        self.editor_camera['target'][1]+= (event.y-y)*scale
        self.request_draw()

    def picture(self,r,x,y,w,h):
        path=None;crop=None;portrait=False
        if self.world.kind=='ps1' and r['key'].startswith('s:'):
            sprite=self.world.scenes()[self.index()]['sprites'][int(r['key'][2:])]
            path=next((t['file'] for t in self.world.doc.get('textures',[]) if t['name']==sprite.get('texture')),None)
            u,v=sprite.get('u',0),sprite.get('v',0);crop=(u,v,u+sprite['w'],v+sprite['h'])
        elif self.world.kind=='vn':
            if r['key']=='background':path=self.world.scenes()[self.index()].get('background')
            elif r['key'].startswith('p:'):
                chars=self.world.doc['kit'].get('characters',[])
                if chars:path=chars[min(int(r['key'][2:]),len(chars)-1)].get('portrait');portrait=True
        if r['key'].startswith('u:'):path=r.get('texture') or None
        if not path:return
        try:
            with Image.open(self.world.root/path) as im:image=im.convert('RGBA')
            if crop:image=image.crop(crop)
            size=(max(1,min(2048,int(w))),max(1,min(2048,int(h))))
            if portrait:image.thumbnail(size,Image.Resampling.NEAREST)
            else:image=image.resize(size,Image.Resampling.NEAREST)
            photo=ImageTk.PhotoImage(image);self.photos.append(photo)
            self.canvas.create_image(x,y+h if portrait else y,anchor='sw' if portrait else 'nw',image=photo,tags=('obj',r['key']))
        except (OSError,ValueError):pass

    def mesh_preview(self,r,ox,oy,scale,a,b,color):
        instance=self.world.scenes()[self.index()]['instances'][int(r['key'][2:])]
        meshes=self.world.doc.get('meshes',[]);ref=instance.get('mesh',0)
        mesh=next((m for i,m in enumerate(meshes) if i==ref or m.get('name')==ref),{})
        vertices=mesh.get('verts',[])
        # Orthographic wireframe uses authored translation and rotation.
        angles=[v*math.pi/2048 for v in instance.get('rot',[0,0,0])]
        points=[]
        for vertex in vertices:
            x,y,z=vertex[:3];rx,ry,rz=angles
            y,z=y*math.cos(rx)-z*math.sin(rx),y*math.sin(rx)+z*math.cos(rx)
            x,z=x*math.cos(ry)+z*math.sin(ry),-x*math.sin(ry)+z*math.cos(ry)
            x,y=x*math.cos(rz)-y*math.sin(rz),x*math.sin(rz)+y*math.cos(rz)
            p=[x+r['pos'][0],y+r['pos'][1],z+r['pos'][2]];points.append((ox+p[a]*scale,oy+p[b]*scale))
        for face in mesh.get('quads',[]):
            if not all(type(i) is int and 0<=i<len(points) for i in face):continue
            coords=[c for i in list(face)+[face[0]] for c in points[i]]
            self.canvas.create_line(*coords,fill=color,tags=('obj',r['key']))

    def cameras(self):
        if not self.world:return
        if self.world.kind=='fixed_room_v1':
            old=self.world.doc['camera_yaw'];caption='Three camera yaw angles, radians:'
        elif self.world.kind=='ps1':
            old=self.world.scenes()[self.index()].get('camera',{}).get('rot',[0,0,0]);caption='Camera X,Y,Z rotation; 4096 = one turn:'
        elif self.world.kind=='lab3d_v1':
            camera=self.world.doc['camera'];old=camera['pos']+camera['target']+[camera['fov']]
            caption='Game camera position X,Y,Z, target X,Y,Z, FOV:'
        else:self.note.configure(text='This adapter has no editable fixed-camera angles.');return
        value=simpledialog.askstring('Camera',caption,initialvalue=', '.join(map(str,old)),parent=self)
        if value is None:return
        checkpointed=False
        try:
            vals=[float(v) if self.world.kind in ('fixed_room_v1','lab3d_v1') else int(v) for v in value.split(',')]
            required=7 if self.world.kind=='lab3d_v1' else 3
            if len(vals)!=required:raise ValueError('%d values required.'%required)
            self.checkpoint();checkpointed=True
            if self.world.kind=='fixed_room_v1':self.world.doc['camera_yaw']=vals
            elif self.world.kind=='lab3d_v1':
                self.world.doc['camera']={'pos':vals[:3],'target':vals[3:6],'fov':vals[6]}
            else:self.world.scenes()[self.index()].setdefault('camera',{})['rot']=vals
            self.world.validate();self.draw()
        except (ValueError,TypeError) as exc:
            if checkpointed:self.undo()
            messagebox.showerror('Camera',str(exc),parent=self)

    def properties(self):
        r=self.record()
        if not r:return
        if r.get('readonly'):
            self.note.configure(text='Open this component in the GameObject editor to change its local properties.')
            return
        if r['key'].startswith('t:'):self.bounds();return
        key=r['key'];obj=None;field=None
        if self.world.kind=='ps1' and key.startswith('m:'):
            obj=self.world.scenes()[self.index()]['instances'][int(key[2:])];field='rot';old=obj.get('rot',[0,0,0]);caption='Rotation X,Y,Z; 4096 = a turn:'
        elif self.world.kind=='ps1' and key.startswith('s:'):
            obj=self.world.scenes()[self.index()]['sprites'][int(key[2:])];field='size';old=[obj['w'],obj['h']];caption='Width, height in pixels:'
        elif self.world.kind=='vn':
            self.note.configure(text='Use ROOM for portrait size, image replacement and layers. VIEWPORT positions the same source layout.');return
        elif (self.world.kind=='lab3d_v1' and key.startswith('o:')) or key.startswith('w:'):
            old=r.get('rot',[0,0,0])+r.get('scale',[1,1,1]);field='transform'
            caption='Rotation degrees X,Y,Z, then scale X,Y,Z:'
        else:self.note.configure(text='This adapter has fixed object geometry.');return
        value=simpledialog.askstring('Object properties',caption,initialvalue=', '.join(map(str,old)),parent=self)
        if value is None:return
        try:
            values=[float(v) if field=='transform' else int(v) for v in value.split(',')]
            if len(values)!=len(old) or any(abs(v)>32767 for v in values):raise ValueError('Invalid property values.')
            if field=='size' and (min(values)<1 or max(values)>1024):raise ValueError('Sprite size must be 1..1024 pixels.')
            self.checkpoint()
            if field=='size':obj['w'],obj['h']=values
            elif field=='transform':self.world.set_transform(key,values[:3],values[3:])
            else:obj[field]=values
            self.world.validate();self.draw()
        except (ValueError,TypeError) as exc:messagebox.showerror('Properties',str(exc),parent=self)

    def material(self):
        r=self.record()
        if not r or not ((self.world.kind in ('lab3d_v1','fixed_room_v1') and r['key'].startswith('o:')) or r['key'].startswith('w:')):
            self.note.configure(text='Select a PS2 3D object to assign a material texture.');return
        source=filedialog.askopenfilename(parent=self,title='Choose PS2 material texture',filetypes=[('PNG texture','*.png')])
        if not source:return
        try:
            with Image.open(source) as image:
                width,height=image.size
            if width>512 or height>512:raise ValueError('PS2 editor material limit is 512x512. Resize this texture first.')
            folder=self.world.root/'textures';folder.mkdir(exist_ok=True)
            destination=folder/Path(source).name
            if Path(source).resolve()!=destination.resolve():shutil.copy2(source,destination)
            self.checkpoint();self.world.set_material(r['key'],destination.relative_to(self.world.root).as_posix())
            self.world.validate();self.draw()
            self.note.configure(text='Assigned %s. The desktop Scene/Game renderer previews the material; SAVE makes it project data.'%destination.name)
        except (OSError,ValueError) as exc:messagebox.showerror('Material',str(exc),parent=self)

    def render_game(self, canvas, object_sink):
        """Render the active room through its placed Main Camera.

        GAME borrows the scene renderer but never its editor camera or editing
        bindings.  Keeping one renderer also prevents the Scene and Game tabs
        from disagreeing about transforms while this preview is still a
        desktop approximation of the console renderer.
        """
        if not self.world:
            canvas.delete('all')
            return
        old_canvas,old_objects,old_rows=self.canvas,self.objects,getattr(self,'rows',[])
        old_mode,old_output,old_plane,old_extent=self.game_mode,self.output_mode,self.plane.get(),getattr(self,'extent',None)
        try:
            self.canvas=canvas;self.objects=object_sink
            records=self.records()
            has_3d=any(r['space']=='3d' for r in records)
            is_2d=bool(self.world.active_screen) or not has_3d or self.plane.get()=='2D'
            self.game_mode=not is_2d;self.output_mode=True
            self.plane.set('2D' if is_2d else 'PERSPECTIVE')
            if is_2d:
                width=640 if self.world.target=='ps2' else 320
                height=448 if self.world.target=='ps2' else 240
                self.extent=(0,0,width,height)
            self.draw()
        finally:
            self.canvas=old_canvas;self.objects=old_objects;self.rows=old_rows
            self.game_mode=old_mode;self.output_mode=old_output;self.plane.set(old_plane)
            if old_extent is None:
                self.__dict__.pop('extent',None)
            else:self.extent=old_extent


class GamePanel(tk.Frame):
    """Read-only target viewport driven by the Scene editor's Main Camera."""
    def __init__(self,parent,scene_editor):
        super().__init__(parent,bg=BG);self.group=self;self.scene_editor=scene_editor
        bar=tk.Frame(self,bg=BG);bar.pack(fill='x')
        tk.Label(bar,text='GAME VIEWPORT  |  MAIN CAMERA',bg=BG,fg=AMBER).pack(side='left',padx=8,pady=5)
        Button(bar,'REFRESH',self.refresh,CYAN).pack(side='left')
        self.status=tk.Label(bar,text='',bg=BG,fg=FG);self.status.pack(side='right',padx=8)
        self.canvas=tk.Canvas(self,bg='#10171b',highlightthickness=0)
        self.canvas.pack(fill='both',expand=True,padx=8,pady=8)
        self.canvas.bind('<Configure>',lambda _e:self.refresh())
        self.sink=tk.Listbox(self)
        self.note=tk.Label(self,text='Read-only output. Edit objects and the Main Camera in SCENE.',bg=BG,fg=AMBER,anchor='w')
        self.note.pack(fill='x',padx=8,pady=(0,6))

    def load(self,project):
        self.scene_editor.load(project)
        self.refresh()

    def refresh(self):
        world=self.scene_editor.world
        if not world:
            self.canvas.delete('all');self.status.configure(text='NO EDITABLE CAMERA');return
        width,height=((640,448) if world.target=='ps2' else (320,240))
        self.status.configure(text='%s  %d x %d'%(world.target.upper(),width,height))
        self.scene_editor.render_game(self.canvas,self.sink)
