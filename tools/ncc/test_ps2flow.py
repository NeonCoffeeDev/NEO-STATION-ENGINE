import json
from pathlib import Path
import tempfile
import unittest
from ncc.ps2flow import compile_project

class LogicTests(unittest.TestCase):
    def compile(self, actions):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'src').mkdir()
            (root/'nc.json').write_text('{"event_adapter":"fixed_room_v1"}')
            nodes=[dict(id=1,kind='On button',value='CROSS')]
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

if __name__=='__main__':unittest.main()
