"""Animation clips: keyframes per joint, sampled at runtime.

The format is the destination, not the source. A clip is a list of joints, a
rotation per joint per frame, and an optional translation for the root -- which
is exactly what falls out of a Mixamo FBX or a motion capture file, and exactly
what the console can sample with a lerp and a matrix build. Authoring a clip
here and reading one from a file produce the same thing, so the runtime that
plays this placeholder is the runtime that plays the real capture.

The two clips in here are placeholders and are labelled as such. They exist so
that skinning, sampling, the renderer and the controller can all be tested on
hardware before any animation data arrives, and so that when a real clip does
arrive there is something to compare it against.

Rotations are XYZ Euler in radians, matching the skeleton's own convention.
Sign conventions, since they are easy to get backwards: the figure faces +Z, a
bone hangs down -Y, and rotating about X by a negative angle swings the far end
towards +Z. So a leg swinging forward is a negative X rotation, and a knee
bending -- heel towards the back -- is a positive one.
"""

import math

import numpy as np


class Clip:
    def __init__(self, name, joints, rotations, root=None, fps=30.0, loop=True):
        self.name = name
        self.joints = list(joints)                  # bone indices
        self.rotations = np.asarray(rotations, dtype=np.float32)
        self.root = None if root is None else np.asarray(root, dtype=np.float32)
        self.fps = fps
        self.loop = loop

    @property
    def frames(self):
        return self.rotations.shape[0]

    def pose(self, rig, time):
        """Local matrices for this clip at `time` seconds, for the preview."""
        from .smdimport import _matrix
        local = rig.bind_local.copy()
        position = time * self.fps
        first = int(math.floor(position)) % self.frames
        second = (first + 1) % self.frames
        blend = position - math.floor(position)
        for slot, bone in enumerate(self.joints):
            angles = (self.rotations[first][slot] * (1.0 - blend)
                      + self.rotations[second][slot] * blend)
            turn = _matrix((0.0, 0.0, 0.0), angles)
            local[bone] = local[bone] @ turn
        if self.root is not None:
            offset = (self.root[first] * (1.0 - blend) + self.root[second] * blend)
            local[rig.roots[0]][:3, 3] = rig.bind_local[rig.roots[0]][:3, 3] + offset
        return local


def _curve(frames, function):
    return [function(i / float(frames)) for i in range(frames)]


def walk(rig, frames=24):
    """A placeholder walk cycle. One full cycle is two steps.

    Not motion capture and not pretending to be. It is built from the handful
    of things that make a walk read at all -- opposed legs, a knee that only
    bends one way, arms counter-swinging, and the body rising twice per cycle
    -- so that a character moving on screen looks like it is walking rather
    than sliding, and so the pipeline underneath it can be judged.
    """
    names = ('LeftUpLeg', 'LeftLeg', 'LeftFoot', 'RightUpLeg', 'RightLeg',
             'RightFoot', 'LeftArm', 'LeftForeArm', 'RightArm', 'RightForeArm',
             'Spine', 'Spine1')
    joints = [rig.index(n) for n in names]
    tau = math.pi * 2.0

    def leg(phase):
        return -0.42 * math.sin(tau * phase)

    def knee(phase):
        # A knee bends one way only. The peak sits just after the leg passes
        # under the body, which is what stops the foot scything through the
        # floor on the way forward.
        return 0.95 * max(0.0, math.sin(tau * phase + 2.2)) ** 1.5

    def ankle(phase):
        return -0.25 * math.sin(tau * phase + 1.1)

    rotations = []
    root = []
    for i in range(frames):
        t = i / float(frames)
        swing = leg(t)
        other = leg(t + 0.5)
        rotations.append([
            (swing, 0.0, 0.0),                      # LeftUpLeg
            (knee(t), 0.0, 0.0),                    # LeftLeg
            (ankle(t), 0.0, 0.0),                   # LeftFoot
            (other, 0.0, 0.0),                      # RightUpLeg
            (knee(t + 0.5), 0.0, 0.0),              # RightLeg
            (ankle(t + 0.5), 0.0, 0.0),             # RightFoot
            # An arm opposes the leg on its own side. Since `other` is
            # exactly -swing, using it here made the left arm track the left
            # leg -- a toy soldier's march, and the sort of wrongness that
            # reads as "the walk looks off" rather than as a bug.
            (-swing * 0.6, 0.0, 0.0),               # LeftArm
            (0.30 + 0.20 * math.sin(tau * t), 0.0, 0.0),
            (-other * 0.6, 0.0, 0.0),               # RightArm
            (0.30 - 0.20 * math.sin(tau * t), 0.0, 0.0),
            (0.0, 0.06 * math.sin(tau * t), 0.0),   # Spine counter-rotates
            (0.03, -0.05 * math.sin(tau * t), 0.0),
        ])
        # The body rises twice per cycle, once per step, and rolls a little
        # towards the supporting leg.
        root.append((0.012 * math.sin(tau * t),
                     0.028 * abs(math.sin(tau * t)) - 0.014,
                     0.0))
    return Clip('walk', joints, rotations, root, fps=frames, loop=True)


def idle(rig, frames=32):
    """A placeholder idle: breathing, and enough sway not to look frozen."""
    names = ('Spine', 'Spine1', 'Spine2', 'Neck', 'LeftArm', 'RightArm',
             'LeftForeArm', 'RightForeArm')
    joints = [rig.index(n) for n in names]
    tau = math.pi * 2.0
    rotations = []
    root = []
    for i in range(frames):
        t = i / float(frames)
        breath = math.sin(tau * t)
        rotations.append([
            (-0.018 * breath, 0.012 * math.sin(tau * t * 0.5), 0.0),
            (-0.014 * breath, 0.0, 0.0),
            (-0.010 * breath, 0.0, 0.0),
            (0.020 * breath, 0.0, 0.0),
            (0.0, 0.0, -0.04 - 0.02 * breath),
            (0.0, 0.0, 0.04 + 0.02 * breath),
            (0.16 + 0.04 * breath, 0.0, 0.0),
            (0.16 + 0.04 * breath, 0.0, 0.0),
        ])
        root.append((0.0, 0.006 * breath, 0.0))
    return Clip('idle', joints, rotations, root, fps=frames * 0.5, loop=True)


def rest(rig):
    """A one-frame clip that is simply the bind pose.

    It exists so that "no animation" is a clip like any other rather than a
    branch in the runtime, and so the lab can show the rig unposed next to the
    same rig moving.
    """
    return Clip('rest', [rig.index('Hips')], [[(0.0, 0.0, 0.0)]],
                fps=1.0, loop=True)
