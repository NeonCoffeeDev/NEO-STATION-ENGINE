"""A reference humanoid: a rig with proper joint names, and a body on it.

Every character problem is easier with a character you control. Cloud is a
useful fixture and a terrible one to debug against: 318 bones named bone000
upward, most of them cape and hair, no semantic names at all, and no
animation. When a walk cycle looks wrong on him there is no way to tell
whether the clip, the retargeter, the skinning or the renderer is at fault.

So this builds one that cannot be any of those things. The skeleton uses the
CMU motion capture joint names exactly -- Hips, LeftUpLeg, LeftForeArm and the
rest -- which means a CMU clip drives it with no retargeting step at all. If a
walk looks right here and wrong on a real character, the fault is in the
retarget. If it looks wrong here, the fault is upstream of every character.

That is also what makes it the backup the project needs: a game can ship with
this figure standing in for anything not yet modelled, and it is original
geometry rather than somebody's asset, so it can live in the repository.

Proportions are a 1.75 m adult, in the engine's units where a cube is two
across and Y is up.
"""

import numpy as np

from .meshimport import Mesh, Part
from .smdimport import Skeleton

# name, parent, offset from the parent, and the box drawn for the segment
# leading to it. CMU's own hierarchy, joint for joint, so a clip from that
# library needs no bone mapping whatsoever.
SKELETON = [
    # name, parent, offset from parent, box width, joint the box reaches to.
    # Mixamo's hierarchy and Mixamo's names, minus the fingers. That is the
    # base because it is where the animation comes from: a clip downloaded for
    # this rig drives it with no mapping step, and a mapping step is a place
    # for a walk to go subtly wrong with nothing to compare against.
    #
    # The reach is named rather than inferred: averaging every child puts the
    # pelvis box inside the hips and fuses both thighs into one slab, because
    # Hips has three children and the mean of them is Hips.
    ('Hips',            None,            (0.00,  1.01,  0.00), 0.30, 'Spine'),
    ('Spine',           'Hips',          (0.00,  0.10,  0.00), 0.30, 'Spine1'),
    ('Spine1',          'Spine',         (0.00,  0.12,  0.00), 0.32, 'Spine2'),
    ('Spine2',          'Spine1',        (0.00,  0.12,  0.00), 0.34, 'Neck'),
    ('Neck',            'Spine2',        (0.00,  0.13,  0.00), 0.09, 'Head'),
    ('Head',            'Neck',          (0.00,  0.10,  0.00), 0.18, None),
    ('LeftShoulder',    'Spine2',        (0.05,  0.09,  0.00), 0.00, None),
    # The arms hang. A bone lying along X cannot be swung forward by an X
    # rotation -- that spins it on its own axis -- so the rest pose puts them
    # down, where a walk's swing is the same rotation the legs use.
    ('LeftArm',         'LeftShoulder',  (0.13,  0.00,  0.00), 0.11, 'LeftForeArm'),
    ('LeftForeArm',     'LeftArm',       (0.04, -0.27,  0.00), 0.09, 'LeftHand'),
    ('LeftHand',        'LeftForeArm',   (0.02, -0.24,  0.00), 0.08, None),
    ('RightShoulder',   'Spine2',        (-0.05, 0.09,  0.00), 0.00, None),
    ('RightArm',        'RightShoulder', (-0.13, 0.00,  0.00), 0.11, 'RightForeArm'),
    ('RightForeArm',    'RightArm',      (-0.04, -0.27, 0.00), 0.09, 'RightHand'),
    ('RightHand',       'RightForeArm',  (-0.02, -0.24, 0.00), 0.08, None),
    ('LeftUpLeg',       'Hips',          (0.11, -0.06,  0.00), 0.15, 'LeftLeg'),
    ('LeftLeg',         'LeftUpLeg',     (0.00, -0.44,  0.00), 0.13, 'LeftFoot'),
    ('LeftFoot',        'LeftLeg',       (0.00, -0.43,  0.00), 0.11, 'LeftToeBase'),
    ('LeftToeBase',     'LeftFoot',      (0.00, -0.08,  0.10), 0.10, None),
    ('RightUpLeg',      'Hips',          (-0.11, -0.06, 0.00), 0.15, 'RightLeg'),
    ('RightLeg',        'RightUpLeg',    (0.00, -0.44,  0.00), 0.13, 'RightFoot'),
    ('RightFoot',       'RightLeg',      (0.00, -0.43,  0.00), 0.11, 'RightToeBase'),
    ('RightToeBase',    'RightFoot',     (0.00, -0.08,  0.10), 0.10, None),
]

# Mixamo prefixes every bone in an exported FBX; CMU and most other libraries
# name the same joints differently. Resolving through this means a clip from
# anywhere lands on the right bone without the rig itself having to change.
ALIASES = {
    'mixamorig:Hips': 'Hips', 'mixamorig:Spine': 'Spine',
    'mixamorig:Spine1': 'Spine1', 'mixamorig:Spine2': 'Spine2',
    'mixamorig:Neck': 'Neck', 'mixamorig:Head': 'Head',
    'mixamorig:LeftShoulder': 'LeftShoulder', 'mixamorig:LeftArm': 'LeftArm',
    'mixamorig:LeftForeArm': 'LeftForeArm', 'mixamorig:LeftHand': 'LeftHand',
    'mixamorig:RightShoulder': 'RightShoulder', 'mixamorig:RightArm': 'RightArm',
    'mixamorig:RightForeArm': 'RightForeArm', 'mixamorig:RightHand': 'RightHand',
    'mixamorig:LeftUpLeg': 'LeftUpLeg', 'mixamorig:LeftLeg': 'LeftLeg',
    'mixamorig:LeftFoot': 'LeftFoot', 'mixamorig:LeftToeBase': 'LeftToeBase',
    'mixamorig:RightUpLeg': 'RightUpLeg', 'mixamorig:RightLeg': 'RightLeg',
    'mixamorig:RightFoot': 'RightFoot', 'mixamorig:RightToeBase': 'RightToeBase',
    # CMU splits the lower spine differently and adds hip and neck stubs.
    'LowerBack': 'Spine', 'LHipJoint': 'LeftUpLeg', 'RHipJoint': 'RightUpLeg',
    'Neck1': 'Neck', 'LeftFingerBase': 'LeftHand', 'RightFingerBase': 'RightHand',
}


def resolve(name):
    """The rig's own name for a joint some other library calls something else."""
    if name in ALIASES:
        return ALIASES[name]
    bare = name.split(':')[-1]
    return ALIASES.get(bare, bare)

# Where a segment's box ends, for the joints nothing hangs off.
TIPS = {'Head': (0.00, 0.15, 0.00), 'LeftHand': (0.01, -0.09, 0.00),
        'RightHand': (-0.01, -0.09, 0.00), 'LeftToeBase': (0.00, 0.00, 0.09),
        'RightToeBase': (0.00, 0.00, 0.09)}


def skeleton():
    """The rig on its own, in the bind pose."""
    rig = Skeleton()
    index = {}
    local = []
    for slot, (name, parent, offset, _, _reach) in enumerate(SKELETON):
        index[name] = slot
        rig.names.append(name)
        rig.parents.append(index[parent] if parent else -1)
        matrix = np.eye(4)
        matrix[:3, 3] = offset
        local.append(matrix)
    rig.bind_local = np.asarray(local)
    rig.bind_world = rig.world_from_local(rig.bind_local)
    rig.inverse_bind = np.asarray([np.linalg.inv(m) for m in rig.bind_world])
    return rig


def _box(a, b, width, bone):
    """A box from a to b, `width` across, as eight vertices and twelve faces.

    Segments are boxes rather than capsules because this is a stand-in whose
    job is to show a pose clearly, and because a box is what the console's
    renderer already knows how to draw.
    """
    a, b = np.asarray(a, dtype=np.float64), np.asarray(b, dtype=np.float64)
    along = b - a
    length = np.linalg.norm(along)
    if length < 1e-6:
        along, length = np.array([0.0, 1.0, 0.0]), 1e-6
    along = along / length
    # Any two directions across the segment will do, as long as they are
    # perpendicular to it and to each other. The helper has to be the axis
    # *least* aligned with the segment: picking one that happens to run along
    # it -- a toe pointing down +Z, say -- gives a zero-length cross product
    # and a box full of NaN.
    helper = np.zeros(3)
    helper[int(np.argmin(np.abs(along)))] = 1.0
    side = np.cross(along, helper)
    side /= np.linalg.norm(side)
    up = np.cross(along, side)
    half = width * 0.5

    corners = []
    for end in (a, b):
        for sx in (-1, 1):
            for sy in (-1, 1):
                corners.append(end + side * (sx * half) + up * (sy * half))
    # Wound so each face's cross product points outwards, matching the
    # convention the rest of the engine culls by.
    faces = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1),
             (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    return corners, faces


def figure(rig=None, width_scale=1.0):
    """The reference character: a Mesh, rigidly skinned to the rig."""
    rig = rig or skeleton()
    positions, normals, uvs, bones, indices = [], [], [], [], []
    world = rig.bind_world

    for slot, (name, parent, _, width, reach) in enumerate(SKELETON):
        if width <= 0:
            continue
        start = world[slot][:3, 3]
        if reach:
            end = world[rig.index(reach)][:3, 3]
        elif name in TIPS:
            end = start + np.asarray(TIPS[name])
        else:
            continue
        corners, faces = _box(start, end, width * width_scale, slot)
        for quad in faces:
            base = len(positions)
            points = [corners[c] for c in quad]
            normal = np.cross(points[1] - points[0], points[2] - points[0])
            length = np.linalg.norm(normal)
            normal = normal / length if length > 1e-9 else np.array([0.0, 1.0, 0.0])
            for corner, point in enumerate(points):
                positions.append(point)
                normals.append(normal)
                uvs.append(((1.0, 0.0), (0.0, 0.0), (0.0, 1.0), (1.0, 1.0))[corner])
                bones.append(slot)
            indices.extend((base, base + 1, base + 2, base, base + 2, base + 3))

    mesh = Mesh()
    mesh.source = 'nc_figure'
    mesh.positions = np.asarray(positions, dtype=np.float32)
    mesh.normals = np.asarray(normals, dtype=np.float32)
    mesh.uvs = np.asarray(uvs, dtype=np.float32)
    mesh.indices = np.asarray(indices, dtype=np.int32)
    mesh.parts = [Part('figure', 0, len(indices))]
    mesh.materials = {'figure': None}
    mesh.bones = np.asarray(bones, dtype=np.int32)
    mesh.skeleton = rig
    mesh.clip_count = 0
    return mesh


def describe(rig=None):
    rig = rig or skeleton()
    height = rig.bind_world[:, 1, 3].max()
    return ('\n  NC reference figure'
            '\n    %d joints, CMU motion capture names, %.2f units tall'
            '\n    a clip from that library drives this rig with no retargeting'
            % (len(rig), height))
