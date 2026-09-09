"""Editable source adapters. Coordinates remain in each console's native units."""
import copy
import json
import math
from pathlib import Path

class World:
    def __init__(self, root):
        self.root=Path(root)
        meta=json.loads((self.root/'nc.json').read_text(encoding='utf-8'))
        self.target=meta['target'];self.adapter=meta.get('event_adapter','')
        if self.target=='ps1' and (self.root/'scene.json').exists():self.kind='ps1';name='scene.json'
        elif self.target=='ps2' and (self.root/'vn.json').exists():self.kind='vn';name='vn.json'
        elif self.target=='ps2' and self.adapter=='screen2d_v1' and (self.root/'screens.json').exists():self.kind='screen2d_v1';name='screens.json'
        elif self.adapter in ('fixed_room_v1','lab3d_v1','pad2d_v1'):self.kind=self.adapter;name='room-layout.json'
        else:raise ValueError('This native demo has no editable scene adapter yet.')
        self.path=self.root/name
        self.original=self.path.read_text(encoding='utf-8')
        self.doc=json.loads(self.original)
        if name=='room-layout.json' and (self.doc.get('target')!=self.target or self.doc.get('version')!=1):raise ValueError('Layout target/version mismatch.')
        if self.kind=='fixed_room_v1':
            from .roomlayout import validate as validate_room
            validate_room(self.doc);self.doc.setdefault('materials',{})
        if self.kind == 'lab3d_v1':
            # Version 1 stored only an object's position. Keep those files valid
            # while adding editor/runtime rotation, scale, and a game camera.
            self.doc.setdefault('rotations', {})
            self.doc.setdefault('scales', {})
            for key in self.doc.get('objects', {}):
                self.doc['rotations'].setdefault(key, [0.0, 0.0, 0.0])
                self.doc['scales'].setdefault(key, [1.0, 1.0, 1.0])
            self.doc.setdefault('camera', {
                'pos': [6.0, 4.5, -8.0],
                'target': [0.0, 0.0, 0.0],
                'fov': 60.0,
            })
            self.doc.setdefault('collisions', [])
            self.doc.setdefault('attachments', [])
            self.doc.setdefault('materials', {})
        self.trigger_path=self.root/'triggers.json'
        self.trigger_original=self.trigger_path.read_text(encoding='utf-8') if self.trigger_path.exists() else None
        self.triggers=json.loads(self.trigger_original) if self.trigger_original else dict(version=1,target=self.target,triggers=[])
        if self.triggers.get('target')!=self.target:raise ValueError('Trigger target does not match project.')
        self.screen_path=self.root/'screens.json'
        self.screen_original=self.original if self.path==self.screen_path else (self.screen_path.read_text(encoding='utf-8') if self.screen_path.exists() else None)
        self.screens=self.doc if self.path==self.screen_path else (json.loads(self.screen_original) if self.screen_original else {'version':1,'target':self.target,'screens':{}})
        if self.screens.get('target')!=self.target:raise ValueError('Screen target does not match project.')
        self.active_screen=None
        self.world3d_path=self.root/'world3d.json'
        self.world3d_original=self.world3d_path.read_text(encoding='utf-8') if self.world3d_path.exists() else None
        self.world3d=json.loads(self.world3d_original) if self.world3d_original else None
        if self.world3d and self.world3d.get('target')!=self.target:raise ValueError('3D world target does not match project.')

    def scenes(self):
        if self.kind=='ps1':return self.doc.get('scenes',[self.doc])
        if self.kind=='vn':return self.doc['kit']['scenes']
        if self.kind=='screen2d_v1':return [dict(name=value.get('name',key),screen_key=key) for key,value in self.doc.get('screens',{}).items()]
        return [dict(name='World')]

    def records(self, room):
        rows=[]
        def add(key,name,pos,size,space):rows.append(dict(key=key,name=name,pos=list(pos),size=list(size),space=space))
        if self.kind=='screen2d_v1':
            keys=list(self.doc.get('screens',{}));self.active_screen=keys[min(room,len(keys)-1)] if keys else None
        if self.active_screen and self.active_screen in self.screens.get('screens',{}):
            for i,obj in enumerate(self.screens['screens'][self.active_screen].get('objects',[])):
                add('u:'+str(i),obj.get('name','UI Object '+str(i)),obj.get('rect',[0,0,64,32])[:2],obj.get('rect',[0,0,64,32])[2:],'2d')
                ui_type=obj.get('type','panel');component={'sprite2d':'Sprite2D','text':'Text2D','button':'Button2D','panel':'Panel2D'}.get(ui_type,'Transform')
                rows[-1].update(ui_type=ui_type,text=obj.get('text',''),texture=obj.get('texture',''),image=obj.get('texture',''),layer=obj.get('layer',i),visible=obj.get('visible',True),details=obj.get('details',{}),component=component)
            return sorted(rows,key=lambda row:row.get('layer',0))
        if self.kind=='ps1':
            sc=self.scenes()[room]
            for i,s in enumerate(sc.get('sprites',[])):add('s:'+str(i),s.get('name','Sprite '+str(i)),[s.get('x',0),s.get('y',0)],[s['w'],s['h']],'2d')
            for i,s in enumerate(sc.get('instances',[])):add('m:'+str(i),s.get('name','Mesh '+str(i)),s.get('pos',[0,0,450]),[100,100,100],'3d')
            add('camera','Camera',sc.get('camera',{}).get('pos',[0,0,0]),[30,30,30],'3d')
        elif self.kind=='vn':
            layout=self.doc['kit'].setdefault('layout',{})
            for key,fallback in [('background',[0,0,640,448]),('dialogue',[32,232,576,168])]:
                r=layout.get(key,fallback);add(key,key,r[:2],r[2:],'2d')
            slots=layout.get('portraits',[dict(name='main',rect=layout.get('portrait',[32,24,128,224]))])
            for i,s in enumerate(slots):add('p:'+str(i),s.get('name','Portrait '+str(i)),s['rect'][:2],s['rect'][2:],'2d')
        else:
            for key,pos in self.doc['objects'].items():
                xyz=[pos[0],0,pos[1]] if self.kind=='fixed_room_v1' else pos
                if self.kind=='pad2d_v1':add('o:'+key,key,xyz,[96,96],'2d')
                else:
                    scale = self.doc.get('scales', {}).get(key, [1, 1, 1])
                    row_size = [.4, 1, .4] if self.kind == 'fixed_room_v1' else [2 * v for v in scale]
                    add('o:'+key,key,xyz,row_size,'3d')
                    rows[-1]['rot'] = list(self.doc.get('rotations', {}).get(key, [0, 0, 0]))
                    rows[-1]['scale'] = list(scale)
                    rows[-1]['material'] = self.doc.get('materials', {}).get(key, {})
            if self.kind=='fixed_room_v1':
                for i,camera in enumerate(self.doc['cameras']):
                    add('camera:'+str(i),camera.get('name','Camera '+str(i+1)),camera['pos'],[.35,.35,.35],'3d')
                    rows[-1].update(target=list(camera['target']),fov=camera['fov'])
            if self.kind == 'lab3d_v1':
                camera = self.doc['camera']
                add('camera', 'Game Camera', camera['pos'], [.35, .35, .35], '3d')
                rows[-1]['target'] = list(camera['target'])
                for collision in self.doc['collisions']:
                    owner = self.doc['objects'].get(collision['object'])
                    if owner is None:continue
                    pos = [owner[i] + collision['center'][i] for i in range(3)]
                    add('c:'+str(collision['id']), collision['name'], pos, collision['size'], '3d')
                    rows[-1]['readonly'] = True
                    rows[-1]['component'] = 'collision'
                for point in self.doc['attachments']:
                    owner = self.doc['objects'].get(point['object'])
                    if owner is None:continue
                    pos = [owner[i] + point['pos'][i] for i in range(3)]
                    add('a:'+str(point['id']), point['name'], pos, [.12,.12,.12], '3d')
                    rows[-1]['readonly'] = True
                    rows[-1]['component'] = 'attachment'
        if self.world3d:
            for name,obj in self.world3d.get('objects',{}).items():
                scale=obj.get('scale',[1,1,1]);add('w:'+name,name,obj.get('position',[0,0,0]),[2*v for v in scale],'3d')
                rows[-1].update(rot=list(obj.get('rotation',[0,0,0])),scale=list(scale),material={'texture':obj.get('material','')} if obj.get('material') else {})
            if self.kind=='vn' and self.world3d.get('camera'):
                camera=self.world3d['camera'];add('camera','Main Camera',camera['pos'],[.35,.35,.35],'3d');rows[-1]['target']=camera['target']
            for name,light in self.world3d.get('lights',{}).items():
                add('l:'+name,name,light.get('position',[0,4,-3]),[.3,.3,.3],'3d');rows[-1].update(light=light,editor_only=True)
            for name,shadow in self.world3d.get('shadows',{}).items():
                size=shadow.get('size',[1,.04,1]);add('h:'+name,name,shadow.get('position',[0,-.5,0]),size,'3d');rows[-1].update(shadow=shadow,editor_only=True)
        for t in self.triggers['triggers']:
            if t['room']==room:add('t:'+str(t['id']),t['name'],t['min'],[b-a for a,b in zip(t['min'],t['max'])],t['space'])
        if self.kind=='vn':rows.sort(key=lambda r: 3 if r['key'].startswith('t:') else 2 if r['key']=='dialogue' else 0 if r['key']=='background' else 1)
        for r in rows:r['name']=self.doc.get('editor_names',{}).get(r['key'],r['name'])
        return rows

    def move(self,room,key,pos):
        if key.startswith('u:') and self.active_screen:
            self.screens['screens'][self.active_screen]['objects'][int(key[2:])]['rect'][:2]=list(map(int,pos));return
        if key.startswith('w:') and self.world3d:
            self.world3d['objects'][key[2:]]['position']=list(pos);return
        if key.startswith('l:') and self.world3d:
            self.world3d['lights'][key[2:]]['position']=list(pos);return
        if key.startswith('h:') and self.world3d:
            self.world3d['shadows'][key[2:]]['position']=list(pos);return
        if key.startswith('camera:') and self.kind=='fixed_room_v1':
            self.doc['cameras'][int(key.split(':')[1])]['pos']=list(pos);return
        if key.startswith('t:'):
            t=next(t for t in self.triggers['triggers'] if t['id']==int(key[2:]));size=[b-a for a,b in zip(t['min'],t['max'])]
            pos=list(map(int,pos)) if self.target=='ps1' else pos
            t['min']=list(pos);t['max']=[a+b for a,b in zip(pos,size)];return
        if self.kind=='ps1':
            sc=self.scenes()[room]
            if key.startswith('s:'):sc['sprites'][int(key[2:])].update(x=int(pos[0]),y=int(pos[1]))
            elif key.startswith('m:'):sc['instances'][int(key[2:])]['pos']=list(map(int,pos))
            else:sc.setdefault('camera',{})['pos']=list(map(int,pos))
        elif self.kind=='vn':
            layout=self.doc['kit'].setdefault('layout',{})
            if key.startswith('p:'):
                if 'portraits' not in layout:layout['portraits']=[dict(name='main',rect=layout.get('portrait',[32,24,128,224]))]
                rect=layout['portraits'][int(key[2:])]['rect']
            else:rect=layout.setdefault(key,[0,0,640,448] if key=='background' else [32,232,576,168])
            rect[:2]=list(map(int,pos))
        else:
            if key == 'camera' and self.kind == 'lab3d_v1':
                self.doc['camera']['pos'] = list(pos)
            else:
                self.doc['objects'][key[2:]]=[pos[0],pos[2]] if self.kind=='fixed_room_v1' else list(pos)

    def set_transform(self, key, rotation, scale):
        """Update an editable PS2 3D object's local transform."""
        if key.startswith('w:') and self.world3d:
            obj=self.world3d['objects'][key[2:]];obj['rotation']=list(rotation);obj['scale']=list(scale);return
        if self.kind != 'lab3d_v1' or not key.startswith('o:'):
            raise ValueError('Rotation and scale are available for PS2 3D objects.')
        name = key[2:]
        self.doc['rotations'][name] = list(rotation)
        self.doc['scales'][name] = list(scale)

    def set_material(self, key, texture):
        if key.startswith('w:') and self.world3d:
            self.world3d['objects'][key[2:]]['material']=texture;return
        if self.kind=='fixed_room_v1' and key.startswith('o:'):
            self.doc.setdefault('materials',{})[key[2:]]={'texture':texture};return
        if self.kind != 'lab3d_v1' or not key.startswith('o:'):
            raise ValueError('Materials are currently editable on PS2 3D objects.')
        self.doc.setdefault('materials', {})[key[2:]] = {'texture': texture}

    def validate(self):
        active_screen=self.active_screen
        if self.kind=='screen2d_v1':
            for key,screen in self.screens.get('screens',{}).items():
                for obj in screen.get('objects',[]):
                    rect=obj.get('rect',[])
                    if len(rect)!=4 or any(type(v) not in (int,float) for v in rect):raise ValueError('Screen objects need X, Y, width, height.')
                    x,y,w,h=rect
                    if w<=0 or h<=0 or x<0 or y<0 or x+w>640 or y+h>448:raise ValueError('%s must fit the 640x448 PS2 canvas.'%obj.get('name','Screen object'))
                    texture=obj.get('texture','')
                    if texture and (Path(texture).is_absolute() or Path(texture).suffix.lower()!='.png' or not (self.root/texture).is_file()):raise ValueError('Sprite2D image must reference a project-local PNG.')
        if self.kind=='ps1':
            for sc in self.scenes():
                if len(sc.get('sprites',[]))>64 or len(sc.get('instances',[]))>128:raise ValueError('PS1 room budget: 64 sprites / 128 mesh instances.')
                for obj in sc.get('instances',[]):
                    if len(obj.get('pos',[0,0,450]))!=3:raise ValueError('Mesh needs X,Y,Z position.')
                rot=sc.get('camera',{}).get('rot',[0,0,0])
                if len(rot)!=3 or any(type(v) is not int or not -32768<=v<=32767 for v in rot):raise ValueError('PS1 camera needs three signed 16-bit angles.')
        for room in range(len(self.scenes())):
            for r in self.records(room):
                if any(type(v) not in (int,float) or not math.isfinite(v) or abs(v)>32767 for v in r['pos']+r['size']):raise ValueError('Invalid coordinates: '+r['name'])
                if self.kind=='vn' and r['space']=='2d' and not r['key'].startswith('t:'):
                    x,y=r['pos'];w,h=r['size']
                    if x<0 or y<0 or x+w>640 or y+h>448:raise ValueError('VN layouts must fit 640x448.')
        if self.kind=='fixed_room_v1':
            from .roomlayout import validate
            validate(self.doc)
            for material in self.doc.get('materials',{}).values():
                texture=material.get('texture','')
                if not texture or Path(texture).is_absolute() or Path(texture).suffix.lower()!='.png' or not (self.root/texture).is_file():raise ValueError('Fixed-camera material must reference a project-local PNG.')
        if self.kind=='pad2d_v1':
            if set(self.doc['objects'])!={'box'} or len(self.doc['objects']['box'])!=2:raise ValueError('Pad demo needs one 2D box.')
            x,y=self.doc['objects']['box']
            if not 48<=x<=592 or not 48<=y<=400:raise ValueError('Box center must fit within the 640x448 display.')
        if self.kind=='lab3d_v1':
            if not 1<=len(self.doc['objects'])<=16:raise ValueError('3D Lab supports 1..16 objects.')
            if any(abs(v)>100 for pos in self.doc['objects'].values() for v in pos):raise ValueError('3D Lab positions must be within +/-100.')
            if any(len(v)!=3 for v in self.doc['objects'].values()):raise ValueError('3D objects need X,Y,Z.')
            names = set(self.doc['objects'])
            if set(self.doc['rotations']) != names or set(self.doc['scales']) != names:
                raise ValueError('Every PS2 3D object needs one rotation and scale.')
            for name in names:
                rot = self.doc['rotations'][name]
                scale = self.doc['scales'][name]
                if len(rot) != 3 or any(type(v) not in (int, float) or not math.isfinite(v) or abs(v) > 360 for v in rot):
                    raise ValueError('PS2 3D rotation uses three degree values in -360..360.')
                if len(scale) != 3 or any(type(v) not in (int, float) or not math.isfinite(v) or not .05 <= v <= 20 for v in scale):
                    raise ValueError('PS2 3D scale uses three values in 0.05..20.')
            camera = self.doc['camera']
            if set(camera) != {'pos', 'target', 'fov'}:
                raise ValueError('PS2 3D game camera needs pos, target, and fov.')
            if any(len(camera[key]) != 3 for key in ('pos', 'target')):
                raise ValueError('PS2 3D camera position and target need X,Y,Z.')
            values = camera['pos'] + camera['target'] + [camera['fov']]
            if any(type(v) not in (int, float) or not math.isfinite(v) for v in values):
                raise ValueError('PS2 3D camera values must be finite.')
            if not 20 <= camera['fov'] <= 100:
                raise ValueError('PS2 3D camera FOV must be 20..100 degrees.')
            component_ids=set()
            for kind,rows in (('collision',self.doc['collisions']),('attachment',self.doc['attachments'])):
                if len(rows)>32:raise ValueError('At most 32 %s components.'%kind)
                for row in rows:
                    if type(row.get('id')) is not int or row['id'] in component_ids:raise ValueError('Component IDs must be unique integers.')
                    component_ids.add(row['id'])
                    if row.get('object') not in names:raise ValueError('%s references a missing object.'%kind.title())
                    key='center' if kind=='collision' else 'pos'
                    if len(row.get(key,[]))!=3 or any(type(v) not in (int,float) or not math.isfinite(v) for v in row[key]):raise ValueError('Invalid %s offset.'%kind)
                    if kind=='collision' and (len(row.get('size',[]))!=3 or any(type(v) not in (int,float) or not .05<=v<=100 for v in row['size'])):raise ValueError('Invalid collision size.')
            for name,material in self.doc.get('materials',{}).items():
                if name not in names:raise ValueError('Material references a missing 3D object.')
                texture=material.get('texture','')
                if not texture or Path(texture).is_absolute() or not (self.root/texture).is_file():
                    raise ValueError('Material texture must be a project-relative PNG.')
                if Path(texture).suffix.lower()!='.png':raise ValueError('PS2 material textures must be PNG files.')
        if self.world3d:
            objects=self.world3d.get('objects',{})
            if len(objects)>64:raise ValueError('PS2 shared 3D world supports at most 64 objects.')
            for name,obj in objects.items():
                for field,default in (('position',[0,0,0]),('rotation',[0,0,0]),('scale',[1,1,1])):
                    values=obj.get(field,default)
                    if len(values)!=3 or any(type(v) not in (int,float) or not math.isfinite(v) for v in values):raise ValueError('Invalid 3D %s for %s.'%(field,name))
                texture=obj.get('material','')
                if texture and (Path(texture).is_absolute() or Path(texture).suffix.lower()!='.png' or not (self.root/texture).is_file()):raise ValueError('3D material must reference a project-local PNG.')
            if len(self.world3d.get('lights',{}))>4:raise ValueError('The starter PS2 lighting budget is four lights.')
            for name,light in self.world3d.get('lights',{}).items():
                if len(light.get('position',[]))!=3 or len(light.get('direction',[]))!=3:raise ValueError('Light %s needs position and direction.'%name)
                if not 0<=light.get('intensity',1)<=2 or not 0<=light.get('ambient',.3)<=1:raise ValueError('Light intensity/ambient is outside the PS2 starter range.')
            if len(self.world3d.get('shadows',{}))>32:raise ValueError('The starter PS2 shadow budget is 32 blobs.')
        validate_triggers(self);self.active_screen=active_screen

    def save(self):
        self.validate()
        changes=[(self.path,self.original,self.doc),(self.trigger_path,self.trigger_original,self.triggers)]
        if self.screen_path!=self.path:changes.append((self.screen_path,self.screen_original,self.screens))
        if self.world3d is not None:changes.append((self.world3d_path,self.world3d_original,self.world3d))
        # Check every source before writing either file.
        for path,original,doc in changes:
            if (path.read_text(encoding='utf-8') if path.exists() else None)!=original:raise ValueError('External changes to '+path.name+'; reload before saving.')
        for path,original,doc in changes:
            if original is None and path==self.trigger_path and not doc.get('triggers',[]):continue
            if original is None and path==self.screen_path and not doc.get('screens',{}):continue
            if original is not None and json.loads(original)==doc:continue
            text=json.dumps(doc,indent=2)+'\n';temp=path.with_suffix('.json.tmp');temp.write_text(text,encoding='utf-8');temp.replace(path)
            if path==self.path:self.original=text
            elif path==self.trigger_path:self.trigger_original=text
            elif path==self.screen_path:self.screen_original=text
            else:self.world3d_original=text


def validate_triggers(world):
    doc=world.triggers
    if doc.get('version')!=1 or doc.get('target')!=world.target:raise ValueError('Unsupported trigger format/console.')
    ts=doc['triggers'];ids=set()
    if len(ts)>32:raise ValueError('At most 32 triggers per project.')
    for t in ts:
        if type(t['id']) is not int or not 1<=t['id']<=65535 or t['id'] in ids:raise ValueError('Invalid/duplicate trigger ID.')
        ids.add(t['id'])
        if type(t['room']) is not int or not 0<=t['room']<len(world.scenes()):raise ValueError('Trigger room does not exist.')
        dimensions={'2d':2,'3d':3}.get(t['space'])
        if not dimensions or len(t['min'])!=dimensions or len(t['max'])!=dimensions:raise ValueError('Trigger bounds dimension mismatch.')
        if any(type(v) not in (int,float) or not math.isfinite(v) or abs(v)>32767 for v in t['min']+t['max']):raise ValueError('Trigger bounds must be finite, within +/-32767.')
        if any(a>=b for a,b in zip(t['min'],t['max'])):raise ValueError('Trigger maximum must exceed minimum on every axis.')
        active=world.active_screen;world.active_screen=None
        try:subject=next((r for r in world.records(t['room']) if r['key']==t['subject'] and not r['key'].startswith('t:')),None)
        finally:world.active_screen=active
        if not subject or subject['space']!=t['space'] or subject['key']=='camera':raise ValueError('Trigger needs an existing subject in the same dimension.')
        if world.kind=='vn' and not t['subject'].startswith('p:'):raise ValueError('VN spatial triggers track a portrait slot anchor; select a portrait first.')
        if world.target=='ps1' and any(type(v) is not int for v in t['min']+t['max']):raise ValueError('PS1 trigger bounds must be integers.')
        if world.kind=='fixed_room_v1' and t['subject']!='o:player':raise ValueError('Fixed-room triggers track the player.')


def load_triggers(project):
    if not (Path(project)/'triggers.json').exists():return None,[]
    world=World(project);validate_triggers(world)
    return world,world.triggers['triggers']
