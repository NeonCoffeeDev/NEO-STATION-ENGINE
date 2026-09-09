"""Compile bounded trigger volumes into native event predicates."""
from .viewportdata import load_triggers

def predicates(project,target):
    world,ts=load_triggers(project)
    result={}
    for t in ts:
        if world.target!=target:raise ValueError('Trigger console mismatch.')
        subject=t['subject'];index=subject.split(':',1)[-1]
        if target=='ps1':
            if any(type(v) is not int for v in t['min']+t['max']):raise ValueError('PS1 trigger coordinates must be integers.')
            calls=['sprite_x','sprite_y'] if t['space']=='2d' else ['get_x','get_y','get_z']
            coords=[f'{c}({int(index)})' for c in calls];room=f'scene() == {t["room"]}'
        elif world.kind=='fixed_room_v1':coords=['player_x','0.0f','player_z'];room='1'
        elif world.kind=='pad2d_v1':coords=['x','y'];room='1'
        elif world.kind=='lab3d_v1':
            i=list(world.doc['objects']).index(index);coords=[f'nc_object_pos[{i}][{a}]' for a in range(3)];room='1'
        elif world.kind=='vn' and subject.startswith('p:'):
            coords=[f'vn_slots[{int(index)}].x',f'vn_slots[{int(index)}].y'];room=f'nc_vn_scene == {t["room"]}'
        else:raise ValueError('This trigger subject has no runtime position adapter.')
        terms=[room]
        for c,low,high in zip(coords,t['min'],t['max']):
            a,b=(str(low),str(high)) if target=='ps1' else (f'{low:.8f}f',f'{high:.8f}f')
            terms += [f'{c} >= {a}',f'{c} < {b}']
        result[t['id']]=(' and ' if target=='ps1' else ' && ').join(terms)
    return result
