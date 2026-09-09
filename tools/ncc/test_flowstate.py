import copy
import json
from pathlib import Path
import re
import tempfile
import unittest
from ncc import eventflow, ncscript, ps2flow, flowstate

class BoxTests(unittest.TestCase):
    def document(self, target):
        pairs=[(1,'On start','',1),(2,'Play effect' if target=='ps1' else 'Set camera','0',1),
               (3,'On button','CROSS',1),(4,'Go to Flow Box','2',1),
               (5,'On start','',2),(6,'Play effect' if target=='ps1' else 'Set camera','1',2),
               (7,'On button','CROSS',2),(8,'Play effect' if target=='ps1' else 'Set camera','2',2),
               (9,'On exit','',1),(10,'Play effect' if target=='ps1' else 'Set camera','2',1)]
        return dict(version=2,target=target,status='enabled',entry=1,stages=[dict(id=1),dict(id=2)],
                    nodes=[dict(id=i,kind=k,value=v,section_id=s) for i,k,v,s in pairs],
                    edges=[[1,2],[3,4],[5,6],[7,8],[9,10]])

    def test_reject_cross_box_and_missing_destination(self):
        d=self.document('ps2');d['edges'].append([1,6])
        with self.assertRaisesRegex(ValueError,'cross-box'):flowstate.validate(d)
        d=self.document('ps2');d['nodes'][3]['value']='99'
        with self.assertRaisesRegex(ValueError,'destination'):flowstate.validate(d)
        d=self.document('ps2');d['edges'].append([9,4])
        with self.assertRaisesRegex(ValueError,'Exit handlers'):flowstate.validate(d)

    def test_ps1_execution_entry_exit_and_input_not_replayed(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'event-flow.json').write_text(json.dumps(self.document('ps1')))
            source=eventflow.compose(root,'ps1','')
            ncscript.compile_source(source)  # Verify the actual NCScript frontend accepts it.
            names=re.findall(r'^var (\w+)',source,re.M)
            python=re.sub(r'^var ', '', source, flags=re.M)
            python=re.sub(r'^func (.*):$', lambda m:'def '+m[1]+':\n    global '+','.join(names), python, flags=re.M)
            sounds=[];pressed=[False]
            env=dict(play_sound=sounds.append,btn_pressed=lambda _:pressed[0],BTN_CROSS=1)
            exec(python,env)
            env['_update']();self.assertEqual(sounds,[0])
            pressed[0]=True;env['_update']();self.assertEqual(sounds,[0,2]) # exit only
            env['_update']();self.assertEqual(sounds,[0,2,1]) # enter, no reused CROSS
            env['_update']();self.assertEqual(sounds,[0,2,1,2])

    def test_ps2_stage_gates_and_exit(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'src').mkdir()
            (root/'nc.json').write_text('{"event_adapter":"fixed_room_v1"}')
            (root/'event-flow.json').write_text(json.dumps(self.document('ps2')))
            ps2flow.compile_project(root)
            code=(root/'src/nc_events.h').read_text()
            self.assertIn('else if (pending) { active = pending;',code)
            self.assertIn('pressed = 0; zone = -1;',code)
            self.assertIn('active == 2 && !pending',code)
            self.assertIn('if (pending && active == 1)',code)

if __name__=='__main__':unittest.main()
