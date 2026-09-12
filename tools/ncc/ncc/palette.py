"""Palettised textures: the reason any of this artwork fits on the console.

A 128x128 texture at 32 bits is 64 KB. The same texture as 4-bit indices into
a 16-colour table is 8 KB, and the table is 64 bytes. That is the difference
between a character needing 960 KB of graphics memory and needing 128 KB, and
on a machine with 4 MB of it -- most of which is already frame and depth
buffers -- it is not an optimisation. It is the whole reason the PlayStation 2
could show a textured character at all, and it is what every game of the era
did.

Two things here are easy to get wrong and produce a picture that is merely
odd rather than obviously broken:

Transparency. The engine's alpha test rejects anything at zero, which is how
cut-out artwork gets a hard edge without blending. So index 0 is reserved for
"transparent" and never handed to the quantiser, which costs one colour and
saves every cut-out texture from acquiring a halo.

And the 8-bit colour table is not stored in order. The GS reads a 256-entry
table with bits 3 and 4 of the index swapped, so writing the table in the
obvious order gives an image whose colours are shuffled in blocks of eight --
recognisable, wrong, and very hard to diagnose from a photograph of a
television. A 16-entry table has no such reordering.
"""

import numpy as np

from . import ps2budget

# What the GS calls these, and how many bits each index takes.
FORMATS = {4: 'PSMT4', 8: 'PSMT8'}

# Below this, a source pixel is transparent and gets index 0.
ALPHA_CUTOFF = 128


def clut_swizzle(entries):
    """Reorder a 256-entry colour table the way the GS reads it.

    CSM1 storage swaps bits 3 and 4 of the index, so entries 8..15 and 16..23
    trade places, and so on up the table. Skipping this does not corrupt the
    image -- it recolours it in bands of eight, which looks like a palette
    chosen by somebody else rather than like a bug.
    """
    if len(entries) != 256:
        return list(entries)
    out = [None] * 256
    for index in range(256):
        swapped = (index & ~0x18) | ((index & 0x08) << 1) | ((index & 0x10) >> 1)
        out[swapped] = entries[index]
    return out


def quantise(image, bits=4, dither=True):
    """An RGBA image as indices plus a colour table.

    Returns (indices, palette) where indices is a height x width array of
    uint8 and palette is a list of (r, g, b, a). Index 0 is transparent.
    """
    from PIL import Image
    if bits not in FORMATS:
        raise ValueError('palette textures are 4-bit or 8-bit, not %d' % bits)
    rgba = image.convert('RGBA')
    width, height = rgba.size
    source = np.asarray(rgba)
    clear = source[..., 3] < ALPHA_CUTOFF

    # Quantise the colour only. Feeding transparent pixels to the quantiser
    # spends table entries on colours nothing will ever show, and lets their
    # colour bleed into neighbours when the hardware filters.
    opaque = Image.fromarray(source[..., :3], 'RGB')
    if clear.any():
        # Transparent pixels take the average of the visible ones, so they
        # cannot pull a table entry towards a colour that is not in the art.
        visible = source[..., :3][~clear]
        filler = visible.reshape(-1, 3).mean(axis=0).astype(np.uint8) if len(visible) \
            else np.zeros(3, dtype=np.uint8)
        patched = source[..., :3].copy()
        patched[clear] = filler
        opaque = Image.fromarray(patched, 'RGB')

    # Index 0 is only spent on transparency when the picture has some. A
    # texture with no cut-out gets the whole table, which is the difference
    # between 255 and 256 colours -- and these textures were palettised when
    # the game shipped, so several of them land on exactly 256.
    reserve = bool(clear.any())
    usable = (1 << bits) - (1 if reserve else 0)
    reduced = opaque.quantize(colors=usable, method=Image.MEDIANCUT,
                              dither=Image.FLOYDSTEINBERG if dither else Image.NONE)
    # A copy, not a view: Pillow hands back read-only pixels.
    indices = np.array(reduced, dtype=np.uint8)
    # Pillow returns however many entries it actually needed, which can be
    # fewer than were asked for when the picture has less colour than that.
    raw = reduced.getpalette()[:usable * 3]
    palette = [(0, 0, 0, 0)] if reserve else []
    if reserve:
        indices = indices + 1
    for entry in range(len(raw) // 3):
        palette.append((raw[entry * 3], raw[entry * 3 + 1], raw[entry * 3 + 2], 0x80))
    indices[clear] = 0
    while len(palette) < (1 << bits):
        palette.append((0, 0, 0, 0))
    return indices, palette


def to_image(indices, palette):
    """What the console will actually show, for looking at before committing."""
    from PIL import Image
    table = np.array([[c[0], c[1], c[2], 255 if c[3] else 0] for c in palette],
                     dtype=np.uint8)
    return Image.fromarray(table[indices], 'RGBA')


def pack(indices, bits):
    """Index bytes in the order the GS expects to receive them.

    4-bit indices are two to a byte, low nibble first.
    """
    flat = np.asarray(indices, dtype=np.uint8).reshape(-1)
    if bits == 8:
        return flat.tobytes()
    if len(flat) % 2:
        flat = np.append(flat, np.uint8(0))
    low = flat[0::2] & 0x0F
    high = flat[1::2] & 0x0F
    return ((high << 4) | low).astype(np.uint8).tobytes()


def clut_bytes(palette, bits):
    """The colour table as GS_PSM_32 texels, swizzled if it needs to be."""
    entries = clut_swizzle(palette) if bits == 8 else list(palette)
    out = bytearray()
    for r, g, b, a in entries:
        out += bytes((r & 0xFF, g & 0xFF, b & 0xFF, a & 0xFF))
    return bytes(out)


def cost(width, height, bits):
    """Graphics memory for the indices and the table, in bytes.

    The table is small but not free: it lives in graphics memory too, and it
    is allocated in 256-byte blocks like everything else.
    """
    pixels = ps2budget.cost(ps2budget.pow2(width), ps2budget.pow2(height),
                            FORMATS[bits])
    entries = 1 << bits
    table = max(256, ((entries * 4) + 255) // 256 * 256)
    return pixels + table


def compare(image, name=''):
    """What this texture costs at each depth, for deciding with numbers."""
    width, height = image.size
    padded = (ps2budget.pow2(width), ps2budget.pow2(height))
    rows = []
    full = ps2budget.cost(padded[0], padded[1], 'PSMCT32')
    rows.append(('32-bit', full))
    rows.append(('16-bit', ps2budget.cost(padded[0], padded[1], 'PSMCT16')))
    for bits in (8, 4):
        rows.append(('%d-bit palette' % bits, cost(width, height, bits)))
    return rows
