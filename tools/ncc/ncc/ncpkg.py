"""Writer for the .ncpkg container -- the contract between the tools and the runtime.

A scene authored anywhere (Godot, a script, a hand-written JSON file) is reduced to
this, and the PS1 runtime renders it without a line of game-specific C.

Design notes, and where this departs from the original draft in docs/NCPKG.md:

- The draft aligned chunks to 2048 so each was a whole number of CD sectors. The
  runtime currently *embeds* the package in the executable rather than streaming it
  off the disc, so sector alignment buys nothing and only wastes RAM. Chunks are
  aligned to 8 instead, which is what the GTE's 32-bit loads need for SVECTOR data.
  When streaming arrives, the alignment goes back up.

- Everything is little-endian and laid out so the runtime can point straight into the
  blob. Nothing is parsed, allocated or byte-swapped at load time.

- Face normals are computed here rather than authored. Getting them wrong is the
  classic way to end up with a mesh that is lit inside out, and the exporter already
  knows the winding order.
"""

import json
import struct

MAGIC = b"NCPK"
VERSION = 1
TARGET_PS1 = 1

HEADER = struct.Struct("<4sHHII")          # magic, version, target, count, total
ENTRY = struct.Struct("<4sIII")            # fourcc, offset, size, id
CHUNK_ALIGN = 8

ONE = 4096                                  # 1.0 in 20.12 fixed point


class NcpkgError(Exception):
    pass


# ---- geometry helpers ---------------------------------------------------

def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0])


def face_normal(verts, quad):
    """Outward normal for a quad, as a 20.12 fixed-point vector.

    Uses the first three corners. Winding order decides the direction, which is
    also what decides whether backface culling keeps the face -- so a mesh whose
    normals look inverted almost always has its winding reversed, not its normals.
    """
    p0, p1, p2 = (verts[quad[0]], verts[quad[1]], verts[quad[2]])
    n = _cross(_sub(p1, p0), _sub(p2, p0))
    length = (n[0] * n[0] + n[1] * n[1] + n[2] * n[2]) ** 0.5
    if length == 0:
        return (0, 0, 0)                    # degenerate face; leave it unlit
    return tuple(int(round(c / length * ONE)) for c in n)


def _clamp_short(v, what):
    if not -32768 <= v <= 32767:
        raise NcpkgError(f"{what} out of range for a 16-bit value: {v}")
    return v


# ---- chunk builders -----------------------------------------------------

def build_mesh(mesh):
    """MESH: vertex positions, one normal per quad, then the quad indices."""
    verts = mesh["verts"]
    quads = mesh["quads"]
    name = mesh.get("name", "?")

    if not verts or not quads:
        raise NcpkgError(f"mesh '{name}' has no geometry")
    if len(verts) > 65535 or len(quads) > 65535:
        raise NcpkgError(f"mesh '{name}' exceeds 65535 vertices or quads")

    for q in quads:
        if len(q) != 4:
            raise NcpkgError(
                f"mesh '{name}': every face must be a quad (got {len(q)} indices). "
                f"Triangles should be emitted as a quad with the last index repeated.")
        for i in q:
            if not 0 <= i < len(verts):
                raise NcpkgError(f"mesh '{name}': face index {i} out of range")

    out = bytearray()
    out += struct.pack("<HHHH", len(verts), len(quads), 0, 0)
    for v in verts:
        out += struct.pack("<hhhh",
                           _clamp_short(int(v[0]), f"mesh '{name}' vertex x"),
                           _clamp_short(int(v[1]), f"mesh '{name}' vertex y"),
                           _clamp_short(int(v[2]), f"mesh '{name}' vertex z"), 0)
    for q in quads:
        n = face_normal(verts, q)
        out += struct.pack("<hhhh", n[0], n[1], n[2], 0)
    for q in quads:
        out += struct.pack("<HHHH", *q)
    return bytes(out)


def build_scene(scene, mesh_ids):
    """SCN0: clear color plus a flat list of instances."""
    clear = scene.get("clear", [24, 16, 48])
    instances = scene.get("instances", [])
    if len(instances) > 65535:
        raise NcpkgError("more than 65535 instances")

    out = bytearray()
    out += struct.pack("<HHBBBB", len(instances), 0,
                       int(clear[0]) & 0xFF, int(clear[1]) & 0xFF,
                       int(clear[2]) & 0xFF, 0)

    for n, inst in enumerate(instances):
        mesh = inst.get("mesh", 0)
        if isinstance(mesh, str):
            if mesh not in mesh_ids:
                raise NcpkgError(f"instance {n} references unknown mesh '{mesh}'")
            mesh = mesh_ids[mesh]
        if not 0 <= mesh < len(mesh_ids):
            raise NcpkgError(f"instance {n} references mesh id {mesh}, which does "
                             f"not exist")

        pos = inst.get("pos", [0, 0, 450])
        rot = inst.get("rot", [0, 0, 0])
        spin = inst.get("spin", [0, 0, 0])

        out += struct.pack(
            "<HH3i3h3h2h", mesh, 0,
            int(pos[0]), int(pos[1]), int(pos[2]),
            _clamp_short(int(rot[0]), "rotation x"),
            _clamp_short(int(rot[1]), "rotation y"),
            _clamp_short(int(rot[2]), "rotation z"),
            _clamp_short(int(spin[0]), "spin x"),
            _clamp_short(int(spin[1]), "spin y"),
            _clamp_short(int(spin[2]), "spin z"),
            0, 0)
    return bytes(out)


# ---- container ----------------------------------------------------------

def pack(scene):
    """Turn a scene dict into .ncpkg bytes."""
    meshes = scene.get("meshes", [])
    if not meshes:
        raise NcpkgError("scene has no meshes")

    mesh_ids = {}
    chunks = []
    for i, mesh in enumerate(meshes):
        if "name" in mesh:
            mesh_ids[mesh["name"]] = i
        chunks.append((b"MESH", i, build_mesh(mesh)))
    chunks.append((b"SCN0", 0, build_scene(scene, mesh_ids or list(range(len(meshes))))))

    # Header, then the table, then payloads -- so offsets need the table size first.
    table_size = ENTRY.size * len(chunks)
    cursor = HEADER.size + table_size
    cursor += (-cursor) % CHUNK_ALIGN

    entries = []
    payloads = []
    for fourcc, cid, data in chunks:
        entries.append((fourcc, cursor, len(data), cid))
        payloads.append((cursor, data))
        cursor += len(data)
        cursor += (-cursor) % CHUNK_ALIGN

    total = cursor
    out = bytearray(total)
    HEADER.pack_into(out, 0, MAGIC, VERSION, TARGET_PS1, len(chunks), total)
    for n, e in enumerate(entries):
        ENTRY.pack_into(out, HEADER.size + n * ENTRY.size, *e)
    for offset, data in payloads:
        out[offset:offset + len(data)] = data
    return bytes(out)


def pack_file(scene_path, out_path):
    with open(scene_path, encoding="utf-8") as fh:
        scene = json.load(fh)
    data = pack(scene)
    with open(out_path, "wb") as fh:
        fh.write(data)
    return len(data), len(scene.get("meshes", [])), len(scene.get("instances", []))
