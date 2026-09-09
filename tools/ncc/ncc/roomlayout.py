"""Authoring data for the PS2 fixed-room prototype, shared with Studio."""
import json
import math
from pathlib import Path

DEFAULT = {'version':1,'target':'ps2','objects':{
    'player':[-2,0], 'key':[-2,1.5], 'door':[2,0]},
    'cameras':[
        {'name':'Camera A','pos':[-4,4,-8],'target':[0,0,0],'fov':55},
        {'name':'Camera B','pos':[5,3,-6],'target':[0,0,0],'fov':55},
        {'name':'Camera C','pos':[0,6,7],'target':[0,0,0],'fov':50}]}

def validate(doc):
    if doc.get('target')!='ps2' or doc.get('version')!=1:raise ValueError('Unsupported room layout target/version.')
    if set(doc['objects'])!=set(DEFAULT['objects']):raise ValueError('This prototype supports player, key and door only.')
    for name,xy in doc['objects'].items():
        if len(xy)!=2 or any(type(v) not in (int,float) or not math.isfinite(v) for v in xy):raise ValueError('Invalid position: '+name)
        maxx,maxz=(2,1.2) if name=='door' else (3,2)
        if not (-maxx<=xy[0]<=maxx and -maxz<=xy[1]<=maxz):raise ValueError('Position outside editable room: '+name)
    if 'cameras' not in doc:
        yaw=doc.pop('camera_yaw',[0.45,-0.65,0.0]);doc['cameras']=[]
        for i,value in enumerate(yaw):doc['cameras'].append({'name':'Camera '+chr(65+i),'pos':[-math.sin(value)*10,5,-math.cos(value)*10],'target':[0,0,0],'fov':55})
    if not 1<=len(doc['cameras'])<=8:raise ValueError('Fixed rooms support 1..8 cameras.')
    for camera in doc['cameras']:
        if len(camera.get('pos',[]))!=3 or len(camera.get('target',[]))!=3:raise ValueError('Each camera needs position and target X,Y,Z.')
        if not 20<=camera.get('fov',0)<=100:raise ValueError('Camera FOV must be 20..100 degrees.')
    return doc

def load(root):
    p=Path(root)/'room-layout.json'
    return validate(json.loads(p.read_text()) if p.exists() else json.loads(json.dumps(DEFAULT)))

def compile_project(root):
    doc=load(root);lines=['/* Generated from room-layout.json. */']
    for name,xy in doc['objects'].items():
        for axis,value in zip(('X','Z'),xy):lines.append('#define ROOM_%s_%s %.8ff'%(name.upper(),axis,value))
    lines.append('#define ROOM_CAMERA_COUNT %d'%len(doc['cameras']))
    lines.append('static const float room_camera_pos[ROOM_CAMERA_COUNT][3]={%s};'%', '.join('{%s}'%', '.join('%.8ff'%v for v in c['pos']) for c in doc['cameras']))
    lines.append('static const float room_camera_target[ROOM_CAMERA_COUNT][3]={%s};'%', '.join('{%s}'%', '.join('%.8ff'%v for v in c['target']) for c in doc['cameras']))
    lines.append('static const float room_camera_fov[ROOM_CAMERA_COUNT]={%s};'%', '.join('%.8ff'%c['fov'] for c in doc['cameras']))
    (Path(root)/'src/nc_room_layout.h').write_text('\n'.join(lines)+'\n')
