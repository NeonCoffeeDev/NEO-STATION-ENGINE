"""Does the console's C agree with the editor's Python about what the camera sees?

The viewport and the hardware were horizontal mirrors of each other for a long
time, and nobody caught it by looking, because a mirrored render is still a
perfectly plausible picture. Writing the formula carefully in two places is
what caused that, so checking it carefully in two places would not fix it.

This reads the projection straight out of nc_world3d.h -- the file the console
actually compiles -- turns the C expressions into Python mechanically, and
evaluates them against ps2camera, which is what NC Studio draws with. There is
no step where a human retypes the maths, so there is no step where a human can
make the two agree on paper while they disagree in the build.

If someone edits either side, this fails.
"""

import math
import re
import unittest
from pathlib import Path

from ncc import ps2camera

RUNTIME = (Path(__file__).resolve().parents[1]
           / 'ncc' / 'templates' / 'ps2_hybrid' / 'src' / 'nc_world3d.h')

# The C spellings of the maths library, and the constants the runtime pulls in
# from elsewhere in the build.
C_TO_PYTHON = {'cosf': 'math.cos', 'sinf': 'math.sin', 'tanf': 'math.tan',
               'atan2f': 'math.atan2', 'sqrtf': 'math.sqrt'}


def c_expression(text, name):
    """The initialiser for `name` in a C declarator list, as Python.

    Scans for `name=` and takes everything up to the comma or semicolon that
    ends that initialiser, ignoring commas inside brackets so a call like
    atan2f(dy, sqrtf(...)) survives intact.
    """
    match = re.search(r'(?<![A-Za-z0-9_])%s\s*=(?!=)' % re.escape(name), text)
    if not match:
        raise AssertionError('%s is not assigned in the runtime any more' % name)
    depth = 0
    start = match.end()
    for index in range(start, len(text)):
        char = text[index]
        if char in '([':
            depth += 1
        elif char in ')]':
            if depth == 0:
                break
            depth -= 1
        elif char in ',;' and depth == 0:
            break
    expression = text[start:index]
    for c_name, python_name in C_TO_PYTHON.items():
        expression = re.sub(r'(?<![A-Za-z0-9_])%s\(' % c_name,
                            python_name + '(', expression)
    # C float suffixes: .5f, 0.3f, 2048. Python has no such spelling.
    expression = re.sub(r'(\d)[fF](?![A-Za-z0-9_])', r'\1', expression)
    expression = expression.replace('(float)', '')
    return expression.strip()


class RuntimeProjection:
    """nc_world_draw's projection, evaluated as the console would compute it."""

    def __init__(self, source=None):
        text = (source or RUNTIME).read_text(encoding='utf-8')
        self.aspect = float(re.search(
            r'#define\s+NC_PIXEL_ASPECT\s+([0-9.]+)f?', text).group(1))
        body = text[text.index('nc_world_draw'):]
        self.steps = [(name, c_expression(body, name)) for name in
                      ('yaw', 'pitch', 'rx', 'rz', 'ry', 'depth', 'focal')]
        self.px = c_expression(body, 'px[i]')
        self.py = c_expression(body, 'py[i]')

    def __call__(self, pos, target, fov, point, screen_h=448):
        scope = {'math': math, 'SCREEN_H': float(screen_h),
                 # The runtime took its field of view from a compiled constant
                 # and now takes it from a runtime camera; accept either name.
                 'NC_WORLD_CAMERA_FOV': float(fov), 'nc_cam_fov': float(fov),
                 'NC_PIXEL_ASPECT': self.aspect,
                 'dx': target[0] - pos[0], 'dy': target[1] - pos[1],
                 'dz': target[2] - pos[2],
                 'vx': point[0] - pos[0], 'vy': point[1] - pos[1],
                 'vz': point[2] - pos[2]}
        for name, expression in self.steps:
            scope[name] = eval(expression, {'__builtins__': {}}, scope)
        if scope['depth'] < 0.3:
            return None
        return (eval(self.px, {'__builtins__': {}}, scope),
                eval(self.py, {'__builtins__': {}}, scope),
                scope['depth'])


class CameraTests(unittest.TestCase):
    def setUp(self):
        self.runtime = RuntimeProjection()

    def test_the_runtime_is_still_shaped_the_way_this_reads_it(self):
        """A rewrite that removed these names would otherwise pass silently."""
        self.assertAlmostEqual(self.runtime.aspect, ps2camera.PIXEL_ASPECT, places=5)
        self.assertIn('math.atan2', dict(self.runtime.steps)['yaw'])
        self.assertIn('NC_PIXEL_ASPECT', self.runtime.px)

    def test_console_and_editor_place_points_identically(self):
        """The whole point. Both are expressed as a fraction of the picture.

        The console works in 640x448 buffer pixels and the editor in a 4:3
        rectangle of arbitrary size, so neither set of numbers means anything
        next to the other until both are divided by the picture they land in.
        """
        worst = 0.0
        compared = 0
        for pos, target, fov in self.cameras():
            rect = ps2camera.letterbox(900, 500)
            for point in self.points():
                on_console = self.runtime(pos, target, fov, point)
                in_editor = ps2camera.project(pos, target, fov, point, rect)
                self.assertEqual(on_console is None, in_editor is None,
                                 'disagreed about whether %s is visible' % (point,))
                if on_console is None:
                    continue
                compared += 1
                console = (on_console[0] / 640.0 + 0.5, on_console[1] / 448.0 + 0.5)
                editor = ((in_editor[0] - rect[0]) / rect[2],
                          (in_editor[1] - rect[1]) / rect[3])
                worst = max(worst, abs(console[0] - editor[0]),
                            abs(console[1] - editor[1]))
        self.assertGreater(compared, 200, 'too few visible points to mean anything')
        self.assertLess(worst, 1e-6,
                        'viewport and console disagree by %.2e of the picture' % worst)

    def test_x_is_to_the_right_on_both(self):
        """The mirror bug, named directly, so it cannot come back quietly."""
        pos, target = [0.0, 0.0, -5.0], [0.0, 0.0, 0.0]
        console = self.runtime(pos, target, 60, [1.0, 0.0, 0.0])
        editor = ps2camera.project(pos, target, 60, [1.0, 0.0, 0.0], (0, 0, 640, 448))
        self.assertGreater(console[0], 0, 'console puts +X on the left')
        self.assertGreater(editor[0], 320, 'editor puts +X on the left')

    def test_up_is_up_on_both(self):
        pos, target = [0.0, 0.0, -5.0], [0.0, 0.0, 0.0]
        console = self.runtime(pos, target, 60, [0.0, 1.0, 0.0])
        editor = ps2camera.project(pos, target, 60, [0.0, 1.0, 0.0], (0, 0, 640, 448))
        # Screen Y grows downwards in both, so a point above the centre is negative
        # on the console and above the halfway line in the editor.
        self.assertLess(console[1], 0, 'console puts +Y down')
        self.assertLess(editor[1], 224, 'editor puts +Y down')

    def test_a_cube_is_a_cube_on_a_four_by_three_television(self):
        """The non-square pixel correction, checked by its purpose.

        A square facing the camera has to reach the screen square. In buffer
        pixels it is wider than it is tall by exactly the amount the television
        squeezes back out.
        """
        pos, target = [0.0, 0.0, -5.0], [0.0, 0.0, 0.0]
        corners = [self.runtime(pos, target, 60, p) for p in
                   ([-1.0, 1.0, 0.0], [1.0, 1.0, 0.0], [1.0, -1.0, 0.0])]
        width = corners[1][0] - corners[0][0]
        height = corners[2][1] - corners[1][1]
        stretch = width / height
        self.assertAlmostEqual(stretch, 640.0 / 448.0 / (4.0 / 3.0), places=4)
        # And on the screen, after the squeeze, it is square again.
        self.assertAlmostEqual((width / 640.0) * (4.0 / 3.0) / (height / 448.0),
                               1.0, places=4)

    @staticmethod
    def cameras():
        return [([-9.25, 12.75, -14.75], [-0.5, 0.0, 0.0], 60),
                ([0.0, 0.0, -5.0], [0.0, 0.0, 0.0], 60),
                ([6.0, 4.5, -8.0], [0.0, 0.0, 0.0], 55),
                ([0.0, 9.0, 0.001], [0.0, 0.0, 0.0], 70),      # near straight down
                ([-3.0, 1.0, 4.0], [2.0, 2.0, -1.0], 35),
                ([12.0, -3.0, 2.0], [0.0, 0.0, 0.0], 90)]

    @staticmethod
    def points():
        span = (-6.0, -1.5, 0.0, 1.0, 3.5)
        return [[x, y, z] for x in span for y in span for z in span]


if __name__ == '__main__':
    unittest.main()


class LightingTests(unittest.TestCase):
    """Does the preview light a face the way the build told the console to?

    ps2materials compiles world3d.json into nc_materials.c, and ps2preview
    reads world3d.json directly. Two readings of one file that are supposed to
    produce the same numbers is exactly the arrangement that silently drifts,
    so the compiled output is parsed back and compared.
    """

    WORLD = {'lights': {
        'Key': {'direction': [0.4, -1.0, 0.25], 'intensity': 0.7, 'ambient': 0.42},
        'Fill': {'direction': [-1.0, -0.2, 0.0], 'intensity': 0.3, 'ambient': 0.1}}}

    def compiled(self, world):
        """Run the real material compiler and read its arrays back."""
        import json
        import tempfile
        from pathlib import Path
        from ncc.ps2materials import compile_project
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'world3d.json').write_text(json.dumps(world), encoding='utf-8')
            compile_project(str(root))
            source = (root / 'src' / 'nc_materials.c').read_text(encoding='utf-8')
            header = (root / 'src' / 'nc_materials.h').read_text(encoding='utf-8')
        directions = [[float(v) for v in row.split(',')] for row in
                      re.findall(r'\{([-0-9.f,]+)\}',
                                 re.search(r'nc_world_light_dir\[\d+\]\[3\]=\{(.*?)\};',
                                           source).group(1).replace('f', ''))]
        powers = [float(v) for v in
                  re.search(r'nc_world_light_power\[\d+\]=\{(.*?)\};',
                            source).group(1).replace('f', '').split(',') if v]
        ambient = float(re.search(r'#define NC_WORLD_AMBIENT ([0-9.]+)f?',
                                  header).group(1))
        return directions, powers, ambient

    def test_preview_reads_the_lights_the_compiler_wrote(self):
        from ncc import ps2preview
        directions, powers, ambient = self.compiled(self.WORLD)
        lights, preview_ambient = ps2preview.lights_of(self.WORLD)
        self.assertAlmostEqual(ambient, preview_ambient, places=4)
        self.assertEqual(len(directions), len(lights))
        for (compiled_dir, compiled_power), (preview_dir, preview_power) in zip(
                zip(directions, powers), lights):
            self.assertAlmostEqual(compiled_power, preview_power, places=4)
            for a, b in zip(compiled_dir, preview_dir):
                self.assertAlmostEqual(a, b, places=5)

    def test_a_light_shining_down_lights_the_top_face(self):
        """The direction is negated on the way in. Getting that backwards would
        light the underside of everything and look merely 'moody'."""
        from ncc import ps2preview
        world = {'lights': {'Sun': {'direction': [0, -1, 0],
                                    'intensity': 1.0, 'ambient': 0.0}}}
        lights, ambient = ps2preview.lights_of(world)
        shades = ps2preview.face_shades([0, 0, 0], lights, ambient)
        top = shades[FACE_UP]
        bottom = shades[FACE_DOWN]
        self.assertAlmostEqual(top, 1.0, places=4)
        self.assertAlmostEqual(bottom, 0.0, places=4)

    def test_no_lights_leaves_the_world_visible(self):
        """Removing the last light should read as an authoring choice, not as
        a renderer that broke."""
        from ncc import ps2preview
        lights, ambient = ps2preview.lights_of({'lights': {}})
        self.assertEqual(lights, [])
        self.assertEqual(ambient, 1.0)
        self.assertEqual(ps2preview.face_shades([0, 0, 0], lights, ambient),
                         [1.0] * 6)


# Index of each face in the runtime's table, named so the tests above read.
FACE_UP = 3
FACE_DOWN = 2
