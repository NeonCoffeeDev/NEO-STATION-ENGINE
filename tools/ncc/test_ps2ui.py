import json
from pathlib import Path
import tempfile
import unittest
from ncc.ps2ui import compile_project


def project(tmp_path, buttons):
    (tmp_path/'src').mkdir()
    (tmp_path/'screens.json').write_text(json.dumps({
        'target':'ps2','screens':{'main_menu':{'objects':buttons}}}))
    return tmp_path


def button(text, action, layer=0):
    return {'name':text,'type':'button','text':text,'action':action,
            'layer':layer,'visible':True,'isActive':True}


class Ps2UiTests(unittest.TestCase):
    def test_menu_is_generated_in_authored_layer_order(self):
        with tempfile.TemporaryDirectory() as directory:
            root=project(Path(directory),[button('VN','load:vn',2),button('3D LAB','load:world3d',1)])
            rows=compile_project(root)
            self.assertEqual(rows,[('3D LAB',1),('VN',2)])
            text=(root/'src/nc_ui_generated.h').read_text()
            self.assertIn('NC_UI_MENU_COUNT 2',text)
            self.assertIn('"3D LAB"',text)

    def test_unknown_action_is_refused_before_console_build(self):
        with tempfile.TemporaryDirectory() as directory:
            root=project(Path(directory),[button('BROKEN','load:missing')])
            with self.assertRaisesRegex(ValueError,'needs an action'):
                compile_project(root)

if __name__=='__main__':unittest.main()
