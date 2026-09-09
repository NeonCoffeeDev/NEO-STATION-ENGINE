"""Compile editable 3D Lab object placements into bounded static storage."""
from pathlib import Path
from .viewportdata import World

def compile_project(root):
    world=World(root);world.validate()
    names=list(world.doc['objects'])
    rows=[world.doc['objects'][name] for name in names]
    rotations=[world.doc['rotations'][name] for name in names]
    scales=[world.doc['scales'][name] for name in names]
    paths=[]
    for material in world.doc.get('materials',{}).values():
        path=material.get('texture')
        if path and path not in paths:paths.append(path)
    material_indices=[paths.index(world.doc['materials'][name]['texture']) if name in world.doc.get('materials',{}) else -1 for name in names]
    text='/* Generated from room-layout.json; positions in PS2 world units. */\n'
    text+='#define NC_OBJECT_COUNT %d\n'%len(rows)
    values=','.join('{'+','.join('%.8ff'%v for v in pos)+'}' for pos in rows)
    text+='static float nc_object_pos[NC_OBJECT_COUNT][3] = {'+values+'};\n'
    text+='static const float nc_object_initial[NC_OBJECT_COUNT][3] = {'+values+'};\n'
    text+='static const float nc_object_rot[NC_OBJECT_COUNT][3] = {'+','.join('{'+','.join('%.8ff'%v for v in row)+'}' for row in rotations)+'};\n'
    text+='static const float nc_object_scale[NC_OBJECT_COUNT][3] = {'+','.join('{'+','.join('%.8ff'%v for v in row)+'}' for row in scales)+'};\n'
    text+='static const int nc_object_material[NC_OBJECT_COUNT] = {'+','.join(map(str,material_indices))+'};\n'
    camera=world.doc['camera']
    text+='#define NC_GAME_CAMERA_POS {%s}\n'%','.join('%.8ff'%v for v in camera['pos'])
    text+='#define NC_GAME_CAMERA_TARGET {%s}\n'%','.join('%.8ff'%v for v in camera['target'])
    text+='#define NC_GAME_CAMERA_FOV %.8ff\n'%camera['fov']
    (Path(root)/'src/nc_objects.h').write_text(text,encoding='utf-8')
