import copy
import json
from pathlib import Path
import tempfile
import unittest
from PIL import Image
from ncc.vn import compile_content


class VNKitTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / 'src').mkdir()
        self.doc = {'title': 'TEST', 'subtitle': 'PS2', 'story': ['LEGACY'], 'about': ['TEST'],
                    'logo_scale_x': 110.0, 'kit': {'start': 'hello', 'frames_per_character': 2.0,
                    'characters': [], 'items': [{'id': 'key', 'name': 'KEY'}],
                    'scenes': [{'id': 'room', 'color': [20.0, 24.0, 26.0]}],
                    'dialogue': [{'id': 'hello', 'scene': 'room', 'text': 'HELLO', 'give': 'key',
                                  'choices': [{'text': 'LEAVE', 'requires': 'key', 'next': 'end'}]},
                                 {'id': 'end', 'scene': 'room', 'text': 'GOODBYE'}]}}

    def tearDown(self):
        self.temp.cleanup()

    def compile(self):
        (self.root / 'vn.json').write_text(json.dumps(self.doc))
        compile_content(self.root)

    def test_godot_numeric_roundtrip_and_inventory(self):
        self.compile()
        result = (self.root / 'src/vn_kit.h').read_text()
        self.assertIn('{"LEAVE",1,0,-1}', result)
        self.assertIn('#define VN_SPEED 2', result)

    def test_dangling_scene(self):
        self.doc['kit']['dialogue'][0]['scene'] = 'missing'
        with self.assertRaisesRegex(ValueError, 'unknown reference'):
            self.compile()

    def test_unknown_required_item(self):
        self.doc['kit']['dialogue'][0]['choices'][0]['requires'] = 'missing'
        with self.assertRaisesRegex(ValueError, 'choice requires'):
            self.compile()

    def test_duplicate_id(self):
        self.doc['kit']['dialogue'].append(copy.deepcopy(self.doc['kit']['dialogue'][0]))
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            self.compile()

    def test_too_much_text(self):
        self.doc['kit']['dialogue'][0]['text'] = 'WORDS ' * 30
        with self.assertRaisesRegex(ValueError, 'four wrapped lines'):
            self.compile()

    def test_texture_padding_and_alpha(self):
        Image.new('RGBA', (3, 5), (255, 0, 0, 255)).save(self.root / 'portrait.png')
        self.doc['kit']['characters'] = [{'id': 'actor', 'portrait': 'portrait.png'}]
        self.compile()
        result = (self.root / 'src/vn_kit.h').read_text()
        self.assertIn('{vn_pixels_0,4,8,3,5}', result)
        self.assertIn('0x800000ff', result)

    def test_texture_dimension_limit(self):
        Image.new('RGB', (513, 1)).save(self.root / 'large.png')
        self.doc['kit']['scenes'][0]['background'] = 'large.png'
        with self.assertRaisesRegex(ValueError, 'resize'):
            self.compile()

    def test_asset_path_escape(self):
        self.doc['kit']['scenes'][0]['background'] = '../outside.png'
        with self.assertRaisesRegex(ValueError, 'inside the project'):
            self.compile()


if __name__ == '__main__':
    unittest.main()
