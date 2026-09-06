"""PNG -> PS1 texture conversion and VRAM placement.

The PS1 stores textures in the same 1024x512 16-bit VRAM as the framebuffers, so
"loading a texture" really means deciding where in that grid it lives. This module
does the conversion and the placement; nc_tex.c on the console just uploads what
it is told.

VRAM map
--------
    (0,0)-(639,239)      the two 320x240 framebuffers
    (960,0)              the debug font
    y=256, x=slot*128    texture slots, 8 of them, 256x240 texels each
    x=0, y=496+slot      one 256-entry CLUT per slot, one row each

Rows 496..511 sit inside the same page band as the textures, which is why
textures are capped at 240 rows rather than 256 -- the last 16 rows are where the
palettes live.

Format
------
8-bit CLUT. Each texel is one byte indexing a 256-colour palette, so a VRAM cell
holds two texels and a 256-wide texture is 128 cells wide. 4-bit would be more
authentic and half the size again, but 8-bit avoids nibble packing and still
looks period-correct. Colours are BGR555.

Transparency
------------
The GPU skips any texel whose 16-bit value is exactly 0x0000. There is no alpha
channel -- transparency is that one reserved value, and nothing else.

So an image with alpha gets quantised to 255 colours instead of 256, every index
shifted up by one, palette entry 0 set to 0x0000, and transparent pixels pointed
at index 0. Opaque images use all 256 and have no transparent entry at all.

That is also why an opaque pure black has to be nudged: black is 0x0000, which
the hardware would read as a hole. Setting the top bit keeps it black and opaque.
"""

import os
import struct

MAX_SLOTS = 8
SLOT_CELL_WIDTH = 128          # 128 VRAM cells = 256 texels at 8bpp
TEX_VRAM_Y = 256
MAX_TEX_W = 256
MAX_TEX_H = 240                # 256 minus the 16 rows reserved for palettes
CLUT_VRAM_X = 0
CLUT_VRAM_Y = 496


class TextureError(Exception):
    pass


def to_bgr555(r, g, b):
    """Pack 8-bit RGB into the PS1's 16-bit BGR555.

    A stored value of 0x0000 means "fully transparent" on this hardware, so a
    pure black texel would punch a hole. Setting the top (semi-transparency)
    bit keeps it opaque while blending is off, which is what we want.
    """
    v = ((b >> 3) << 10) | ((g >> 3) << 5) | (r >> 3)
    if v == 0:
        v = 0x8000
    return v


ALPHA_THRESHOLD = 128          # below this a pixel becomes fully transparent


def convert(path, name):
    """Load an image and return (indices, palette, width, height)."""
    try:
        from PIL import Image
    except ImportError:
        raise TextureError(
            "Pillow is needed to convert textures. Install it with:\n"
            "         pip install Pillow")

    if not os.path.isfile(path):
        raise TextureError(f"texture '{name}': no such file: {path}")

    img = Image.open(path).convert("RGBA")
    w, h = img.size

    if w > MAX_TEX_W or h > MAX_TEX_H:
        raise TextureError(
            f"texture '{name}' is {w}x{h}; the limit is "
            f"{MAX_TEX_W}x{MAX_TEX_H}. Resize it, or split it up.")
    if w % 2:
        raise TextureError(
            f"texture '{name}' is {w} wide. Width must be even, because two "
            f"8-bit texels share one 16-bit VRAM cell.")
    if w == 0 or h == 0:
        raise TextureError(f"texture '{name}' is empty")

    alpha = img.getchannel("A")
    has_alpha = alpha.getextrema()[0] < ALPHA_THRESHOLD

    # Quantise with MEDIANCUT: it keeps flat, poster-like regions, which is
    # closer to how period art was authored than dithering everything.
    flat = img.convert("RGB")
    colors = 255 if has_alpha else 256
    pal_img = flat.quantize(colors=colors, method=Image.MEDIANCUT)

    indices = bytearray(pal_img.tobytes())
    raw_pal = pal_img.getpalette() or []

    palette = []
    if has_alpha:
        # Index 0 is the hole. Everything else shifts up to make room.
        palette.append(0x0000)
        alpha_bytes = alpha.tobytes()
        for i in range(len(indices)):
            indices[i] = 0 if alpha_bytes[i] < ALPHA_THRESHOLD else indices[i] + 1

    for i in range(colors):
        if i * 3 + 2 < len(raw_pal):
            palette.append(to_bgr555(raw_pal[i * 3], raw_pal[i * 3 + 1],
                                     raw_pal[i * 3 + 2]))
        else:
            palette.append(0x8000)
    while len(palette) < 256:
        palette.append(0x8000)

    if len(indices) != w * h:
        raise TextureError(
            f"texture '{name}': expected {w * h} bytes of index data, got "
            f"{len(indices)}")

    return bytes(indices), palette, w, h


def build_chunk(slot, indices, palette, w, h):
    """TEX0: where it goes in VRAM, then the pixels, then the palette."""
    if slot >= MAX_SLOTS:
        raise TextureError(
            f"more than {MAX_SLOTS} textures. Each needs its own VRAM slot.")

    vram_x = slot * SLOT_CELL_WIDTH
    out = bytearray()
    # slot, w, h, then the VRAM placement the runtime uploads to. Sending the
    # placement rather than recomputing it on the console keeps the layout rules
    # in exactly one place -- this file.
    out += struct.pack("<HHHH", slot, w, h, 0)
    out += struct.pack("<hhhh", vram_x, TEX_VRAM_Y, w // 2, h)
    out += struct.pack("<hhhh", CLUT_VRAM_X, CLUT_VRAM_Y + slot, 256, 1)
    out += indices
    if len(indices) % 4:
        out += b"\x00" * (4 - len(indices) % 4)   # keep the palette 4-aligned
    for entry in palette:
        out += struct.pack("<H", entry)
    return bytes(out)


def build(textures, base_dir):
    """Convert every texture in a scene document.

    Returns (chunks, name -> {"slot", "w", "h"}). The size matters downstream:
    UV coordinates address the whole 256x256 page, so a mesh using a 64x64
    texture must stop at 63, not 255, or it samples whatever is next to it in
    VRAM.
    """
    chunks = []
    slots = {}
    for slot, tex in enumerate(textures):
        name = tex.get("name") or f"tex{slot}"
        rel = tex.get("file")
        if not rel:
            raise TextureError(f"texture '{name}' has no 'file'")
        path = rel if os.path.isabs(rel) else os.path.join(base_dir, rel)
        indices, palette, w, h = convert(path, name)
        chunks.append(build_chunk(slot, indices, palette, w, h))
        slots[name] = {"slot": slot, "w": w, "h": h}
    return chunks, slots
