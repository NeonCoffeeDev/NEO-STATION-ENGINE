"""The ways a model arrives wrong, and whether the importer notices.

Every one of these is a real thing an exporter does, not a hypothetical. The
Cloud model that prompted the importer arrived with no normals at all and with
a tenth of its triangles built as double-sided cards, and both of those would
have produced a plausible-looking but wrong result rather than an error.
"""

import os
import tempfile
import unittest

import numpy as np

from ncc import meshimport


def write(directory, name, text):
    path = os.path.join(directory, name)
    with open(path, 'w', encoding='utf-8') as handle:
        handle.write(text)
    return path


class ObjTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.dir = self.temp.name

    def tearDown(self):
        self.temp.cleanup()

    def load(self, obj, mtl=None):
        if mtl is not None:
            write(self.dir, 'test.mtl', mtl)
        return meshimport.load_obj(write(self.dir, 'test.obj', obj))

    def test_a_quad_arrives_as_two_triangles(self):
        """OBJ allows n-gons and the hardware does not."""
        mesh = self.load(
            'v 0 0 0\nv 1 0 0\nv 1 1 0\nv 0 1 0\n'
            'vt 0 0\nvt 1 0\nvt 1 1\nvt 0 1\n'
            'usemtl wall\nf 1/1 2/2 3/3 4/4\n')
        self.assertEqual(mesh.triangle_count, 2)
        self.assertEqual(mesh.vertex_count, 4)

    def test_one_position_two_texture_coordinates_is_two_vertices(self):
        """OBJ indexes position and texture coordinate separately; the GS
        cannot, so the combination is the vertex."""
        mesh = self.load(
            'v 0 0 0\nv 1 0 0\nv 1 1 0\n'
            'vt 0 0\nvt 1 0\nvt 1 1\nvt 0.5 0.5\n'
            'f 1/1 2/2 3/3\nf 1/4 2/2 3/3\n')
        self.assertEqual(mesh.triangle_count, 2)
        # Position 1 appears with two different texture coordinates.
        self.assertEqual(mesh.vertex_count, 4)

    def test_the_same_vertex_twice_is_not_duplicated(self):
        mesh = self.load(
            'v 0 0 0\nv 1 0 0\nv 1 1 0\nv 0 1 0\n'
            'vt 0 0\nvt 1 0\nvt 1 1\nvt 0 1\n'
            'f 1/1 2/2 3/3\nf 1/1 3/3 4/4\n')
        self.assertEqual(mesh.triangle_count, 2)
        self.assertEqual(mesh.vertex_count, 4)

    def test_negative_indices_count_back_from_the_end(self):
        mesh = self.load('v 0 0 0\nv 1 0 0\nv 1 1 0\nf -3 -2 -1\n')
        self.assertEqual(mesh.triangle_count, 1)
        np.testing.assert_allclose(mesh.positions[0], [0, 0, 0], atol=1e-6)

    def test_missing_normals_are_generated_and_all_unit_length(self):
        mesh = self.load('v 0 0 0\nv 2 0 0\nv 0 2 0\nf 1 2 3\n')
        lengths = np.linalg.norm(mesh.normals, axis=1)
        np.testing.assert_allclose(lengths, 1.0, atol=1e-5)

    def test_a_double_sided_card_still_gets_a_normal(self):
        """The same triangle wound both ways sums to exactly zero.

        This is how every PlayStation 2 model builds hair, cloth and foliage,
        and a zero normal lights those surfaces black.
        """
        mesh = self.load('v 0 0 0\nv 2 0 0\nv 0 2 0\n'
                         'f 1 2 3\nf 3 2 1\n')
        lengths = np.linalg.norm(mesh.normals, axis=1)
        self.assertTrue((lengths > 0.9).all(),
                        'cancelled normals were left at zero: %s' % lengths)

    def test_normals_are_weighted_by_area(self):
        """A large face must not be outvoted by the slivers trimming its edge.

        A big triangle facing +Z and a sliver facing +Y share a vertex; the
        shared normal should lean heavily towards +Z.
        """
        mesh = self.load(
            'v 0 0 0\nv 10 0 0\nv 0 10 0\n'
            'v 0 0 0.01\n'
            'f 1 2 3\nf 1 2 4\n')
        shared = mesh.normals[0]
        self.assertGreater(abs(shared[2]), abs(shared[1]),
                           'the sliver outvoted the large face')

    def test_texture_coordinates_are_flipped_for_the_gs(self):
        """OBJ puts v=0 at the bottom of the image, the GS at the top."""
        mesh = self.load('v 0 0 0\nv 1 0 0\nv 1 1 0\n'
                         'vt 0 0\nvt 1 0\nvt 1 1\nf 1/1 2/2 3/3\n')
        self.assertAlmostEqual(float(mesh.uvs[0][1]), 1.0, places=5)

    def test_materials_group_their_triangles_together(self):
        """Every change of material is a texture bind, so the runs matter."""
        mesh = self.load(
            'mtllib test.mtl\n'
            'v 0 0 0\nv 1 0 0\nv 1 1 0\nv 2 2 2\n'
            'usemtl skin\nf 1 2 3\n'
            'usemtl cloth\nf 1 2 4\nf 1 3 4\n',
            'newmtl skin\nmap_Kd skin.png\nnewmtl cloth\nmap_Kd cloth.png\n')
        self.assertEqual([p.material for p in mesh.parts], ['skin', 'cloth'])
        self.assertEqual([p.count // 3 for p in mesh.parts], [1, 2])
        self.assertEqual(mesh.materials['skin'], 'skin.png')
        self.assertEqual(mesh.materials['cloth'], 'cloth.png')

    def test_map_kd_options_are_not_mistaken_for_the_filename(self):
        mesh = self.load(
            'mtllib test.mtl\nv 0 0 0\nv 1 0 0\nv 1 1 0\n'
            'usemtl skin\nf 1 2 3\n',
            'newmtl skin\nmap_Kd -s 1 1 1 -o 0 0 0 diffuse.png\n')
        self.assertEqual(mesh.materials['skin'], 'diffuse.png')

    def test_a_file_with_no_faces_is_refused(self):
        with self.assertRaises(meshimport.MeshError):
            self.load('v 0 0 0\nv 1 0 0\nv 1 1 0\n')

    def test_scaling_reports_what_it_did(self):
        mesh = self.load('v 0 0 0\nv 1 0 0\nv 0 224 0\nf 1 2 3\n')
        factor = mesh.scale_to_height(1.8)
        self.assertAlmostEqual(factor, 1.8 / 224.0, places=6)
        self.assertAlmostEqual(float(mesh.size()[1]), 1.8, places=4)

    def test_centring_puts_the_feet_on_the_floor(self):
        mesh = self.load('v -1 5 -1\nv 1 5 1\nv 0 9 0\nf 1 2 3\n')
        mesh.centre_on_floor()
        low, high = mesh.bounds()
        self.assertAlmostEqual(float(low[1]), 0.0, places=5)
        self.assertAlmostEqual(float(low[0] + high[0]), 0.0, places=5)


if __name__ == '__main__':
    unittest.main()
