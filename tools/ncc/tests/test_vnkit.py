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

    # ---- portrait slots and the cast ---------------------------------

    def _cast_setup(self):
        kit = self.doc['kit']
        kit['characters'] = [{'id': 'a', 'name': 'A'}, {'id': 'b', 'name': 'B'}]
        kit['layout'] = {'portraits': [{'name': 'left', 'rect': [32, 24, 128, 224]},
                                       {'name': 'right', 'rect': [400, 24, 128, 224]}]}
        return kit

    def test_slots_default_to_the_old_single_portrait(self):
        """Content written before slots existed still compiles, unchanged."""
        self.doc['kit']['characters'] = [{'id': 'a', 'name': 'A'}]
        self.doc['kit']['dialogue'][0]['speaker'] = 'a'
        self.compile()
        result = (self.root / 'src/vn_kit.h').read_text()
        self.assertIn('#define VN_SLOT_COUNT 1', result)
        # The speaker is placed in slot 0, which is what the old runtime drew.
        self.assertIn('1,{{0,0},{-1,-1},{-1,-1},{-1,-1}}', result)

    def test_cast_is_sorted_by_slot_so_order_is_layer_order(self):
        kit = self._cast_setup()
        # Deliberately the wrong way round: the compiler must sort these, or the
        # list order in the editor would not match what the console draws.
        kit['dialogue'][0]['cast'] = [{'slot': 'right', 'character': 'b'},
                                      {'slot': 'left', 'character': 'a'}]
        self.compile()
        result = (self.root / 'src/vn_kit.h').read_text()
        self.assertIn('#define VN_SLOT_COUNT 2', result)
        self.assertIn('vn_slots[] = {{32,24,128,224},{400,24,128,224}}', result)
        self.assertIn('2,{{0,0},{1,1},{-1,-1},{-1,-1}}', result)

    def test_two_characters_cannot_share_a_slot(self):
        kit = self._cast_setup()
        kit['dialogue'][0]['cast'] = [{'slot': 'left', 'character': 'a'},
                                      {'slot': 'left', 'character': 'b'}]
        with self.assertRaisesRegex(ValueError, 'two characters in slot'):
            self.compile()

    def test_unknown_slot_is_reported(self):
        kit = self._cast_setup()
        kit['dialogue'][0]['cast'] = [{'slot': 'middle', 'character': 'a'}]
        with self.assertRaisesRegex(ValueError, 'unknown portrait slot'):
            self.compile()

    def test_slot_rectangle_must_fit_the_screen(self):
        kit = self._cast_setup()
        kit['layout']['portraits'][0]['rect'] = [600, 24, 128, 224]
        with self.assertRaisesRegex(ValueError, 'must fit'):
            self.compile()

    def test_duplicate_slot_names_are_rejected(self):
        kit = self._cast_setup()
        kit['layout']['portraits'][1]['name'] = 'left'
        with self.assertRaisesRegex(ValueError, 'duplicate name'):
            self.compile()

    def test_asset_path_escape(self):
        self.doc['kit']['scenes'][0]['background'] = '../outside.png'
        with self.assertRaisesRegex(ValueError, 'inside the project'):
            self.compile()


if __name__ == '__main__':
    unittest.main()
