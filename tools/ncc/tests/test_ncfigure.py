"""The reference figure: a rig whose joints have names that mean something."""

import unittest

import numpy as np

from ncc import ncfigure, smdimport


class FigureTests(unittest.TestCase):
    def setUp(self):
        self.rig = ncfigure.skeleton()
        self.mesh = ncfigure.figure(self.rig)

    def test_the_joints_are_named_the_way_the_capture_library_names_them(self):
        """The entire point: a CMU clip drives this rig with no retargeting,
        so a walk that looks wrong here is wrong before any character."""
        for joint in ('Hips', 'LeftUpLeg', 'LeftLeg', 'LeftFoot', 'LeftToeBase',
                      'RightUpLeg', 'LowerBack', 'Spine', 'Spine1', 'Neck',
                      'Head', 'LeftShoulder', 'LeftArm', 'LeftForeArm',
                      'LeftHand', 'RightForeArm', 'RightHand'):
            self.assertGreaterEqual(self.rig.index(joint), 0,
                                    '%s is missing from the rig' % joint)

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
