"""Bring a real model into the engine: Wavefront OBJ, with its materials.

Crocotile and Blender both write this, and so did the tools people were using
when the PlayStation 2 was new, which is why a model ripped from a 2002 game
and a tileset exported this morning arrive in the same shape.

What comes out the other side is an NCMesh: one flat array of vertices with
position, texture coordinate and normal already interleaved the way the
hardware wants to read them, an index list, and a run of indices per material.
The parts are what matter on this console -- every change of material is a
texture bind, and a bind is not free, so the triangles that share one are kept
together and counted.

Three things this fixes on the way in, because every exporter gets them wrong
in the same ways:

OBJ indexes position, texture coordinate and normal separately, and the GS
cannot. A vertex here is the combination, de-duplicated, so a corner shared by
two faces with the same texture coordinate stays one vertex.

Models frequently arrive with no normals at all -- the Cloud model that
prompted this has 2754 vertices and not one normal. They are generated,
weighted by the area of each face so that a large flat surface is not
outvoted by the slivers around its edge.

And a model is authored in whatever units its artist felt like. A character
224 units tall in a world where a cube is 2 units across is not a mistake to
report, it is a scale to apply, so the importer measures it and says what it
did.
"""

import math
import os
import re

import numpy as np


class MeshError(Exception):
    """Something about the model cannot be represented, with what to do."""


class Part:
    """A run of triangles sharing one material."""

    def __init__(self, material, first, count):
        self.material = material
        self.first = first
        self.count = count


class Mesh:
    def __init__(self):
        self.positions = np.zeros((0, 3), dtype=np.float32)
        self.uvs = np.zeros((0, 2), dtype=np.float32)
        self.normals = np.zeros((0, 3), dtype=np.float32)
        self.indices = np.zeros((0,), dtype=np.int32)
        self.parts = []
        self.materials = {}         # name -> texture path, relative to the model
        self.source = None

    # ---- measurements -------------------------------------------------

    @property
    def triangle_count(self):
        return len(self.indices) // 3

    @property
    def vertex_count(self):
        return len(self.positions)

    def bounds(self):
        if not len(self.positions):
            return np.zeros(3), np.zeros(3)
        return self.positions.min(axis=0), self.positions.max(axis=0)

    def size(self):
        low, high = self.bounds()
        return high - low

    # ---- fixing it up -------------------------------------------------

    def generate_normals(self):
        """Area-weighted vertex normals, for a model that shipped without any.

        Weighting by area rather than treating every face equally is what keeps
        a broad flat panel from being tilted by the narrow triangles that trim
        its edge. Smoothing is by position, not by vertex index, so a seam
        introduced purely to split a texture coordinate does not become a
        visible crease in the lighting.
        """
        tri = self.indices.reshape(-1, 3)
        a = self.positions[tri[:, 0]]
        b = self.positions[tri[:, 1]]
        c = self.positions[tri[:, 2]]
        # The cross product's length is twice the triangle's area, so leaving
        # it un-normalised is the weighting.
        face = np.cross(b - a, c - a)

        # Vertices that sit at the same place act as one, whatever their index.
        quantised = np.round(self.positions * 1024.0).astype(np.int64)
        _, group = np.unique(quantised, axis=0, return_inverse=True)

        summed = np.zeros((group.max() + 1, 3), dtype=np.float64)
        for corner in range(3):
            np.add.at(summed, group[tri[:, corner]], face)

        # A double-sided card -- the same triangle wound both ways, which is
        # how every PlayStation 2 model does hair, cloth and foliage -- sums to
        # exactly zero, because the two halves cancel. 10% of the model that
        # prompted this is built that way. Those vertices fall back to one
        # adjacent face rather than being left with no normal at all, which
        # would light them black.
        fallback = np.zeros_like(summed)
        for corner in range(3):
            fallback[group[tri[:, corner]]] = face
        length = np.linalg.norm(summed, axis=1, keepdims=True)
        summed = np.where(length < 1e-12, fallback, summed)

        length = np.linalg.norm(summed, axis=1, keepdims=True)
        length[length < 1e-12] = 1.0
        self.normals = (summed / length)[group].astype(np.float32)

    def scale_to_height(self, height, axis=1):
        """Fit the model to a world where a cube is two units across."""
        span = float(self.size()[axis])
        if span <= 0:
            return 1.0
        factor = height / span
        self.positions = self.positions * factor
        return factor

    def centre_on_floor(self):
        """Put the model's feet at y=0 and its middle on the origin."""
        low, high = self.bounds()
        offset = np.array([(low[0] + high[0]) * 0.5, low[1],
                           (low[2] + high[2]) * 0.5], dtype=np.float32)
        self.positions = self.positions - offset
        return offset


# ---- reading ----------------------------------------------------------

def _face_index(token, count):
    """One OBJ index: 1-based, and negative counts back from the end."""
    value = int(token)
    return value - 1 if value > 0 else count + value


def load_mtl(path):
    """material name -> diffuse texture, relative to the .mtl."""
    materials = {}
    current = None
    if not os.path.isfile(path):
        return materials
    with open(path, encoding='utf-8', errors='replace') as handle:
        for line in handle:
            parts = line.split()
            if not parts:
                continue
            if parts[0] == 'newmtl':
                current = ' '.join(parts[1:])
                materials.setdefault(current, None)
            elif parts[0].lower() == 'map_kd' and current:
                # map_Kd can carry options before the filename (-s, -o, -bm).
                tokens = [t for t in parts[1:] if not t.startswith('-')]
                skip = 0
                cleaned = []
                for token in parts[1:]:
                    if skip:
                        skip -= 1
                        continue
                    if token.startswith('-'):
                        skip = 3 if token in ('-s', '-o', '-t') else 1
                        continue
                    cleaned.append(token)
                materials[current] = ' '.join(cleaned or tokens)
    return materials


def load_obj(path):
    """Read an OBJ and its material library into one Mesh."""
    root = os.path.dirname(os.path.abspath(path))
    positions, uvs, normals = [], [], []
    # (position, uv, normal) -> index into the unified vertex array.
    unified = {}
    out_pos, out_uv, out_nrm, indices = [], [], [], []
    runs = []                   # (material, first index, count)
    current = None
    materials = {}

    with open(path, encoding='utf-8', errors='replace') as handle:
        for number, line in enumerate(handle, 1):
            parts = line.split()
            if not parts or parts[0].startswith('#'):
                continue
            tag = parts[0]
            if tag == 'v':
                positions.append([float(v) for v in parts[1:4]])
            elif tag == 'vt':
                uvs.append([float(v) for v in parts[1:3]])
            elif tag == 'vn':
                normals.append([float(v) for v in parts[1:4]])
            elif tag == 'mtllib':
                materials.update(load_mtl(os.path.join(root, ' '.join(parts[1:]))))
            elif tag == 'usemtl':
                name = ' '.join(parts[1:])
                if runs and runs[-1][0] == name:
                    continue
                runs.append([name, len(indices), 0])
                current = name
            elif tag == 'f':
                if not runs:
                    runs.append([current or 'default', len(indices), 0])
                corners = []
                for token in parts[1:]:
                    bits = (token.split('/') + ['', ''])[:3]
                    try:
                        pi = _face_index(bits[0], len(positions))
                        ti = _face_index(bits[1], len(uvs)) if bits[1] else -1
                        ni = _face_index(bits[2], len(normals)) if bits[2] else -1
                    except ValueError:
                        raise MeshError('%s line %d: face index is not a number'
                                        % (os.path.basename(path), number))
                    key = (pi, ti, ni)
                    slot = unified.get(key)
                    if slot is None:
                        slot = len(out_pos)
                        unified[key] = slot
                        if not 0 <= pi < len(positions):
                            raise MeshError('%s line %d: vertex %d does not exist'
                                            % (os.path.basename(path), number, pi + 1))
                        out_pos.append(positions[pi])
                        out_uv.append(uvs[ti] if 0 <= ti < len(uvs) else [0.0, 0.0])
                        out_nrm.append(normals[ni] if 0 <= ni < len(normals)
                                       else [0.0, 0.0, 0.0])
                    corners.append(slot)
                # A fan, so quads and n-gons come in as triangles rather than
                # being refused. Anything concave will fan wrongly, which is a
                # thing to say out loud rather than to pretend cannot happen.
                for i in range(1, len(corners) - 1):
                    indices.extend((corners[0], corners[i], corners[i + 1]))
                runs[-1][2] = len(indices) - runs[-1][1]

    mesh = Mesh()
    mesh.source = path
    mesh.positions = np.asarray(out_pos, dtype=np.float32).reshape(-1, 3)
    mesh.uvs = np.asarray(out_uv, dtype=np.float32).reshape(-1, 2)
    mesh.normals = np.asarray(out_nrm, dtype=np.float32).reshape(-1, 3)
    mesh.indices = np.asarray(indices, dtype=np.int32)
    mesh.parts = [Part(name, first, count) for name, first, count in runs if count]
    mesh.materials = materials
    if not len(mesh.indices):
        raise MeshError('%s contains no faces' % os.path.basename(path))
    if not mesh.normals.any():
        mesh.generate_normals()
    # OBJ texture coordinates put v=0 at the bottom; the GS puts it at the top.
    mesh.uvs[:, 1] = 1.0 - mesh.uvs[:, 1]
    return mesh


# ---- what it will cost ------------------------------------------------

def texture_report(mesh, budget_module=None):
    """Every distinct texture the model needs, and what it occupies in VRAM."""
    from . import ps2budget
    budget_module = budget_module or ps2budget
    root = os.path.dirname(os.path.abspath(mesh.source))
    seen = {}
    for part in mesh.parts:
        texture = mesh.materials.get(part.material)
        if not texture:
            continue
        full = os.path.join(root, texture.replace('\\', '/'))
        if texture in seen or not os.path.isfile(full):
            continue
        from PIL import Image
        with Image.open(full) as image:
            width, height = image.size
        padded = (budget_module.pow2(width), budget_module.pow2(height))
        seen[texture] = {
            'path': full, 'used': (width, height), 'padded': padded,
            'bytes32': budget_module.cost(padded[0], padded[1], 'PSMCT32'),
            'bytes16': budget_module.cost(padded[0], padded[1], 'PSMCT16'),
        }
    return seen


def describe(mesh):
    """A readable account of the model and what it will take to run it."""
    low, high = mesh.bounds()
    size = mesh.size()
    rows = ['', '  %s' % os.path.basename(mesh.source), '',
            '  GEOMETRY   %d triangles, %d vertices, %d material parts'
            % (mesh.triangle_count, mesh.vertex_count, len(mesh.parts)),
            '  SIZE       %.1f x %.1f x %.1f in the units it was authored in'
            % (size[0], size[1], size[2]),
            '  FLOOR      y from %.1f to %.1f' % (low[1], high[1])]
    textures = texture_report(mesh)
    total32 = sum(t['bytes32'] for t in textures.values())
    total16 = sum(t['bytes16'] for t in textures.values())
    rows.append('  TEXTURES   %d distinct, %d KB at 32-bit, %d KB at 16-bit'
                % (len(textures), total32 // 1024, total16 // 1024))
    rows.append('')
    rows.append('  Parts, largest first -- each one is a texture bind per frame:')
    for part in sorted(mesh.parts, key=lambda p: -p.count)[:8]:
        texture = mesh.materials.get(part.material) or '(no texture)'
        rows.append('    %-24s %5d tris  %s'
                    % (part.material[:24], part.count // 3, texture))
    if len(mesh.parts) > 8:
        rows.append('    ... and %d more' % (len(mesh.parts) - 8))
    return '\n'.join(rows)

def unit_cube(texture=None, material='cube'):
    """A two-unit cube as a Mesh, so engine primitives and imported models are
    the same kind of thing to everything downstream."""
    corners = [(x, y, z) for z in (-1, 1) for y in (-1, 1) for x in (-1, 1)]
    faces = [((0, 1, 3, 2), (0, 0, -1)), ((5, 4, 6, 7), (0, 0, 1)),
             ((4, 5, 1, 0), (0, -1, 0)), ((2, 3, 7, 6), (0, 1, 0)),
             ((4, 0, 2, 6), (-1, 0, 0)), ((1, 5, 7, 3), (1, 0, 0))]
    positions, uvs, normals, indices = [], [], [], []
    for quad, normal in faces:
        base = len(positions)
        for slot, corner in enumerate(quad):
            positions.append(corners[corner])
            normals.append(normal)
            uvs.append(((1.0, 0.0), (0.0, 0.0), (0.0, 1.0), (1.0, 1.0))[slot])
        indices.extend((base, base + 1, base + 2, base, base + 2, base + 3))
    mesh = Mesh()
    mesh.source = 'unit_cube'
    mesh.positions = np.asarray(positions, dtype=np.float32)
    mesh.uvs = np.asarray(uvs, dtype=np.float32)
    mesh.normals = np.asarray(normals, dtype=np.float32)
    mesh.indices = np.asarray(indices, dtype=np.int32)
    mesh.parts = [Part(material, 0, len(indices))]
    mesh.materials = {material: texture}
    return mesh
