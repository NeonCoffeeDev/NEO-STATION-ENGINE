import json
from pathlib import Path
import tempfile
import unittest
from ncc.ps2flow import compile_project
from ncc.nccode import create as create_code

class LogicTests(unittest.TestCase):
    def compile(self, actions, event='On button', value='CROSS'):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'src').mkdir()
            (root/'nc.json').write_text('{"event_adapter":"fixed_room_v1"}')
            (root/'src/main.c').write_text('static int nc_move_arrived;\nif(action==3)\n')
            nodes=[dict(id=1,kind=event,value=value)]
            nodes += [dict(id=i+2,kind=kind,value=value) for i,(kind,value) in enumerate(actions)]
            (root/'event-flow.json').write_text(json.dumps(dict(target='ps2',status='enabled',nodes=nodes,edges=[[i,i+1] for i in range(1,len(nodes))])))
            compile_project(root)
            return (root/'src/nc_events.h').read_text()
    def test_counter_condition(self):
        code=self.compile([('Add variable','presses, 1'),('If equal','presses, 3'),('Set camera','2')])
        self.assertLess(code.index('var_presses += 1'),code.index('if(var_presses == 3)'))
        self.assertIn('nc_action(0, 2);',code)
    def test_bounded_repeat(self):
        code=self.compile([('Repeat','3'),('Add variable','tokens, 1')])
        self.assertEqual(code.count('var_tokens += 1'),3)
    def test_reject_invalid_parameters(self):
        for kind,value in [('Repeat','0'),('Repeat','17'),('Set variable','score;evil, 1'),('Add variable','score, 40000')]:
            with self.subTest(kind=kind,value=value), self.assertRaises(ValueError):
                self.compile([(kind,value)])
    def test_expansion_budget(self):
        with self.assertRaisesRegex(ValueError,'2048'):
            self.compile([('Repeat','16')]*4+[('Add variable','score, 1')])
    def test_arrival_is_not_a_boot_event(self):
        code=self.compile([('Interact','0')],event='On arrival',value='')
        self.assertIn('if (!start && nc_move_arrived)',code)
        self.assertIn('nc_action(1, 0);',code)
    def test_cancel_opcode(self):
        self.assertIn('nc_action(3, 0);',self.compile([('Stop movement','0')]))
    def test_visual_event_calls_compiled_nc_code(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'src').mkdir();(root/'scripts').mkdir()
            (root/'nc.json').write_text('{"event_adapter":"vn_v1"}')
            (root/'vn.json').write_text('{"kit":{"scenes":[{}]}}')
            (root/'scripts/menu.nc').write_text('func confirm():\n    play_sound(3)\n')
            nodes=[dict(id=1,kind='On button',value='CROSS'),dict(id=2,kind='Call NC-Code',value='confirm')]
            (root/'event-flow.json').write_text(json.dumps(dict(target='ps2',status='enabled',nodes=nodes,edges=[[1,2]])))
            compile_project(root)
            self.assertIn('nc_code_confirm();',(root/'src/nc_events.h').read_text())
            self.assertIn('nc_sfx_play(3);',(root/'src/nc_code_generated.h').read_text())
    def test_nc_code_rejects_unknown_console_call(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'src').mkdir();path=create_code(root,'bad')
            path.write_text('func run():\n    unlimited_gpu_magic(1)\n')
            with self.assertRaisesRegex(ValueError,'unsupported call'):
                from ncc.nccode import compile_project as compile_code
                compile_code(root)

if __name__=='__main__':unittest.main()
