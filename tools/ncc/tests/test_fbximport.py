"""The binary FBX reader, checked against files this test builds itself.

FBX has no specification, so the only honest way to test a reader for it is to
write the container by hand and assert that what comes back is what went in.
The writer here is deliberately dumb -- it exists to produce known bytes, not
to be a good FBX writer -- and that is what makes a failure point at the
reader.
"""

import os
import struct
import tempfile
import unittest
import zlib

import numpy as np

from ncc import fbximport
from ncc.meshimport import MeshError


# ---- a minimal FBX writer, for making fixtures ------------------------

def prop_int32(value):
    return b'I' + struct.pack('<i', value)


def prop_double(value):
    return b'D' + struct.pack('<d', value)


def prop_string(text):
    raw = text.encode('utf-8')
    return b'S' + struct.pack('<I', len(raw)) + raw


def prop_int64(value):
    return b'L' + struct.pack('<q', value)


def prop_array(code, values, compress=False):
    dtype = {'d': '<d', 'i': '<i'}[code]
    raw = np.asarray(values, dtype=np.dtype(dtype)).tobytes()
    if compress:
        packed = zlib.compress(raw)
        return (code.encode() + struct.pack('<III', len(values), 1, len(packed))
                + packed)
    return code.encode() + struct.pack('<III', len(values), 0, len(raw)) + raw


def node(name, props=(), children=()):
    """Returns a function of `start offset` so EndOffset can be filled in."""
    def build(start):
        body = b''.join(props)
        raw_name = name.encode('utf-8')
        header_size = 13
        child_bytes = b''
        cursor = start + header_size + len(raw_name) + len(body)
        for child in children:
            piece = child(cursor)
            child_bytes += piece
            cursor += len(piece)
        if children:
            child_bytes += b'\x00' * 13          # the null terminator record
            cursor += 13
        end = cursor
        return (struct.pack('<IIIB', end, len(props), len(body), len(raw_name))
                + raw_name + body + child_bytes)
    return build


def write_fbx(path, roots):
    header = b'Kaydara FBX Binary  \x00' + b'\x1a\x00' + struct.pack('<I', 7400)
    out = header
    cursor = len(header)
    for root in roots:
        piece = root(cursor)
        out += piece
        cursor += len(piece)
    out += b'\x00' * 13
    with open(path, 'wb') as handle:
        handle.write(out)
    return path


def triangle_document(compress=False, uv=True, material=True, extra=()):
    """One triangle, one material, one texture -- the smallest real scene."""
    geometry = node('Geometry', [prop_int64(100), prop_string('Geo'), prop_string('Mesh')], [
        node('Vertices', [prop_array('d', [0, 0, 0, 2, 0, 0, 0, 2, 0], compress)]),
        # The last index of a polygon is stored bitwise-negated. That marker is
        # the only thing separating one polygon from the next.
        node('PolygonVertexIndex', [prop_array('i', [0, 1, ~2], compress)]),
    ] + ([node('LayerElementUV', [prop_int32(0)], [
        node('MappingInformationType', [prop_string('ByPolygonVertex')]),
        node('ReferenceInformationType', [prop_string('IndexToDirect')]),
        node('UV', [prop_array('d', [0, 0, 1, 0, 1, 1], compress)]),
        node('UVIndex', [prop_array('i', [0, 1, 2], compress)]),
    ])] if uv else []) + ([node('LayerElementMaterial', [prop_int32(0)], [
        node('MappingInformationType', [prop_string('AllSame')]),
        node('ReferenceInformationType', [prop_string('IndexToDirect')]),
        node('Materials', [prop_array('i', [0], compress)]),
    ])] if material else []))

    model = node('Model', [prop_int64(200), prop_string('Box'), prop_string('Mesh')], [
        node('Properties70', [], [
            node('P', [prop_string('Lcl Translation'), prop_string('Lcl Translation'),
                       prop_string(''), prop_string('A'),
                       prop_double(10.0), prop_double(0.0), prop_double(0.0)]),
        ]),
    ])

    objects = node('Objects', [], [
        geometry, model,
        node('Material', [prop_int64(300), prop_string('brick'), prop_string('')]),
        node('Texture', [prop_int64(400), prop_string('tex'), prop_string('')], [
            node('RelativeFilename', [prop_string('wall.png')]),
        ]),
    ] + list(extra))
    connections = node('Connections', [], [
        node('C', [prop_string('OO'), prop_int64(100), prop_int64(200)]),
        node('C', [prop_string('OO'), prop_int64(300), prop_int64(200)]),
        node('C', [prop_string('OP'), prop_int64(400), prop_int64(300)]),
    ])
    return [objects, connections]


class ContainerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.temp.name, 'test.fbx')

    def tearDown(self):
        self.temp.cleanup()

    def test_a_file_that_is_not_fbx_is_refused_with_advice(self):
        with open(self.path, 'wb') as handle:
            handle.write(b'; FBX 7.4.0 project file\n')
        with self.assertRaises(MeshError) as caught:
            fbximport.parse(self.path)
        self.assertIn('OBJ', str(caught.exception))

    def test_the_record_tree_round_trips(self):
        write_fbx(self.path, triangle_document())
        root = fbximport.parse(self.path)
        self.assertEqual(root.props[0], 7400)
        names = [child.name for child in root.children]
        self.assertIn('Objects', names)
        self.assertIn('Connections', names)
        objects = root.children[names.index('Objects')]
        self.assertEqual(len(objects.find_all('Geometry')), 1)
        self.assertEqual(len(objects.find_all('Material')), 1)

    def test_compressed_arrays_read_the_same_as_raw_ones(self):
        """Array properties may be zlib-deflated, and usually are."""
        write_fbx(self.path, triangle_document(compress=False))
        plain = fbximport.load_fbx(self.path)
        write_fbx(self.path, triangle_document(compress=True))
        packed = fbximport.load_fbx(self.path)
        np.testing.assert_allclose(plain.positions, packed.positions, atol=1e-6)
        self.assertEqual(plain.triangle_count, packed.triangle_count)


class GeometryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.temp.name, 'test.fbx')
        write_fbx(self.path, triangle_document())
        self.mesh = fbximport.load_fbx(self.path)

    def tearDown(self):
        self.temp.cleanup()

    def test_the_negated_last_index_closes_the_polygon(self):
        """Getting this wrong makes the whole file one broken face."""
        self.assertEqual(self.mesh.triangle_count, 1)
        self.assertEqual(len(self.mesh.indices), 3)

    def test_the_model_transform_is_applied(self):
        """Geometry alone is at the origin; the Model says where it goes.

        Skipping this stacks an entire environment on top of itself.
        """
        low, high = self.mesh.bounds()
        self.assertAlmostEqual(float(low[0]), 10.0, places=4)
        self.assertAlmostEqual(float(high[0]), 12.0, places=4)

    def test_texture_coordinates_are_flipped_for_the_gs(self):
        self.assertAlmostEqual(float(self.mesh.uvs[0][1]), 1.0, places=5)

    def test_the_material_is_named_and_carries_its_texture(self):
        self.assertEqual([p.material for p in self.mesh.parts], ['brick'])
        self.assertEqual(self.mesh.materials['brick'], 'wall.png')

    def test_missing_normals_are_generated(self):
        lengths = np.linalg.norm(self.mesh.normals, axis=1)
        np.testing.assert_allclose(lengths, 1.0, atol=1e-5)


class EmbeddedTextureTests(unittest.TestCase):
    def test_a_texture_stored_inside_the_file_is_written_out(self):
        """FBX can carry its artwork as raw bytes, and artists rely on it."""
        temp = tempfile.TemporaryDirectory()
        try:
            path = os.path.join(temp.name, 'test.fbx')
            payload = b'\x89PNG\r\n\x1a\n' + b'pretend pixels'
            video = node('Video', [prop_int64(500), prop_string('vid'),
                                   prop_string('Clip')], [
                node('RelativeFilename', [prop_string('embedded.png')]),
                node('Content', [b'R' + struct.pack('<I', len(payload)) + payload]),
            ])
            write_fbx(path, triangle_document(extra=[video]))
            out = os.path.join(temp.name, 'out')
            root = fbximport.parse(path)
            written = fbximport.extract_embedded(root, path, out)
            self.assertIn('embedded.png', written)
            with open(written['embedded.png'], 'rb') as handle:
                self.assertEqual(handle.read(), payload)
        finally:
            temp.cleanup()


if __name__ == '__main__':
    unittest.main()
