"""Render what the console will draw, without a console.

Testing a change here costs a build, a USB stick, a walk to the television and
a boot. That round trip is long enough that it stops you trying things, and it
is the reason a mirrored camera survived as long as it did -- nobody looks hard
at a picture they had to work that hard to see.

So this draws the frame on the desk instead. Not an approximation of it: the
same projection ps2camera describes and test_ps2camera proves the runtime C
evaluates to, the same face ordering, the same lighting, the same choice
between perspective-correct and affine texture mapping the runtime offers,
and the same 5-bits-a-channel quantisation a 16-bit frame buffer ends at.

Where this and the television disagree, one of them is wrong and the
difference says which part. If the shapes match and the colours do not, it is
lighting or the frame buffer format. If a texture is right here and flat on
the console, it is the upload. If both are wrong the same way, this is
faithfully reproducing a real bug, which is the outcome that saves the most
time.
"""

import json
import math
import os
import re

import numpy as np

from . import ps2camera
from . import ps2budget

# The runtime's own vertex and face tables. A cube's corner i takes the sign of
# each bit of i, and the faces are wound the way nc_world_cube winds them.
CORNERS = [(1 if i & 1 else -1, 1 if i & 2 else -1, 1 if i & 4 else -1)
           for i in range(8)]
FACES = ((0, 1, 3, 2), (4, 5, 7, 6), (0, 1, 5, 4),
         (2, 3, 7, 6), (0, 2, 6, 4), (1, 3, 7, 5))
FACE_NORMALS = ((0, 0, -1), (0, 0, 1), (0, -1, 0),
                (0, 1, 0), (-1, 0, 0), (1, 0, 0))


def _rotate(point, rotation):
    """The runtime's rotation order: X, then Y, then Z."""
    x, y, z = point
    ax, ay, az = [v * math.pi / 180.0 for v in rotation]
    y, z = y * math.cos(ax) - z * math.sin(ax), y * math.sin(ax) + z * math.cos(ax)
    x, z = x * math.cos(ay) + z * math.sin(ay), -x * math.sin(ay) + z * math.cos(ay)
    x, y = x * math.cos(az) - y * math.sin(az), x * math.sin(az) + y * math.cos(az)
    return x, y, z


def lights_of(world):
    """Direction towards each light and its power, as ps2materials compiles them."""
    lights = []
    ambient = 0.0
    for light in world.get('lights', {}).values():
        direction = [float(v) for v in light.get('direction', [0, -1, 0])]
        length = math.sqrt(sum(v * v for v in direction)) or 1.0
        lights.append(([-v / length for v in direction],
                       float(light.get('intensity', 1.0))))
        ambient = max(ambient, float(light.get('ambient', 0.0)))
    if not lights:
        ambient = max(ambient, 1.0)
    return lights, ambient


def face_shades(rotation, lights, ambient):
    """How lit each of the six faces is, 0..1. nc_world_shade, in Python."""
    shades = []
    for normal in FACE_NORMALS:
        nx, ny, nz = _rotate(normal, rotation)
        lit = ambient
        for direction, power in lights:
            towards = nx * direction[0] + ny * direction[1] + nz * direction[2]
            if towards > 0:
                lit += towards * power
        shades.append(min(1.0, max(0.0, lit)))
    return shades


def _texture(path):
    """A material PNG padded to power-of-two, as the material compiler pads it."""
    from PIL import Image
    with Image.open(path) as opened:
        image = opened.convert('RGBA')
    width, height = ps2budget.pow2(image.width), ps2budget.pow2(image.height)
    canvas = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    canvas.paste(image, (0, 0))
    return np.asarray(canvas, dtype=np.float32) / 255.0, image.width, image.height


def _triangle(colour, depth_of, points, uvs, shade, texture, used,
              perspective=True):
    """Fill one triangle, perspective-correct or affine.

    Both, because the runtime offers both. Affine interpolates the texture
    coordinate straight across the screen, which is what the GS does for a
    primitive carrying fixed-point UV, and it visibly bends a large floor
    along the diagonal of every quad. Perspective-correct divides through by
    an interpolated 1/z, which is what the GS does when the primitive carries
    ST with a per-vertex Q.

    Reproducing whichever one the runtime is set to is the point; a renderer
    that was always "better" than the console would hide the difference
    instead of showing it.
    """
    height, width = colour.shape[:2]
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    low_x, high_x = max(0, int(min(xs))), min(width - 1, int(max(xs)) + 1)
    low_y, high_y = max(0, int(min(ys))), min(height - 1, int(max(ys)) + 1)
    if low_x > high_x or low_y > high_y:
        return
    (x0, y0), (x1, y1), (x2, y2) = [(p[0], p[1]) for p in points]
    area = (x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0)
    if abs(area) < 1e-6:
        return
    grid_y, grid_x = np.mgrid[low_y:high_y + 1, low_x:high_x + 1]
    px, py = grid_x + 0.5, grid_y + 0.5
    w1 = ((px - x0) * (y2 - y0) - (x2 - x0) * (py - y0)) / area
    w2 = ((x1 - x0) * (py - y0) - (px - x0) * (y1 - y0)) / area
    w0 = 1.0 - w1 - w2
    inside = (w0 >= 0) & (w1 >= 0) & (w2 >= 0)
    if not inside.any():
        return
    # Painter's algorithm, as the runtime does it -- faces are already sorted
    # back to front, so a later face simply wins.
    if perspective:
        inverse = [1.0 / d if d else 0.0 for d in depth_of]
        across = w0 * inverse[0] + w1 * inverse[1] + w2 * inverse[2]
        across = np.where(np.abs(across) < 1e-9, 1e-9, across)
        u = (w0 * uvs[0][0] * inverse[0] + w1 * uvs[1][0] * inverse[1]
             + w2 * uvs[2][0] * inverse[2]) / across
        v = (w0 * uvs[0][1] * inverse[0] + w1 * uvs[1][1] * inverse[1]
             + w2 * uvs[2][1] * inverse[2]) / across
    else:
        u = w0 * uvs[0][0] + w1 * uvs[1][0] + w2 * uvs[2][0]
        v = w0 * uvs[0][1] + w1 * uvs[1][1] + w2 * uvs[2][1]
    tex_h, tex_w = texture.shape[:2]
    ui = np.clip(u.astype(np.int32), 0, tex_w - 1)
    vi = np.clip(v.astype(np.int32), 0, tex_h - 1)
    texel = texture[vi, ui]
    opaque = inside & (texel[..., 3] >= 0.5)      # the runtime's alpha test
    if not opaque.any():
        return
    lit = texel[..., :3] * shade
    region = colour[low_y:high_y + 1, low_x:high_x + 1]
    region[opaque] = lit[opaque]


def render(project, size=None, background=(0x14, 0x18, 0x1a), quantise=None,
           override_material=None, perspective=True):
    """Draw the project's 3D world the way the console would.

    Returns a PIL image. `quantise` defaults to whatever colour depth the
    project's own frame buffer uses, so the preview bands exactly where the
    television will.
    """
    from PIL import Image
    root = os.path.abspath(project)
    with open(os.path.join(root, 'world3d.json'), encoding='utf-8') as handle:
        world = json.load(handle)

    psm, _, screen = ps2budget.frame_setup(root)
    size = size or screen
    if quantise is None:
        quantise = 5 if '16' in psm else 8

    camera = world.get('camera', {})
    pos = [float(v) for v in camera.get('pos', [6, 4.5, -8])]
    target = [float(v) for v in camera.get('target', [0, 0, 0])]
    fov = float(camera.get('fov', 60))
    lights, ambient = lights_of(world)

    colour = np.zeros((size[1], size[0], 3), dtype=np.float32)
    colour[:, :] = np.array(background, dtype=np.float32) / 255.0

    textures = {}
    for name, obj in world.get('objects', {}).items():
        material = override_material or obj.get('material')
        if not material:
            continue
        if material not in textures:
            full = os.path.join(root, material)
            if not os.path.isfile(full):
                continue
            textures[material] = _texture(full)
        texture, used_w, used_h = textures[material]
        position = [float(v) for v in obj.get('position', [0, 0, 0])]
        rotation = [float(v) for v in obj.get('rotation', [0, 0, 0])]
        scale = [float(v) for v in obj.get('scale', [1, 1, 1])]
        shades = face_shades(rotation, lights, ambient)

        screen_points, depths = [], []
        for corner in CORNERS:
            local = _rotate([corner[i] * scale[i] for i in range(3)], rotation)
            point = [local[i] + position[i] for i in range(3)]
            placed = ps2camera.ps2_pixels(pos, target, fov, point, screen=size)
            if placed is None:
                screen_points.append(None)
                depths.append(0.0)
            else:
                screen_points.append((placed[0] + size[0] * 0.5,
                                      placed[1] + size[1] * 0.5))
                depths.append(placed[2])

        order = sorted(range(6), key=lambda f: -sum(depths[v] for v in FACES[f]))
        for face in order:
            quad = FACES[face]
            if any(screen_points[v] is None for v in quad):
                continue
            # Corner 1 and 2 take the far edge in u, corners 2 and 3 in v --
            # the same mapping nc_world_cube writes into the UV register.
            uv = [((used_w - 1) if c in (1, 2) else 0,
                   (used_h - 1) if c >= 2 else 0) for c in range(4)]
            for a, b, c in ((0, 1, 2), (0, 2, 3)):
                _triangle(colour, [depths[quad[a]], depths[quad[b]], depths[quad[c]]],
                          [screen_points[quad[a]], screen_points[quad[b]],
                           screen_points[quad[c]]],
                          [uv[a], uv[b], uv[c]], shades[face], texture,
                          (used_w, used_h), perspective)

    pixels = np.clip(colour, 0.0, 1.0)
    if quantise < 8:
        levels = (1 << quantise) - 1
        pixels = np.round(pixels * levels) / levels
    return Image.fromarray((pixels * 255.0 + 0.5).astype(np.uint8), 'RGB')


def describe(project):
    """A line per light and object, for reading next to the picture."""
    root = os.path.abspath(project)
    with open(os.path.join(root, 'world3d.json'), encoding='utf-8') as handle:
        world = json.load(handle)
    lights, ambient = lights_of(world)
    rows = ['  ambient %.2f, %d light(s)' % (ambient, len(lights))]
    for name, obj in world.get('objects', {}).items():
        shades = face_shades([float(v) for v in obj.get('rotation', [0, 0, 0])],
                             lights, ambient)
        rows.append('  %-14s faces -Z %.2f +Z %.2f -Y %.2f +Y %.2f -X %.2f +X %.2f'
                    % tuple([name[:14]] + shades))
    return '\n'.join(rows)
