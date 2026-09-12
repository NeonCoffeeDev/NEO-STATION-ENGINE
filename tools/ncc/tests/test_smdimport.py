"""The skeleton reader: hierarchy, bind pose, and rigid skinning."""

import math
import os
import tempfile
import unittest

import numpy as np

from ncc import smdimport
from ncc.meshimport import MeshError


def smd(nodes, skeleton, triangles):
    return ('version 1\nnodes\n%s\nend\nskeleton\n%s\nend\ntriangles\n%s\nend\n'
            % (nodes, skeleton, triangles))


# Two bones in a chain: root at the origin, child one unit up its Z. One
# triangle, every vertex weighted to the child.
TWO_BONE = smd(
    '0 "root" -1\n1 "arm" 0',
    'time 0\n'
    '  0 0 0 0 0 0 0\n'
    '  1 0 0 1 0 0 0',
    'skin.png\n'
    '  0 0 0 1 0 0 1 0 0 1 1 1.000000\n'
    '  0 1 0 1 0 0 1 1 0 1 1 1.000000\n'
    '  0 0 1 1 0 0 1 0 1 1 1 1.000000')


class LoadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.temp.name, 'test.smd')

    def tearDown(self):
        self.temp.cleanup()

    def write(self, text):
        with open(self.path, 'w', encoding='utf-8') as handle:
            handle.write(text)
        return self.path

    def test_a_file_with_no_nodes_is_refused(self):
        self.write('version 1\ntriangles\nend\n')
        with self.assertRaises(MeshError):
            smdimport.load_smd(self.path)

    def test_bones_and_their_parents_are_read(self):
        mesh, skeleton, _ = smdimport.load_smd(self.write(TWO_BONE))
        self.assertEqual(skeleton.names, ['root', 'arm'])
        self.assertEqual(skeleton.parents, [-1, 0])
        self.assertEqual(skeleton.roots, [0])

    def test_a_rip_with_only_a_bind_pose_reports_no_animation(self):
        """The difference between "cannot move" and "is standing still"."""
        mesh, _, frames = smdimport.load_smd(self.write(TWO_BONE))
        self.assertEqual(len(frames), 1)
        self.assertEqual(mesh.clip_count, 0)

    def test_extra_frames_are_counted_as_animation(self):
        text = TWO_BONE.replace(
            '  1 0 0 1 0 0 0',
            '  1 0 0 1 0 0 0\ntime 1\n  0 0 0 0 0 0 0\n  1 0 0 1 0 0 0.5')
        mesh, _, frames = smdimport.load_smd(self.write(text))
        self.assertEqual(len(frames), 2)
        self.assertEqual(mesh.clip_count, 1)

    def test_every_vertex_carries_a_bone(self):
        mesh, _, _ = smdimport.load_smd(self.write(TWO_BONE))
        self.assertEqual(len(mesh.bones), mesh.vertex_count)
        self.assertTrue((mesh.bones == 1).all())

    def test_the_heaviest_link_wins_when_weights_are_blended(self):
        """This renderer binds rigidly, so a blend has to resolve to one bone
        rather than be silently averaged into a position between them."""
        text = TWO_BONE.replace(
            '  0 0 0 1 0 0 1 0 0 1 1 1.000000',
            '  0 0 0 1 0 0 1 0 0 2 0 0.250000 1 0.750000')
        mesh, _, _ = smdimport.load_smd(self.write(text))
        self.assertEqual(int(mesh.bones[0]), 1)

    def test_z_up_becomes_y_up(self):
        """Studiomdl is Z-up and this engine is Y-up; one convention has to
        exist downstream or every renderer needs a flag."""
        mesh, _, _ = smdimport.load_smd(self.write(TWO_BONE))
        # The triangle spans z 1..1 and y 0..1 in the file, so after the turn
        # the height sits in Y and the depth in Z.
        low, high = mesh.bounds()
        self.assertAlmostEqual(float(low[1]), 1.0, places=5)
        mesh_raw, _, _ = smdimport.load_smd(self.path, z_up=False)
        low_raw, _ = mesh_raw.bounds()
        self.assertAlmostEqual(float(low_raw[2]), 1.0, places=5)


class SkinningTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.temp.name, 'test.smd')
        with open(self.path, 'w', encoding='utf-8') as handle:
            handle.write(TWO_BONE)
        self.mesh, self.skeleton, _ = smdimport.load_smd(self.path)

    def tearDown(self):
        self.temp.cleanup()

    def test_the_bind_pose_reproduces_the_mesh_exactly(self):
        """If posing at the bind pose moves anything, the inverse bind is wrong
        and every other pose is wrong by the same amount."""
        points, normals = smdimport.skin(self.mesh, self.skeleton.bind_world)
        np.testing.assert_allclose(points, self.mesh.positions, atol=1e-5)
        np.testing.assert_allclose(normals, self.mesh.normals, atol=1e-5)

    def test_moving_a_bone_moves_the_vertices_bound_to_it(self):
        local = self.skeleton.bind_local.copy()
        local[1][:3, 3] += np.array([5.0, 0.0, 0.0])
        points, _ = smdimport.skin(self.mesh, self.skeleton.world_from_local(local))
        moved = points - self.mesh.positions
        np.testing.assert_allclose(moved, np.tile([5.0, 0.0, 0.0], (3, 1)), atol=1e-5)

    def test_moving_a_parent_carries_its_children(self):
        """The whole reason a hierarchy exists."""
        local = self.skeleton.bind_local.copy()
        local[0][:3, 3] += np.array([0.0, 2.0, 0.0])
        points, _ = smdimport.skin(self.mesh, self.skeleton.world_from_local(local))
        moved = points - self.mesh.positions
        self.assertTrue(np.allclose(moved, np.tile([0.0, 2.0, 0.0], (3, 1)), atol=1e-5),
                        'a root move did not reach the vertices on its child')

    def test_parents_are_ordered_before_their_children(self):
        order = self.skeleton.order()
        placed = {}
        for slot, bone in enumerate(order):
            placed[bone] = slot
        for bone, parent in enumerate(self.skeleton.parents):
            if parent >= 0:
                self.assertLess(placed[parent], placed[bone])

    def test_a_rotation_is_about_the_bone_not_the_origin(self):
        """Rotating a bone must pivot the geometry around that bone's own
        position. Getting this wrong swings the model around the world origin,
        which looks like the rig exploding."""
        local = self.skeleton.bind_local.copy()
        angle = math.pi / 2
        turn = np.eye(4)
        turn[:3, :3] = [[math.cos(angle), -math.sin(angle), 0],
                        [math.sin(angle), math.cos(angle), 0], [0, 0, 1]]
        local[1] = local[1] @ turn
        points, _ = smdimport.skin(self.mesh, self.skeleton.world_from_local(local))
        bone_at = self.skeleton.bind_world[1][:3, 3]
        before = np.linalg.norm(self.mesh.positions - bone_at, axis=1)
        after = np.linalg.norm(points - bone_at, axis=1)
        np.testing.assert_allclose(before, after, atol=1e-5)


if __name__ == '__main__':
    unittest.main()
