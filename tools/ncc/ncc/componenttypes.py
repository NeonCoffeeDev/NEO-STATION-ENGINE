"""Shared authoring vocabulary for GameObjects, visual actions, and NC-CODE."""
COMPONENTS={
 'Transform':dict(icon='XYZ',targets=('ps1','ps2'),fields=('position','rotation','scale'),code=('set_pos(object,x,y,z)','set_rot(object,x,y,z)','move(object,x,y,z)')),
 'Sprite2D':dict(icon='IMG',targets=('ps1','ps2'),fields=('image','frame','layer','visible','flip'),code=('sprite_frame(sprite,x,y)','sprite_show(sprite)','sprite_hide(sprite)')),
 'Mesh3D':dict(icon='MSH',targets=('ps1','ps2'),fields=('mesh','material','visible'),code=('show(object)','hide(object)')),
 'Material':dict(icon='MAT',targets=('ps1','ps2'),fields=('texture','tint','lighting'),code=('show(object)',)),
 'Camera':dict(icon='CAM',targets=('ps1','ps2'),fields=('target','fov','active'),code=('camera_set(x,y,z,pitch,yaw,roll)','camera_move(x,y,z)')),
 'Collision Box':dict(icon='COL',targets=('ps1','ps2'),fields=('center','size','solid'),code=('touching(a,b)','sprite_set_solid(sprite,enabled)')),
 'Trigger Volume':dict(icon='TRG',targets=('ps1','ps2'),fields=('center','size','event'),code=('touching(a,b)',)),
 'Audio Source':dict(icon='SFX',targets=('ps1','ps2'),fields=('sound','volume','loop','radius'),code=('play_sound(sound)',)),
 'Light':dict(icon='LIT',targets=('ps2',),fields=('color','intensity','direction','range'),code=()),
 'FX Emitter':dict(icon='FX',targets=('ps1','ps2'),fields=('effect','rate','duration','layer'),code=('shake(strength)',)),
 'Attachment Point':dict(icon='PNT',targets=('ps1','ps2'),fields=('position','rotation','tag'),code=()),
 'Custom Variables':dict(icon='VAR',targets=('ps1','ps2'),fields=('name','type','default','exposed'),code=('save_get(slot)','save_set(slot,value)')),
}

READY_OBJECTS={
 'Empty GameObject':('Transform',),
 '2D Sprite':('Transform','Sprite2D'),
 '3D Mesh':('Transform','Mesh3D','Material'),
 'Main Camera':('Transform','Camera'),
 'Solid Object':('Transform','Collision Box'),
 'Trigger':('Transform','Trigger Volume'),
 'Audio Emitter':('Transform','Audio Source'),
 'FX Emitter':('Transform','FX Emitter'),
 'PS2 Light':('Transform','Light'),
}

def ready_for(target):
    return {name:parts for name,parts in READY_OBJECTS.items()
            if all(target in COMPONENTS[part]['targets'] for part in parts)}
