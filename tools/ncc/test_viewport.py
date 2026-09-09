import copy
import json
from pathlib import Path
import re
import tempfile
import unittest
from ncc.viewportdata import World
from ncc.lablayout import compile_project as compile_lab
from ncc import eventflow,ncscript
from ncc.ps2materials import compile_project as compile_ps2_materials

class ViewportTests(unittest.TestCase):
    def setup_world(self,root):
        (root/'nc.json').write_text('{"target":"ps1"}')
        scene=dict(scenes=[dict(sprites=[dict(name='Ship',x=5,y=5,w=16,h=16,texture='sheet')],instances=[dict(mesh=0,pos=[10,20,30])])],textures=[])
        (root/'scene.json').write_text(json.dumps(scene))
        return World(root)
    def test_2d_3d_positions_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);w=self.setup_world(root)
            w.move(0,'s:0',[25,40]);w.move(0,'m:0',[40,50,60]);w.save()
            fresh=World(root)
            self.assertEqual(fresh.doc['scenes'][0]['sprites'][0]['x'],25)
            self.assertEqual(fresh.doc['scenes'][0]['instances'][0]['pos'],[40,50,60])
            self.assertEqual(fresh.doc['scenes'][0]['sprites'][0]['texture'],'sheet')
    def test_conflict_does_not_partially_save(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);w=self.setup_world(root);w.move(0,'s:0',[25,40])
            before=(root/'scene.json').read_text()
            (root/'triggers.json').write_text('{"external":true}')
            with self.assertRaisesRegex(ValueError,'External'):w.save()
            self.assertEqual((root/'scene.json').read_text(),before)
    def test_invalid_trigger_subject_and_bounds(self):
        with tempfile.TemporaryDirectory() as d:
            w=self.setup_world(Path(d))
            t=dict(id=1,name='Gate',room=0,subject='s:0',space='2d',min=[10,0],max=[30,40])
            w.triggers['triggers']=[t];w.validate()
            t['subject']='s:9'
            with self.assertRaises(ValueError):w.validate()
            t['subject']='s:0';t['max']=[10,40]
            with self.assertRaises(ValueError):w.validate()
    def test_trigger_crossing_fires_once_and_exit(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);w=self.setup_world(root)
            w.triggers['triggers']=[dict(id=1,name='Gate',room=0,subject='s:0',space='2d',min=[10,0],max=[30,40])];w.save()
            nodes=[dict(id=1,kind='On trigger enter',value='1'),dict(id=2,kind='Play effect',value='0'),dict(id=3,kind='On trigger exit',value='1'),dict(id=4,kind='Play effect',value='1')]
            (root/'event-flow.json').write_text(json.dumps(dict(version=1,target='ps1',status='enabled',nodes=nodes,edges=[[1,2],[3,4]])))
            source=eventflow.compose(root,'ps1','');ncscript.compile_source(source)
            names=re.findall(r'^var (\w+)',source,re.M)
            python=re.sub(r'^var ', '',source,flags=re.M)
            python=re.sub(r'^func (.*):$',lambda m:'def '+m[1]+':\n    global '+','.join(names),python,flags=re.M)
            pos=[5,5];sounds=[]
            env=dict(scene=lambda:0,sprite_x=lambda _:pos[0],sprite_y=lambda _:pos[1],play_sound=sounds.append)
            exec(python,env);env['_ready']();env['_update']();self.assertEqual(sounds,[])
            pos[0]=10;env['_update']();env['_update']();self.assertEqual(sounds,[0])
            pos[0]=30;env['_update']();env['_update']();self.assertEqual(sounds,[0,1])
    def test_console_separation(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);self.setup_world(root)
            (root/'triggers.json').write_text('{"version":1,"target":"ps2","triggers":[]}')
            with self.assertRaisesRegex(ValueError,'target'):World(root)

    def test_ps2_3d_transform_and_camera_codegen(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'src').mkdir()
            (root/'nc.json').write_text('{"target":"ps2","event_adapter":"lab3d_v1"}')
            layout=dict(version=1,target='ps2',objects={'cube':[1,2,3]},
                rotations={'cube':[10,20,30]},scales={'cube':[1,2,3]},
                camera={'pos':[6,4,-8],'target':[0,0,0],'fov':55},
                collisions=[dict(id=1,name='Body',object='cube',center=[0,0,0],size=[2,2,2])],
                attachments=[dict(id=2,name='Top',object='cube',pos=[0,1,0])])
            (root/'room-layout.json').write_text(json.dumps(layout))
            compile_lab(root);code=(root/'src/nc_objects.h').read_text()
            self.assertIn('nc_object_rot',code)
            self.assertIn('nc_object_scale',code)
            self.assertIn('nc_object_material[NC_OBJECT_COUNT] = {-1}',code)
            self.assertIn('NC_GAME_CAMERA_FOV 55.00000000f',code)

    def test_ps2_3d_rejects_component_from_other_object(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            (root/'nc.json').write_text('{"target":"ps2","event_adapter":"lab3d_v1"}')
            source=Path('tools/ncc/ncc/templates/ps2_3d/room-layout.json')
            (root/'room-layout.json').write_text(source.read_text())
            world=World(root);world.doc['collisions'][0]['object']='missing'
            with self.assertRaisesRegex(ValueError,'missing object'):world.validate()

    def test_projects_do_not_share_workspace_state(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            first=self.setup_world(Path(a));second=self.setup_world(Path(b))
            first.move(0,'s:0',[99,77])
            self.assertEqual(second.records(0)[0]['pos'],[5,5])
            self.assertEqual(first.records(0)[0]['pos'],[99,77])

    def test_boot_screen_objects_are_real_editable_project_data(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);world=self.setup_world(root)
            world.screens['screens']['splash']={'objects':[dict(name='Logo',type='image',rect=[10,20,80,40],text='',texture='')]}
            world.active_screen='splash'
            self.assertEqual(world.records(0)[0]['name'],'Logo')
            world.move(0,'u:0',[30,40]);world.save()
            fresh=World(root);fresh.active_screen='splash'
            self.assertEqual(fresh.records(0)[0]['pos'],[30,40])

    def test_ps2_sprite_screen_roundtrip(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'textures').mkdir();Image.new('RGBA',(16,16),(255,0,255,255)).save(root/'textures/logo.png')
            (root/'nc.json').write_text('{"target":"ps2","event_adapter":"screen2d_v1"}')
            screen={'version':1,'target':'ps2','screens':{'logo':{'name':'Logo Screen','objects':[{'name':'Logo','type':'sprite2d','role':'brand_logo','rect':[10,20,64,64],'layer':3,'texture':'textures/logo.png'}]}}}
            (root/'screens.json').write_text(json.dumps(screen))
            world=World(root);self.assertEqual(world.scenes()[0]['name'],'Logo Screen')
            row=world.records(0)[0];self.assertEqual((row['image'],row['layer']),('textures/logo.png',3))
            world.move(0,'u:0',[30,40]);world.save();fresh=World(root)
            self.assertEqual(fresh.records(0)[0]['pos'],[30,40])

    def test_shared_gameobject_properties_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);world=self.setup_world(root)
            world.set_common('s:0',{'isActive':False,'tag':'player','state':'hurt','persistent':True})
            world.save();row=World(root).records(0)[0]
            self.assertFalse(row['isActive']);self.assertEqual(row['tag'],'player')
            self.assertEqual(row['state'],'hurt');self.assertTrue(row['persistent'])

    def test_ps2_materials_compile_to_aligned_native_data(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'src').mkdir();(root/'textures').mkdir()
            Image.new('RGBA',(3,5),(255,64,16,255)).save(root/'textures/test.png')
            (root/'room-layout.json').write_text(json.dumps({'materials':{'cube':{'texture':'textures/test.png'}}}))
            count,size=compile_ps2_materials(root)
            self.assertEqual((count,size),(1,4*8*4))
            self.assertIn('NC_MATERIAL_o_cube 0',(root/'src/nc_materials.h').read_text())

if __name__=='__main__':unittest.main()
