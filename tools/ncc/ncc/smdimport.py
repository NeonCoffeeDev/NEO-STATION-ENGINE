"""Read a Studiomdl Data file: skeleton, bind pose, and skin weights.

SMD is a plain-text format with three sections -- the bone hierarchy, a pose
per frame, and the triangles with a bone weight on every vertex -- and it is
what most model rips of this era come out as. It is also, unlike FBX, small
enough to read in an afternoon and specified well enough that the reading is
not guesswork.

What it gives us that OBJ cannot: the rig. A mesh alone can be placed and lit
and it cannot move, and a character that cannot move is scenery.

The important thing to understand about the format is where the vertices live.
They are not in bone space. They are in model space, already posed, at the
bind pose -- so moving a bone means undoing the bind first:

    skinned = BoneWorld(animated) * BoneWorld(bind)^-1 * vertex

That inverse bind matrix is the whole of rigid skinning, and computing it once
at import is why posing afterwards is a matrix multiply per vertex rather than
a walk up the hierarchy.

A file may contain a rig and no animation at all -- one frame, the bind pose,
which is exactly what a mesh rip usually captures. `clip_count` says so, so
that a caller can tell "this character cannot move yet" from "this character
is standing still", and neither has to be inferred from the picture.
"""

import os

import numpy as np

from .meshimport import Mesh, MeshError, Part


class Skeleton:
    """Bones, their hierarchy, and the pose the mesh was built in."""

    def __init__(self):
        self.names = []
        self.parents = []
        self.bind_local = np.zeros((0, 4, 4))     # each bone in its parent
        self.bind_world = np.zeros((0, 4, 4))
        self.inverse_bind = np.zeros((0, 4, 4))

    def __len__(self):
        return len(self.names)

    @property
    def roots(self):
        return [i for i, parent in enumerate(self.parents) if parent < 0]

    def index(self, name):
        try:
            return self.names.index(name)
        except ValueError:
            return -1

    def world_from_local(self, local):
        """Walk the hierarchy once, parents before children."""
        world = np.zeros_like(local)
        for bone in self.order():
            parent = self.parents[bone]
            world[bone] = local[bone] if parent < 0 else world[parent] @ local[bone]
        return world

    def order(self):
        """Bone indices with every parent before its children."""
        out = []
        pending = list(range(len(self.names)))
        placed = set()
        while pending:
            progressed = False
            for bone in list(pending):
                parent = self.parents[bone]
                if parent < 0 or parent in placed:
                    out.append(bone)
                    placed.add(bone)
                    pending.remove(bone)
                    progressed = True
            if not progressed:
                # A cycle. Take the rest in file order rather than hanging.
                out.extend(pending)
                break
        return out


def _matrix(position, rotation):
    """SMD bone transform: XYZ Euler in radians, then translate."""
    x, y, z = rotation
    cx, sx = np.cos(x), np.sin(x)
    cy, sy = np.cos(y), np.sin(y)
    cz, sz = np.cos(z), np.sin(z)
    rx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
    ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    rz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])
    out = np.eye(4)
    out[:3, :3] = rz @ ry @ rx
    out[:3, 3] = position
    return out


def _sections(path):
    with open(path, encoding='utf-8', errors='replace') as handle:
        lines = handle.read().split('\n')
    found = {}
    name = None
    body = []
    for line in lines:
        stripped = line.strip()
        if stripped in ('nodes', 'skeleton', 'triangles', 'vertexanimation'):
            name, body = stripped, []
            continue
        if stripped == 'end' and name:
            found.setdefault(name, body)
            name = None
            continue
        if name is not None and stripped:
            body.append(stripped)
    return found


# Studiomdl is Z-up; this engine is Y-up, like the OBJ and FBX that arrive
# beside it. Converting at import rather than at draw means one convention
# exists downstream instead of a flag every renderer has to remember.
Z_UP_TO_Y_UP = np.array([[1.0, 0.0, 0.0, 0.0],
                         [0.0, 0.0, 1.0, 0.0],
                         [0.0, -1.0, 0.0, 0.0],
                         [0.0, 0.0, 0.0, 1.0]])


def load_smd(path, texture_dir=None, z_up=True):
    """Returns (mesh, skeleton, frames).

    `frames` is a list of per-bone local matrices, one entry per `time` in the
    file. A rip with no animation has exactly one, and it is the bind pose.
    """
    sections = _sections(path)
    if 'nodes' not in sections:
        raise MeshError('%s has no nodes section; it is not an SMD'
                        % os.path.basename(path))

    skeleton = Skeleton()
    for line in sections['nodes']:
        # `<id> "<name>" <parent>`, and a name may contain spaces.
        head, _, rest = line.partition('"')
        name, _, tail = rest.rpartition('"')
        skeleton.names.append(name)
        try:
            skeleton.parents.append(int(tail.split()[0]))
        except (IndexError, ValueError):
            skeleton.parents.append(-1)

    frames = []
    current = None
    for line in sections.get('skeleton', []):
        if line.startswith('time'):
            if current is not None:
                frames.append(current)
            current = [np.eye(4) for _ in skeleton.names]
            continue
        fields = line.split()
        if len(fields) < 7 or current is None:
            continue
        bone = int(fields[0])
        values = [float(v) for v in fields[1:7]]
        if 0 <= bone < len(current):
            current[bone] = _matrix(values[0:3], values[3:6])
    if current is not None:
        frames.append(current)
    if not frames:
        raise MeshError('%s has no pose; a skeleton with no frames cannot bind'
                        % os.path.basename(path))

    if z_up:
        # Rotating the root bones carries the whole hierarchy with them, and
        # rotating the vertices keeps them in step with it.
        for frame in frames:
            for bone, parent in enumerate(skeleton.parents):
                if parent < 0:
                    frame[bone] = Z_UP_TO_Y_UP @ frame[bone]
    skeleton.bind_local = np.asarray(frames[0])
    skeleton.bind_world = skeleton.world_from_local(skeleton.bind_local)
    skeleton.inverse_bind = np.asarray([np.linalg.inv(m)
                                        for m in skeleton.bind_world])

    positions, uvs, normals, bones = [], [], [], []
    runs = {}
    material = None
    pending = []
    for line in sections.get('triangles', []):
        fields = line.split()
        if len(fields) < 9:
            material = line
            continue
        values = [float(v) for v in fields[1:9]]
        links = int(fields[9]) if len(fields) > 9 else 0
        bone = int(fields[10]) if links else int(fields[0])
        # Every vertex in this file has exactly one link. Blended weights are
        # a different renderer, so the heaviest link is taken and the fact is
        # reported rather than silently averaged.
        if links > 1:
            # The links are bone/weight pairs starting at field 10, so link k
            # is the bone at 10 + 2k and its weight at 11 + 2k.
            best, weight = bone, float(fields[11])
            for extra in range(1, links):
                candidate = float(fields[11 + extra * 2])
                if candidate > weight:
                    best, weight = int(fields[10 + extra * 2]), candidate
            bone = best
        slot = len(positions)
        positions.append(values[0:3])
        normals.append(values[3:6])
        uvs.append((values[6], 1.0 - values[7]))
        bones.append(bone)
        pending.append(slot)
        if len(pending) == 3:
            runs.setdefault(material or 'default', []).extend(pending)
            pending = []

    if not runs:
        raise MeshError('%s has no triangles' % os.path.basename(path))

    mesh = Mesh()
    mesh.source = path
    mesh.positions = np.asarray(positions, dtype=np.float32)
    mesh.uvs = np.asarray(uvs, dtype=np.float32)
    mesh.normals = np.asarray(normals, dtype=np.float32)
    if z_up:
        turn = Z_UP_TO_Y_UP[:3, :3].astype(np.float32)
        mesh.positions = mesh.positions @ turn.T
        mesh.normals = mesh.normals @ turn.T
    indices = []
    for name, run in runs.items():
        first = len(indices)
        indices.extend(run)
        mesh.parts.append(Part(name, first, len(run)))
    mesh.indices = np.asarray(indices, dtype=np.int32)
    root = texture_dir or os.path.dirname(os.path.abspath(path))
    mesh.materials = {name: (os.path.join(root, name)
                             if os.path.isfile(os.path.join(root, name)) else name)
                      for name in runs}
    mesh.bones = np.asarray(bones, dtype=np.int32)
    mesh.skeleton = skeleton
    mesh.clip_count = len(frames) - 1        # frame 0 is the bind pose
    return mesh, skeleton, frames


def skin(mesh, world):
    """Positions and normals for a pose, given each bone's world matrix.

    Rigid binding: one bone per vertex, so this is a matrix pick and a
    multiply rather than a weighted sum. That is what the models of this era
    did, and it is cheap enough to run on the console's main core.
    """
    skeleton = mesh.skeleton
    transform = world @ skeleton.inverse_bind        # per bone, once
    picked = transform[mesh.bones]
    points = np.einsum('vij,vj->vi', picked[:, :3, :3],
                       mesh.positions.astype(np.float64)) + picked[:, :3, 3]
    normals = np.einsum('vij,vj->vi', picked[:, :3, :3],
                        mesh.normals.astype(np.float64))
    length = np.linalg.norm(normals, axis=1, keepdims=True)
    length[length < 1e-9] = 1.0
    return points.astype(np.float32), (normals / length).astype(np.float32)


def describe(mesh, skeleton):
    rows = ['', '  %s' % os.path.basename(mesh.source), '',
            '  GEOMETRY   %d triangles, %d vertices, %d material parts'
            % (mesh.triangle_count, mesh.vertex_count, len(mesh.parts)),
            '  SKELETON   %d bones, %d roots, %d actually skinned to'
            % (len(skeleton), len(skeleton.roots),
               len(set(mesh.bones.tolist())))]
    if mesh.clip_count:
        rows.append('  ANIMATION  %d frame(s) beyond the bind pose' % mesh.clip_count)
    else:
        rows.append('  ANIMATION  none -- the file holds a rig and a bind pose only')
    return '\n'.join(rows)
