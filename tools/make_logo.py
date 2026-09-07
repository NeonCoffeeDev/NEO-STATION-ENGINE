"""Render the Neon Coffee logo at any size.

The mark is a coffee mug drawn as an outline: a rounded-square body with a
handle on the left, stroked in a magenta-to-blue gradient and edged in black.

It is generated rather than stored as one fixed PNG because it has to exist at
several sizes for several machines -- a 512px master for the tools, a 128px
power-of-two texture for the PS2 -- and rescaling a bitmap logo makes the black
edging go grey and furry. Drawing it at the size you need keeps the edges crisp.

    python tools/make_logo.py out.png 512

Everything is supersampled 4x and downsampled once at the end, which is what
gives clean diagonals without a real vector renderer.
"""

import sys

SS = 4                      # supersampling factor

# The gradient, left to right. Magenta into purple into blue, which is the
# order the handle and body read in.
STOPS = [
    (0.00, (0xFF, 0x00, 0xC8)),
    (0.38, (0xA0, 0x00, 0xF5)),
    (0.62, (0x6A, 0x2C, 0xF0)),
    (1.00, (0x00, 0xAE, 0xFF)),
]


def _gradient_colour(t):
    """Colour at 0..1 across the mark."""
    t = max(0.0, min(1.0, t))
    for i in range(len(STOPS) - 1):
        t0, c0 = STOPS[i]
        t1, c1 = STOPS[i + 1]
        if t0 <= t <= t1:
            f = 0.0 if t1 == t0 else (t - t0) / (t1 - t0)
            return tuple(int(round(c0[k] + (c1[k] - c0[k]) * f)) for k in range(3))
    return STOPS[-1][1]


def _shapes(draw, size, stroke):
    """Stroke the mug into a mask image at the given line width."""
    s = float(size)

    # Body: a rounded square occupying the right two thirds.
    left, top = 0.315 * s, 0.045 * s
    right, bottom = 0.955 * s, 0.955 * s
    radius = 0.10 * s
    draw.rounded_rectangle([left, top, right, bottom], radius=radius,
                           outline=255, width=int(round(stroke)))

    # Handle: a half circle whose centre sits INSIDE the body stroke, so its
    # two ends finish underneath it. Ending them on the body's outer edge
    # instead leaves a hairline gap that the black rim then widens into a
    # visible notch.
    cx, cy = 0.355 * s, 0.50 * s
    r = 0.275 * s
    draw.arc([cx - r, cy - r, cx + r, cy + r], start=90, end=270,
             fill=255, width=int(round(stroke)))


def render(size):
    from PIL import Image, ImageDraw

    big = size * SS
    stroke = 0.070 * big
    edge = max(2.0, 0.010 * big)          # the black rim, on both sides

    # Two masks: the black rim is the same shape drawn fatter, and the gradient
    # sits inside it. Drawing them in that order is what puts a line on both
    # edges of the stroke rather than only the outside.
    outer = Image.new("L", (big, big), 0)
    _shapes(ImageDraw.Draw(outer), big, stroke + edge * 2)

    inner = Image.new("L", (big, big), 0)
    _shapes(ImageDraw.Draw(inner), big, stroke)

    gradient = Image.new("RGB", (big, 1))
    px = gradient.load()
    for x in range(big):
        px[x, 0] = _gradient_colour(x / float(big - 1))
    gradient = gradient.resize((big, big))

    out = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    out.paste((0, 0, 0, 255), (0, 0), outer)
    out.paste(gradient, (0, 0), inner)

    return out.resize((size, size), Image.LANCZOS)


def main(argv):
    out = argv[1] if len(argv) > 1 else "logo.png"
    size = int(argv[2]) if len(argv) > 2 else 512
    render(size).save(out)
    print("Wrote %s (%dx%d)" % (out, size, size))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
