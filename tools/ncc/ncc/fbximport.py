"""Read a binary FBX and hand back the same Mesh the OBJ importer produces.

FBX is what Blender, Maya and most level editors export when someone wants a
whole environment rather than one object, so an engine that cannot read it
cannot take a scene from anybody. It is also a format with no specification,
which is why this is a parser rather than a call into a library: there is no
library here to call, and adding a dependency to read one file type is a poor
trade for a toolchain that currently needs nothing but Pillow and numpy.

The file is a tree of records. Each carries the offset of its own end, a list
of typed properties, and any children, so it can be walked without knowing what
any of the node names mean. Array properties may be zlib-compressed, which is
why a five megabyte file holds rather more than five megabytes of geometry.

What has to be understood, rather than merely walked:

Polygons are stored as a flat run of vertex indices where the *last* index of
each polygon is stored bitwise-negated. That is the only marker of where one
polygon ends and the next begins, and it is why a naive reader produces one
enormous broken face.

Normals, texture coordinates and material assignments each arrive with their
own mapping and reference mode -- per vertex or per polygon-vertex, direct or
through a second index array. Guessing at these produces geometry that looks
right and is shaded or textured wrongly.

And which material a face uses is not stored with the face. It is a number into
a list built from the file's Connections section, which is a flat pile of
parent/child id pairs for the entire document.
"""

import os
import struct
import zlib

import numpy as np

from .meshimport import Mesh, MeshError, Part


class Node:
    __slots__ = ('name', 'props', 'children')

    def __init__(self, name, props, children):
        self.name = name
        self.props = props
        self.children = children

    def find(self, name):
        for child in self.children:
            if child.name == name:
                return child
        return None

    def find_all(self, name):
        return [child for child in self.children if child.name == name]

    def __repr__(self):
        return 'Node(%s, %d props, %d children)' % (
            self.name, len(self.props), len(self.children))


# ---- the container ----------------------------------------------------

_ARRAY_TYPES = {'f': ('f', 4), 'd': ('d', 8), 'l': ('q', 8),
                'i': ('i', 4), 'b': ('b', 1)}
_SCALAR_TYPES = {'Y': ('h', 2), 'C': ('?', 1), 'I': ('i', 4),
                 'F': ('f', 4), 'D': ('d', 8), 'L': ('q', 8)}


def _read_property(data, pos):
    kind = chr(data[pos])
    pos += 1
    if kind in _SCALAR_TYPES:
        code, size = _SCALAR_TYPES[kind]
        value = struct.unpack_from('<' + code, data, pos)[0]
        return value, pos + size
    if kind in _ARRAY_TYPES:
        code, size = _ARRAY_TYPES[kind]
        length, encoding, compressed = struct.unpack_from('<III', data, pos)
        pos += 12
        raw = data[pos:pos + compressed]
        pos += compressed
        if encoding:
            raw = zlib.decompress(raw)
        return np.frombuffer(raw, dtype=np.dtype('<' + code), count=length), pos
    if kind in 'SR':
        length = struct.unpack_from('<I', data, pos)[0]
        pos += 4
        raw = data[pos:pos + length]
        pos += length
        return (raw.decode('utf-8', 'replace') if kind == 'S' else raw), pos
    raise MeshError('FBX: unknown property type %r' % kind)


def _read_node(data, pos, wide):
    header = '<QQQB' if wide else '<IIIB'
    header_size = struct.calcsize(header)
    end, count, props_len, name_len = struct.unpack_from(header, data, pos)
    pos += header_size
    if end == 0:
        return None, pos
    name = data[pos:pos + name_len].decode('utf-8', 'replace')
    pos += name_len
    props = []
    after_props = pos + props_len
    for _ in range(count):
        value, pos = _read_property(data, pos)
        props.append(value)
    pos = after_props
    children = []
    while pos + header_size < end:
        child, pos = _read_node(data, pos, wide)
        if child is None:
            break
        children.append(child)
    return Node(name, props, children), end


def parse(path):
    """The whole document as a tree of Nodes."""
    with open(path, 'rb') as handle:
        data = handle.read()
    if not data.startswith(b'Kaydara FBX Binary'):
        raise MeshError('%s is not a binary FBX. Export it as binary, or as OBJ.'
                        % os.path.basename(path))
    version = struct.unpack_from('<I', data, 23)[0]
    # 7500 widened every offset in the file from 32 to 64 bits.
    wide = version >= 7500
    pos = 27
    roots = []
    while pos + (25 if wide else 13) < len(data):
        node, pos = _read_node(data, pos, wide)
        if node is None:
            break
        roots.append(node)
    return Node('root', [version], roots)


# ---- making sense of it -----------------------------------------------

def _layer(geometry, element, values_name, index_name):
    """One layer element, resolved through its mapping and reference modes."""
    node = geometry.find(element)
    if node is None:
        return None, None, None
    values = node.find(values_name)
    index = node.find(index_name)
    mapping = node.find('MappingInformationType')
    reference = node.find('ReferenceInformationType')
    return (np.asarray(values.props[0]) if values and values.props else None,
            np.asarray(index.props[0]) if index and index.props else None,
            (mapping.props[0] if mapping and mapping.props else 'ByPolygonVertex',
             reference.props[0] if reference and reference.props else 'Direct'))


def _connections(root):
    """child id -> [parent id], from the document-wide Connections pile."""
    links = {}
    section = None
    for node in root.children:
        if node.name == 'Connections':
            section = node
            break
    if section is None:
        return links
    for link in section.find_all('C'):
        if len(link.props) >= 3:
            child, parent = int(link.props[1]), int(link.props[2])
            links.setdefault(child, []).append(parent)
    return links


def _prop70(node, name, default):
    """One value out of a Properties70 block, which is FBX's property bag."""
    block = node.find('Properties70')
    if block is None:
        return default
    for entry in block.children:
        if entry.props and str(entry.props[0]) == name:
            tail = [v for v in entry.props[4:]]
            return tail if tail else default
    return default


def _euler(degrees):
    """FBX rotations are XYZ Euler in degrees, applied X then Y then Z."""
    ax, ay, az = [float(v) * np.pi / 180.0 for v in degrees]
    cx, sx = np.cos(ax), np.sin(ax)
    cy, sy = np.cos(ay), np.sin(ay)
    cz, sz = np.cos(az), np.sin(az)
    rx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]], dtype=np.float64)
    ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]], dtype=np.float64)
    rz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]], dtype=np.float64)
    return rz @ ry @ rx


def _local_matrix(model):
    """A Model's own translate/rotate/scale as a 4x4.

    Ignoring these is what puts an entire environment on top of itself at the
    origin: an FBX scene is hundreds of small meshes whose only placement is
    the transform on the Model that owns each one.
    """
    translation = _prop70(model, 'Lcl Translation', [0.0, 0.0, 0.0])
    rotation = _prop70(model, 'Lcl Rotation', [0.0, 0.0, 0.0])
    scaling = _prop70(model, 'Lcl Scaling', [1.0, 1.0, 1.0])
    pre = _prop70(model, 'PreRotation', None)
    basis = _euler(rotation)
    if pre:
        basis = _euler(pre) @ basis
    basis = basis @ np.diag([float(v) for v in scaling])
    matrix = np.eye(4)
    matrix[:3, :3] = basis
    matrix[:3, 3] = [float(v) for v in translation]
    return matrix


def _geometric_matrix(model):
    """The extra offset FBX allows between a Model and its Geometry."""
    translation = _prop70(model, 'GeometricTranslation', [0.0, 0.0, 0.0])
    rotation = _prop70(model, 'GeometricRotation', [0.0, 0.0, 0.0])
    scaling = _prop70(model, 'GeometricScaling', [1.0, 1.0, 1.0])
    matrix = np.eye(4)
    matrix[:3, :3] = _euler(rotation) @ np.diag([float(v) for v in scaling])
    matrix[:3, 3] = [float(v) for v in translation]
    return matrix


def _objects(root):
    section = None
    for node in root.children:
        if node.name == 'Objects':
            section = node
            break
    return section


def extract_embedded(root, path, out_dir=None):
    """Write out textures stored inside the file itself.

    An FBX can carry its textures as raw bytes in a Video node, and this one
    does -- 1.8 MB of PNG. A model whose artwork travels with it is the whole
    reason artists send FBX rather than OBJ plus a folder, so refusing to look
    inside means refusing half of what people will hand the engine.
    """
    objects = _objects(root)
    if objects is None:
        return {}
    out_dir = out_dir or os.path.join(os.path.dirname(os.path.abspath(path)),
                                      os.path.splitext(os.path.basename(path))[0] + '.fbm')
    written = {}
    for video in objects.find_all('Video'):
        content = video.find('Content')
        if content is None or not content.props or not len(content.props[0]):
            continue
        relative = video.find('RelativeFilename') or video.find('FileName')
        name = os.path.basename(str(relative.props[0]).replace(chr(92), '/'))             if relative and relative.props else 'texture%d.png' % len(written)
        os.makedirs(out_dir, exist_ok=True)
        target = os.path.join(out_dir, name)
        blob = content.props[0]
        if not isinstance(blob, (bytes, bytearray)):
            blob = bytes(blob)
        with open(target, 'wb') as handle:
            handle.write(blob)
        written[name] = target
    return written


def load_fbx(path, merge=True, texture_dir=None):
    """Read every mesh in an FBX into one Mesh, with a part per material."""
    root = parse(path)
    objects = _objects(root)
    if objects is None:
        raise MeshError('%s has no Objects section' % os.path.basename(path))

    links = _connections(root)

    # Models carry the placement; geometry on its own is all at the origin.
    models = {}
    for node in objects.find_all('Model'):
        if node.props:
            models[int(node.props[0])] = node

    def world_of(model_id, seen=None):
        """A Model's transform with its parents applied, root-most first."""
        seen = seen or set()
        if model_id in seen or model_id not in models:
            return np.eye(4)
        seen.add(model_id)
        matrix = _local_matrix(models[model_id])
        for parent in links.get(model_id, []):
            if parent in models:
                return world_of(parent, seen) @ matrix
        return matrix

    # id -> name, for materials and textures.
    materials = {}
    textures = {}
    for node in objects.find_all('Material'):
        if node.props:
            name = node.props[1] if len(node.props) > 1 else ''
            materials[int(node.props[0])] = str(name).split('\x00')[0] or 'material'
    for node in objects.find_all('Texture'):
        if not node.props:
            continue
        relative = node.find('RelativeFilename') or node.find('FileName')
        if relative and relative.props:
            textures[int(node.props[0])] = str(relative.props[0]).replace('\\', '/')

    # material id -> texture path, through whichever texture connects to it.
    material_texture = {}
    for texture_id, filename in textures.items():
        for parent in links.get(texture_id, []):
            if parent in materials:
                material_texture.setdefault(parent, os.path.basename(filename))

    out_pos, out_uv, out_nrm, indices = [], [], [], []
    runs = {}
    unified = {}

    for geometry in objects.find_all('Geometry'):
        verts_node = geometry.find('Vertices')
        polys_node = geometry.find('PolygonVertexIndex')
        if verts_node is None or polys_node is None:
            continue
        positions = np.asarray(verts_node.props[0], dtype=np.float64).reshape(-1, 3)
        polygons = np.asarray(polys_node.props[0], dtype=np.int64)

        normals, normal_index, normal_mode = _layer(
            geometry, 'LayerElementNormal', 'Normals', 'NormalsIndex')
        uvs, uv_index, uv_mode = _layer(
            geometry, 'LayerElementUV', 'UV', 'UVIndex')
        mats, _, mat_mode = _layer(
            geometry, 'LayerElementMaterial', 'Materials', 'MaterialsIndex')
        if normals is not None:
            normals = normals.reshape(-1, 3)
        if uvs is not None:
            uvs = uvs.reshape(-1, 2)

        # Which materials this geometry can reach, in connection order. A face's
        # material number is an index into this, not a document-wide id.
        geometry_id = int(geometry.props[0]) if geometry.props else None

        # Place it. The Model that owns this geometry supplies the transform,
        # and its own parents supply theirs.
        placement = np.eye(4)
        for parent in links.get(geometry_id, []):
            if parent in models:
                placement = world_of(parent) @ _geometric_matrix(models[parent])
                break
        positions = (positions @ placement[:3, :3].T) + placement[:3, 3]
        rotation_only = placement[:3, :3]
        scale_length = np.linalg.norm(rotation_only, axis=0)
        scale_length[scale_length < 1e-9] = 1.0
        normal_matrix = rotation_only / scale_length

        reachable = []
        for parent in links.get(geometry_id, []):
            for grandparent in links.get(parent, []):
                pass
            for other, parents in links.items():
                if other in materials and parent in parents:
                    if other not in reachable:
                        reachable.append(other)
        if not reachable:
            reachable = sorted(materials)

        polygon = 0
        corner_start = 0
        for corner in range(len(polygons)):
            raw = int(polygons[corner])
            if raw >= 0:
                continue
            # A negative index is the last corner of this polygon, negated.
            corners = list(range(corner_start, corner + 1))
            face = []
            for slot in corners:
                value = int(polygons[slot])
                vertex = ~value if value < 0 else value

                if normals is None:
                    normal = (0.0, 0.0, 0.0)
                elif normal_mode[0].startswith('ByPolygonVertex'):
                    at = int(normal_index[slot]) if (normal_index is not None
                                                     and normal_mode[1] != 'Direct') else slot
                    normal = tuple(normals[at]) if at < len(normals) else (0.0, 0.0, 0.0)
                else:
                    at = int(normal_index[vertex]) if (normal_index is not None
                                                       and normal_mode[1] != 'Direct') else vertex
                    normal = tuple(normals[at]) if at < len(normals) else (0.0, 0.0, 0.0)
                if normal != (0.0, 0.0, 0.0):
                    normal = tuple(normal_matrix @ np.asarray(normal))

                if uvs is None:
                    uv = (0.0, 0.0)
                elif uv_index is not None:
                    at = int(uv_index[slot])
                    uv = tuple(uvs[at]) if 0 <= at < len(uvs) else (0.0, 0.0)
                else:
                    at = slot if uv_mode[0].startswith('ByPolygonVertex') else vertex
                    uv = tuple(uvs[at]) if at < len(uvs) else (0.0, 0.0)

                key = (id(geometry), vertex, uv, normal)
                slot_index = unified.get(key)
                if slot_index is None:
                    slot_index = len(out_pos)
                    unified[key] = slot_index
                    out_pos.append(positions[vertex])
                    # FBX puts v=0 at the bottom of the image; the GS at the top.
                    out_uv.append((uv[0], 1.0 - uv[1]))
                    out_nrm.append(normal)
                face.append(slot_index)

            if mats is None or len(mats) == 0:
                material_id = reachable[0] if reachable else None
            elif mat_mode[0] == 'AllSame':
                pick = int(mats[0])
                material_id = reachable[pick] if pick < len(reachable) else None
            else:
                pick = int(mats[polygon]) if polygon < len(mats) else 0
                material_id = reachable[pick] if pick < len(reachable) else None
            name = materials.get(material_id, 'default')

            run = runs.setdefault(name, [])
            for i in range(1, len(face) - 1):
                run.extend((face[0], face[i], face[i + 1]))

            polygon += 1
            corner_start = corner + 1

    if not runs:
        raise MeshError('%s has no polygons this importer could read'
                        % os.path.basename(path))

    mesh = Mesh()
    mesh.source = path
    mesh.positions = np.asarray(out_pos, dtype=np.float32).reshape(-1, 3)
    mesh.uvs = np.asarray(out_uv, dtype=np.float32).reshape(-1, 2)
    mesh.normals = np.asarray(out_nrm, dtype=np.float32).reshape(-1, 3)
    for name, run in runs.items():
        first = len(indices)
        indices.extend(run)
        mesh.parts.append(Part(name, first, len(run)))
    mesh.indices = np.asarray(indices, dtype=np.int32)
    # Textures carried inside the file are written out and referred to by
    # absolute path, so nothing depends on a sidecar folder existing.
    embedded = extract_embedded(root, path, texture_dir)
    resolved = {}
    for material_id, name in materials.items():
        texture = material_texture.get(material_id)
        if texture and texture in embedded:
            resolved[name] = embedded[texture]
        else:
            resolved[name] = texture
    mesh.materials = resolved
    if not mesh.normals.any():
        mesh.generate_normals()
    else:
        length = np.linalg.norm(mesh.normals, axis=1, keepdims=True)
        length[length < 1e-9] = 1.0
        mesh.normals = (mesh.normals / length).astype(np.float32)
    return mesh
