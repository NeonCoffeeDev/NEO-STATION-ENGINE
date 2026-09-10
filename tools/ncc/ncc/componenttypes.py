"""Shared authoring vocabulary for GameObjects, visual actions, and NC-CODE."""
COMPONENTS={
 'Transform':dict(icon='XYZ',targets=('ps1','ps2'),fields=('position','rotation','scale'),code=('set_pos(object,x,y,z)','set_rot(object,x,y,z)','move(object,x,y,z)')),
 'Lifecycle':dict(icon='PWR',targets=('ps1','ps2'),fields=('isActive','visible','persistent'),code=('show(object)','hide(object)','goto_scene(scene)')),
 'Identity':dict(icon='TAG',targets=('ps1','ps2'),fields=('name','tag','state'),code=('save_set(slot,value)',)),
 'Sprite2D':dict(icon='IMG',targets=('ps1','ps2'),fields=('image','frame','layer','visible','flip'),code=('sprite_frame(sprite,x,y)','sprite_show(sprite)','sprite_hide(sprite)')),
 'Text2D':dict(icon='TXT',targets=('ps1','ps2'),fields=('text','font','color','align','layer','visible'),code=('draw_text(x,y,text)','set_text(object,text)','show(object)','hide(object)')),
 'Panel2D':dict(icon='PNL',targets=('ps1','ps2'),fields=('size','color','layer','visible'),code=('show(object)','hide(object)')),
 'Button2D':dict(icon='BTN',targets=('ps1','ps2'),fields=('text','action','selected','layer','visible'),code=('button_pressed(object)','set_text(object,text)','show(object)','hide(object)')),
 'Canvas2D':dict(icon='UI',targets=('ps1','ps2'),fields=('size','target_resolution','visible'),code=('show(object)','hide(object)')),
 'Container2D':dict(icon='BOX',targets=('ps1','ps2'),fields=('layout','padding','spacing','layer','visible'),code=('show(object)','hide(object)')),
 'Grid Container':dict(icon='GRID',targets=('ps1','ps2'),fields=('columns','rows','spacing','selection'),code=('inventory_select(slot)','inventory_show()','inventory_hide()')),
 'Texture Rect':dict(icon='TEX',targets=('ps1','ps2'),fields=('image','stretch','tint','layer','visible'),code=('show(object)','hide(object)')),
 'Progress Bar':dict(icon='BAR',targets=('ps1','ps2'),fields=('value','maximum','color','layer','visible'),code=('set_value(object,value)','show(object)','hide(object)')),
 'Mesh3D':dict(icon='MSH',targets=('ps1','ps2'),fields=('mesh','material','visible'),code=('show(object)','hide(object)')),
 'Material':dict(icon='MAT',targets=('ps1','ps2'),fields=('texture','tint','lighting'),code=('show(object)',)),
 'Camera':dict(icon='CAM',targets=('ps1','ps2'),fields=('target','fov','active'),code=('camera_set(x,y,z,pitch,yaw,roll)','camera_move(x,y,z)')),
 'Collision Box':dict(icon='COL',targets=('ps1','ps2'),fields=('center','size','solid'),code=('touching(a,b)','sprite_set_solid(sprite,enabled)')),
 'Trigger Volume':dict(icon='TRG',targets=('ps1','ps2'),fields=('center','size','event'),code=('touching(a,b)',)),
 'Audio Source':dict(icon='SFX',targets=('ps1','ps2'),fields=('sound','volume','loop','radius'),code=('play_sound(sound)',)),
 'NC-Code Script':dict(icon='CODE',targets=('ps2',),fields=('script','enabled'),code=('func on_activate():','    play_sound(0)')),
 'Light':dict(icon='LIT',targets=('ps2',),fields=('color','intensity','direction','range'),code=()),
 'FX Emitter':dict(icon='FX',targets=('ps1','ps2'),fields=('effect','rate','duration','layer'),code=('shake(strength)',)),
 'Attachment Point':dict(icon='PNT',targets=('ps1','ps2'),fields=('position','rotation','tag'),code=()),
 'Custom Variables':dict(icon='VAR',targets=('ps1','ps2'),fields=('name','type','default','exposed'),code=('save_get(slot)','save_set(slot,value)')),
}

# The current compact Canvas subset. Anchors, responsive containers and themes
# intentionally remain a later UI-canvas milestone; these calls already share
# the NC-Code/runtime vocabulary used by visual Events.
UI_NC_CODE=('open_inventory()','load_level(0)','load_level(1)','show_main_menu()')

READY_OBJECTS={
 'Empty GameObject':('Transform','Lifecycle','Identity'),
 '2D Sprite':('Transform','Lifecycle','Identity','Sprite2D'),
 '2D Text':('Transform','Lifecycle','Identity','Text2D'),
 'Menu Button':('Transform','Lifecycle','Identity','Button2D'),
 'UI Panel':('Transform','Lifecycle','Identity','Panel2D'),
 'UI Canvas':('Transform','Lifecycle','Identity','Canvas2D'),
 'UI Container':('Transform','Lifecycle','Identity','Container2D'),
 'Texture Rect':('Transform','Lifecycle','Identity','Texture Rect'),
 'Progress Bar':('Transform','Lifecycle','Identity','Progress Bar'),
 'Inventory Grid':('Transform','Lifecycle','Identity','Panel2D','Grid Container'),
 '3D Mesh':('Transform','Lifecycle','Identity','Mesh3D','Material'),
 'Main Camera':('Transform','Lifecycle','Identity','Camera'),
 'Solid Object':('Transform','Lifecycle','Identity','Collision Box'),
 'Trigger':('Transform','Lifecycle','Identity','Trigger Volume'),
 'Audio Emitter':('Transform','Lifecycle','Identity','Audio Source'),
 'Scripted GameObject':('Transform','Lifecycle','Identity','NC-Code Script'),
 'FX Emitter':('Transform','Lifecycle','Identity','FX Emitter'),
 'PS2 Light':('Transform','Lifecycle','Identity','Light'),
}

def ready_for(target):
    return {name:parts for name,parts in READY_OBJECTS.items()
            if all(target in COMPONENTS[part]['targets'] for part in parts)}
