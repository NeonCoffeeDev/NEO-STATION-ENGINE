"""The reference figure: a rig whose joints have names that mean something."""

import unittest

import numpy as np

from ncc import ncfigure, smdimport


class FigureTests(unittest.TestCase):
    def setUp(self):
        self.rig = ncfigure.skeleton()
        self.mesh = ncfigure.figure(self.rig)

    def test_the_joints_are_named_the_way_mixamo_names_them(self):
        """The entire point: a Mixamo clip drives this rig with no retargeting,
        so a walk that looks wrong here is wrong before any character."""
        for joint in ('Hips', 'Spine', 'Spine1', 'Spine2', 'Neck', 'Head',
                      'LeftShoulder', 'LeftArm', 'LeftForeArm', 'LeftHand',
                      'RightShoulder', 'RightArm', 'RightForeArm', 'RightHand',
                      'LeftUpLeg', 'LeftLeg', 'LeftFoot', 'LeftToeBase',
                      'RightUpLeg', 'RightLeg', 'RightFoot', 'RightToeBase'):
            self.assertGreaterEqual(self.rig.index(joint), 0,
                                    '%s is missing from the rig' % joint)

    def test_other_libraries_names_resolve_onto_this_rig(self):
        """Mixamo prefixes every bone; CMU splits the lower spine differently.
        Both have to land on the right joint without the rig changing."""
        for given, expected in (('mixamorig:LeftForeArm', 'LeftForeArm'),
                                ('mixamorig:Hips', 'Hips'),
                                ('LowerBack', 'Spine'),
                                ('Neck1', 'Neck'),
                                ('LHipJoint', 'LeftUpLeg')):
            resolved = ncfigure.resolve(given)
            self.assertEqual(resolved, expected)
            self.assertGreaterEqual(self.rig.index(resolved), 0)

    def test_there_is_exactly_one_root_and_it_is_the_hips(self):
        self.assertEqual(self.rig.roots, [self.rig.index('Hips')])

    def test_the_figure_is_adult_sized_and_stands_on_the_floor(self):
        low, high = self.mesh.bounds()
        height = float(high[1] - low[1])
        self.assertTrue(1.6 < height < 1.95, 'height is %.2f' % height)
        self.assertLess(abs(float(low[1])), 0.12, 'the feet are not near y=0')

    def test_nothing_in_the_geometry_is_not_a_number(self):
        """A segment running along the axis used to build its cross section
        gives a zero-length cross product and a box full of NaN."""
        self.assertFalse(bool(np.isnan(self.mesh.positions).any()))
        self.assertFalse(bool(np.isnan(self.mesh.normals).any()))

    def test_every_vertex_is_bound_to_a_bone(self):
        self.assertEqual(len(self.mesh.bones), self.mesh.vertex_count)
        self.assertTrue((self.mesh.bones >= 0).all())

    def test_the_legs_are_separate(self):
        """Averaging every child of the hips fused both thighs into one slab."""
        left = self.mesh.positions[self.mesh.bones == self.rig.index('LeftUpLeg')]
        right = self.mesh.positions[self.mesh.bones == self.rig.index('RightUpLeg')]
        self.assertGreater(float(left[:, 0].min()), float(right[:, 0].max()),
                           'the thighs overlap in x')

    def test_the_bind_pose_skins_back_to_itself(self):
        points, _ = smdimport.skin(self.mesh, self.rig.bind_world)
        np.testing.assert_allclose(points, self.mesh.positions, atol=1e-5)

    def test_posing_a_named_joint_moves_only_what_hangs_off_it(self):
        local = self.rig.bind_local.copy()
        elbow = self.rig.index('LeftForeArm')
        local[elbow][:3, 3] += np.array([0.0, 0.5, 0.0])
        points, _ = smdimport.skin(self.mesh, self.rig.world_from_local(local))
        moved = np.linalg.norm(points - self.mesh.positions, axis=1) > 1e-6
        hand = self.rig.index('LeftHand')
        self.assertTrue(moved[self.mesh.bones == hand].all(),
                        'the hand did not follow the forearm')
        self.assertFalse(moved[self.mesh.bones == self.rig.index('RightArm')].any(),
                         'the other arm moved')
        self.assertFalse(moved[self.mesh.bones == self.rig.index('Head')].any(),
                         'the head moved')


if __name__ == '__main__':
    unittest.main()


class RuntimeSkinTests(unittest.TestCase):
    """The console's own skinning arithmetic, read out of nc_skin.h.

    A clip is authored in Python against one Euler convention and played in C
    against another. If those disagree the character still moves, plausibly,
    and every pose is wrong by an amount nobody can name from a photograph --
    so the C is read here and evaluated rather than trusted.
    """

    import re as _re
    from pathlib import Path as _Path

    SOURCE = (_Path(__file__).resolve().parents[1]
              / 'ncc' / 'templates' / 'ps2_hybrid' / 'src' / 'nc_skin.h')

    def c_euler(self, x, y, z):
        import math
        import re
        text = self.SOURCE.read_text(encoding='utf-8')
        body = text[text.index('nc_mat34_euler'):]
        body = body[:body.index('\n}')]
        scope = {'cosf': math.cos, 'sinf': math.sin, 'x': x, 'y': y, 'z': z}
        for line in body.split('\n'):
            line = line.strip().rstrip(';')
            assign = re.match(r'^float (\w+) = (.+?), (\w+) = (.+)$', line)
            if assign:
                scope[assign.group(1)] = eval(assign.group(2), {}, scope)
                scope[assign.group(3)] = eval(assign.group(4), {}, scope)
                continue
            out = re.match(r'^out\[(\d+)\] = (.+)$', line)
            if out:
                scope['out%s' % out.group(1)] = eval(
                    out.group(2).replace('f;', '').replace('0.f', '0.0'), {}, scope)
        return np.array([[scope['out0'], scope['out1'], scope['out2']],
                         [scope['out4'], scope['out5'], scope['out6']],
                         [scope['out8'], scope['out9'], scope['out10']]])

    def test_the_runtime_rotation_matches_the_one_clips_are_authored_with(self):
        from ncc.smdimport import _matrix
        for angles in ((0.3, -0.7, 0.2), (-1.1, 0.4, 0.9), (0.0, 0.0, 0.0),
                       (1.5, 1.5, -1.5)):
            expected = _matrix((0, 0, 0), angles)[:3, :3]
            np.testing.assert_allclose(self.c_euler(*angles), expected, atol=1e-9,
                                       err_msg='angles %s' % (angles,))

    def test_the_runtime_rotation_is_a_rotation(self):
        matrix = self.c_euler(0.4, -0.8, 1.2)
        np.testing.assert_allclose(matrix @ matrix.T, np.eye(3), atol=1e-9)
        self.assertAlmostEqual(float(np.linalg.det(matrix)), 1.0, places=9)


class ClipTests(unittest.TestCase):
    def setUp(self):
        from ncc import ncanim
        self.rig = ncfigure.skeleton()
        self.walk = ncanim.walk(self.rig)
        self.idle = ncanim.idle(self.rig)

    def test_every_joint_a_clip_names_exists_on_the_rig(self):
        """A clip addressed to a joint the rig does not have silently animates
        whatever happens to sit at that index."""
        for clip in (self.walk, self.idle):
            for bone in clip.joints:
                self.assertTrue(0 <= bone < len(self.rig),
                                '%s addresses bone %d' % (clip.name, bone))

    def test_the_walk_loops_without_a_jump(self):
        """The last frame has to lead back into the first, or the character
        twitches once per stride."""
        step = self.walk.rotations[1] - self.walk.rotations[0]
        wrap = self.walk.rotations[0] - self.walk.rotations[-1]
        self.assertLess(float(np.abs(wrap).max()), float(np.abs(step).max()) * 2.5,
                        'the seam between last frame and first is a jump')

    def test_the_legs_are_half_a_cycle_apart(self):
        left = self.walk.joints.index(self.rig.index('LeftUpLeg'))
        right = self.walk.joints.index(self.rig.index('RightUpLeg'))
        half = self.walk.frames // 2
        np.testing.assert_allclose(self.walk.rotations[:, left, 0],
                                   np.roll(self.walk.rotations[:, right, 0], half),
                                   atol=1e-5)

    def test_the_knees_only_bend_one_way(self):
        """A knee that goes negative is a leg bending forwards at the joint."""
        for side in ('LeftLeg', 'RightLeg'):
            slot = self.walk.joints.index(self.rig.index(side))
            self.assertGreaterEqual(float(self.walk.rotations[:, slot, 0].min()),
                                    -1e-6, '%s bends backwards' % side)

    def test_the_arms_swing_against_the_legs(self):
        """Same-side arm and leg swinging together is the thing that makes a
        walk look like a toy soldier."""
        leg = self.walk.joints.index(self.rig.index('LeftUpLeg'))
        arm = self.walk.joints.index(self.rig.index('LeftArm'))
        correlation = float(np.corrcoef(self.walk.rotations[:, leg, 0],
                                        self.walk.rotations[:, arm, 0])[0, 1])
        self.assertLess(correlation, -0.8,
                        'left arm and left leg swing together (%.2f)' % correlation)
