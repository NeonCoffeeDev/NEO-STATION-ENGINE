# .ncpkg format — v0 (DRAFT)

The contract between `ncc` and the runtimes. This is the one piece worth designing
carefully, because both sides depend on it and changing it later is expensive.

Status: **v1 shipped and in use.** The writer is `tools/ncc/ncc/ncpkg.py`, the
reader is `nc_pkg.c` in every generated project. They must change together; the
version field exists so a stale package fails loudly instead of drawing garbage.

Two things changed from the draft once the runtime was real:

- **Chunks align to 8, not 2048.** The 2048 figure was for reading whole CD
  sectors. The package is currently *embedded in the executable* rather than
  streamed off the disc, so sector alignment only wasted RAM. 8 is what the GTE's
  32-bit loads need. When streaming arrives, this goes back up.
- **Normals are computed by the writer**, not authored, from quad winding order.

## Principles

- **Little-endian.** Both MIPS targets run LE. No byte swapping anywhere.
- **Load in place.** The runtime `memcpy`s a chunk to its final home, or reads it
  straight into VRAM. No parsing, no allocation, no pointer fixups at load time.
  Offsets are relative to the chunk, so a chunk is position-independent.
- **2048-byte alignment.** Chunks start on CD sector boundaries so a chunk is a whole
  number of sector reads. On PS1 the CD is the bottleneck; this is not premature.
- **Fixed-point on the wire.** Vertices ship as 16-bit integers. The PS1 has no FPU
  and float-to-fixed conversion at load time is wasted CD-blocked time.

## Container

```
offset  size  field
0x00    4     magic       'N','C','P','K'
0x04    2     version     0
0x06    2     target      0=any 1=ps1 2=ps2
0x08    4     total_size  bytes, whole file
0x0C    4     chunk_count
0x10    ...   chunk_count x ChunkEntry (16 bytes each)
        ...   padding to 2048
        ...   chunk payloads, each 2048-aligned
```

```
ChunkEntry (16 bytes)
0x00    4     fourcc
0x04    4     offset      from start of file, 2048-aligned
0x08    4     size        payload bytes, unpadded
0x0C    4     id          per-type index, referenced by other chunks
```

## Chunk types

| fourcc | Contents                                                        |
|--------|-----------------------------------------------------------------|
| `TEX0` | Texture: raw 4/8/16-bit pixel data, plus its VRAM placement      |
| `CLUT` | Palette, 16 or 256 entries of 16-bit BGR555                      |
| `MESH` | Vertices, faces, per-face material/texture refs                  |
| `ANIM` | Keyframes, fixed-point                                           |
| `SND0` | Audio, SPU-ADPCM on PS1                                          |
| `SCN0` | Scene graph: node list, transforms, mesh refs, spawn data        |
| `STRT` | Startup config: first scene, screen mode, budgets                |

Cross-references are by `id`, never by file offset — a chunk can be rebuilt or moved
without touching the chunks that point at it.

## MESH v0

```
Header
0x00    2     vertex_count
0x02    2     face_count
0x04    2     flags        bit0 textured, bit1 gouraud, bit2 skinned
0x06    2     _pad
0x08    ...   vertex_count x Vertex
        ...   face_count x Face
```

`Vertex` — 8 bytes. `int16 x, y, z` then `int16 _pad`. The pad is not waste: the PS1's
`SVECTOR` is 8 bytes and the GTE loads it as one aligned quantity.

`Face` — indices as `uint16`, plus texture id, CLUT id, and UVs. Triangles and quads
are both native on PS1; the compiler emits quads where it can, because one quad is
cheaper than two triangles through the GPU.

## Open questions

- Does `SCN0` hold collision, or does that become its own `COLL` chunk?
- Skeletal animation on PS1: bake to vertex keyframes, or run joints on the GTE?
  Answer this from the runtime, after profiling.
- Streaming: does a `.ncpkg` map to one level, or is there an index of many?
