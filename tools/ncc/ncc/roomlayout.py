"""Authoring data for the PS2 fixed-room prototype, shared with Studio."""
import json
import math
from pathlib import Path

DEFAULT = {'version':1,'target':'ps2','objects':{
    'player':[-2,0], 'key':[-2,1.5], 'door':[2,0]},
    'camera_yaw':[0.45,-0.65,0.0]}

def validate(doc):
    if doc.get('target')!='ps2' or doc.get('version')!=1:raise ValueError('Unsupported room layout target/version.')
    if set(doc['objects'])!=set(DEFAULT['objects']):raise ValueError('This prototype supports player, key and door only.')
    for name,xy in doc['objects'].items():
        if len(xy)!=2 or any(type(v) not in (int,float) or not math.isfinite(v) for v in xy):raise ValueError('Invalid position: '+name)
        maxx,maxz=(2,1.2) if name=='door' else (3,2)
        if not (-maxx<=xy[0]<=maxx and -maxz<=xy[1]<=maxz):raise ValueError('Position outside editable room: '+name)
    if len(doc['camera_yaw'])!=3 or any(type(v) not in (int,float) or not math.isfinite(v) or abs(v)>3.1416 for v in doc['camera_yaw']):raise ValueError('Three camera angles in radians (-pi..pi) are required.')
    return doc

def load(root):
    p=Path(root)/'room-layout.json'
    return validate(json.loads(p.read_text()) if p.exists() else json.loads(json.dumps(DEFAULT)))

def compile_project(root):
    doc=load(root);lines=['/* Generated from room-layout.json. */']
    for name,xy in doc['objects'].items():
        for axis,value in zip(('X','Z'),xy):lines.append('#define ROOM_%s_%s %.8ff'%(name.upper(),axis,value))
    lines.append('#define ROOM_CAMERA_YAW {%s}'%', '.join('%.8ff'%v for v in doc['camera_yaw']))
    (Path(root)/'src/nc_room_layout.h').write_text('\n'.join(lines)+'\n')
