"""Compile project PNG materials into bounded GS_PSM_32 native data."""
import json
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
    out=root/'src';out.mkdir(exist_ok=True)
    (out/'nc_materials.h').write_text('\n'.join(header)+'\n',encoding='utf-8')
    (out/'nc_materials.c').write_text('\n'.join(source)+'\n',encoding='utf-8')
    print('  PS2 materials: %d texture(s), %d/1048576 bytes GS pixels'%(len(arrays),total))
    return len(arrays),total
