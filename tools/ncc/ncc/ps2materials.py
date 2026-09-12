"""Compile project PNG materials into bounded GS_PSM_32 native data."""
import json
import math
import re
from pathlib import Path

MAX_TEXTURES=8
MAX_BYTES=1024*1024

def _pow2(value):
    result=1
    while result<value:result*=2
    return result

def _symbol(value):return re.sub(r'[^a-zA-Z0-9_]','_',value).lower()

def compile_project(root):
    from PIL import Image
    root=Path(root);layout_path=root/'room-layout.json';world_path=root/'world3d.json'
    layout=json.loads(layout_path.read_text(encoding='utf-8')) if layout_path.exists() else {}
    world=json.loads(world_path.read_text(encoding='utf-8')) if world_path.exists() else {}
    assignments={}
    for name,material in layout.get('materials',{}).items():
        if material.get('texture'):assignments['o:'+name]=material['texture']
    for name,obj in world.get('objects',{}).items():
        if obj.get('material'):assignments['w:'+name]=obj['material']
    paths=[]
    for path in assignments.values():
        if path not in paths:paths.append(path)
    if len(paths)>MAX_TEXTURES:raise ValueError('PS2 material budget is %d unique textures.'%MAX_TEXTURES)
    arrays=[];total=0
    for index,relative in enumerate(paths):
        source=root/relative
        with Image.open(source) as opened:image=opened.convert('RGBA')
        if image.width>512 or image.height>512:raise ValueError('%s exceeds the 512x512 PS2 material limit.'%relative)
        width,height=_pow2(image.width),_pow2(image.height)
        canvas=Image.new('RGBA',(width,height),(0,0,0,0));canvas.paste(image,(0,0))
        words=[]
        pixels=canvas.get_flattened_data() if hasattr(canvas,'get_flattened_data') else canvas.getdata()
        for red,green,blue,alpha in pixels:
            ps2_alpha=0x80 if alpha>=128 else 0
            words.append((ps2_alpha<<24)|(blue<<16)|(green<<8)|red)
        total+=len(words)*4
        if total>MAX_BYTES:raise ValueError('PS2 material pixels exceed the 1 MiB starter VRAM budget.')
        arrays.append((index,relative,width,height,image.width,image.height,words))
    header=['/* Generated from PS2 project materials. */','#pragma once','#include <tamtypes.h>',
            '#define NC_MATERIAL_COUNT %d'%len(arrays),'typedef struct { int width,height,used_width,used_height; u32 *pixels; } nc_material_t;',
            'extern nc_material_t nc_materials[%d];'%max(1,len(arrays))]
    for key,path in assignments.items():header.append('#define NC_MATERIAL_%s %d'%(_symbol(key),paths.index(path)))
    source=['/* Generated GS_PSM_32 pixels; alpha 0x80 is opaque on PS2. */','#include "nc_materials.h"']
    for index,relative,width,height,used_w,used_h,words in arrays:
        source.append('static u32 nc_tex_%d[%d] __attribute__((aligned(64)))={'%(index,len(words)))
        for start in range(0,len(words),8):source.append('  '+','.join('0x%08Xu'%v for v in words[start:start+8])+',')
        source.append('};')
    source.append('nc_material_t nc_materials[%d]={'%max(1,len(arrays)))
    if arrays:
        for index,relative,width,height,used_w,used_h,words in arrays:source.append('  {%d,%d,%d,%d,nc_tex_%d},'%(width,height,used_w,used_h,index))
    else:source.append('  {0,0,0,0,0},')
    source.append('};')
    objects=list(world.get('objects',{}).items())
    camera=world.get('camera',{'pos':[6,4.5,-8],'target':[0,0,0],'fov':60})
    def cfloat(value):
        text=('%g'%value)
        return (text+'.0' if '.' not in text and 'e' not in text.lower() else text)+'f'
    header += ['#define NC_WORLD_OBJECT_COUNT %d'%len(objects),
               'extern float nc_world_pos[%d][3];'%max(1,len(objects)),
               'extern float nc_world_rot[%d][3];'%max(1,len(objects)),
               'extern float nc_world_scale[%d][3];'%max(1,len(objects)),
               'extern int nc_world_material[%d];'%max(1,len(objects)),
               '#define NC_WORLD_CAMERA_POS {%s}'%(','.join(cfloat(v) for v in camera['pos'])),
               '#define NC_WORLD_CAMERA_TARGET {%s}'%(','.join(cfloat(v) for v in camera['target'])),
               '#define NC_WORLD_CAMERA_FOV %s'%cfloat(camera.get('fov',60))]
    # Lights are authored by the direction they shine; shading wants the
    # direction *towards* the light, so the vector is negated and normalised
    # here rather than every frame on a 294 MHz CPU with no divide to spare.
    lights=[]
    ambient=0.0
    for light in world.get('lights',{}).values():
        direction=[float(v) for v in light.get('direction',[0,-1,0])]
        length=math.sqrt(sum(v*v for v in direction)) or 1.0
        lights.append(([-v/length for v in direction],float(light.get('intensity',1.0))))
        ambient=max(ambient,float(light.get('ambient',0.0)))
    if not lights:
        # An unlit world still has to be visible, or removing the last light
        # reads as a renderer fault rather than as an authoring choice.
        ambient=max(ambient,1.0)
    header += ['#define NC_WORLD_LIGHT_COUNT %d'%len(lights),
               '#define NC_WORLD_AMBIENT %s'%cfloat(round(ambient,4)),
               'extern float nc_world_light_dir[%d][3];'%max(1,len(lights)),
               'extern float nc_world_light_power[%d];'%max(1,len(lights))]
    source += ['float nc_world_light_dir[%d][3]={%s};'%(max(1,len(lights)),
               ','.join('{%s}'%','.join(cfloat(round(v,6)) for v in d) for d,_ in lights) or '{0,0,0}'),
               'float nc_world_light_power[%d]={%s};'%(max(1,len(lights)),
               ','.join(cfloat(round(power,4)) for _,power in lights) or '0.0f')]
    def triples(field,default):return ','.join('{%s}'%','.join(cfloat(v) for v in obj.get(field,default)) for _,obj in objects) or '{0,0,0}'
    source += ['float nc_world_pos[%d][3]={%s};'%(max(1,len(objects)),triples('position',[0,0,0])),
               'float nc_world_rot[%d][3]={%s};'%(max(1,len(objects)),triples('rotation',[0,0,0])),
               'float nc_world_scale[%d][3]={%s};'%(max(1,len(objects)),triples('scale',[1,1,1])),
               'int nc_world_material[%d]={%s};'%(max(1,len(objects)),','.join(str(paths.index(obj['material'])) if obj.get('material') in paths else '-1' for _,obj in objects) or '-1')]
    out=root/'src';out.mkdir(exist_ok=True)
    (out/'nc_materials.h').write_text('\n'.join(header)+'\n',encoding='utf-8')
    (out/'nc_materials.c').write_text('\n'.join(source)+'\n',encoding='utf-8')
    print('  PS2 materials: %d texture(s), %d/1048576 bytes GS pixels'%(len(arrays),total))
    return len(arrays),total
