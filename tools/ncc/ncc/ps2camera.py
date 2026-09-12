"""One description of how a PlayStation 2 camera projects.

NC Studio's viewport and the console's renderer have to agree about what the
camera sees, or the editor is a lie -- and they disagreed for a long time in a
way nobody could see by looking, because a horizontal mirror still looks like a
plausible picture. The fix is not to write the same formula carefully in two
places. It is to write it once here, have Studio call it, and have a test read
the C in nc_world3d.h and check it evaluates to the same numbers.

Two things in here are easy to get backwards, so they are spelled out:

The handedness. Looking down +Z, +X is to the right. Building the right vector
as cross(forward, up) puts it on the left, which is what the viewport used to
do.

The pixels. A 640x448 buffer is stretched onto a 4:3 television, so the picture
is squeezed horizontally on the way out -- 640/448 is 1.4286 and the screen is
1.3333. The console draws 1/0.9333 wider in buffer pixels to cancel it. The
editor draws into a plain 4:3 rectangle and needs no correction of its own,
which is why the factor appears here only in ps2_pixels().
"""

import math

# Buffer pixels per unit of square picture. Only the console needs it; see above.
PIXEL_ASPECT = 1.0714286

SCREEN = (640, 448)


def _sub(a, b):
    return [a[i] - b[i] for i in range(3)]


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a, b):
    return [a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0]]


def _unit(v):
    length = math.sqrt(_dot(v, v))
    return [c / length for c in v] if length else [0.0, 0.0, 1.0]


def basis(pos, target):
    """Forward, right and up, in the handedness the console renders."""
    forward = _unit(_sub(target, pos))
    right = _unit(_cross([0.0, 1.0, 0.0], forward))
    up = _unit(_cross(forward, right))
    return forward, right, up


def view(pos, target, point):
    """A world point in camera space: how far right, how far up, how far away."""
    forward, right, up = basis(pos, target)
    delta = _sub(point, pos)
    return _dot(delta, right), _dot(delta, up), _dot(delta, forward)


def focal_length(fov_degrees, height):
    """Distance from the eye to a picture `height` tall at this field of view."""
    return (height * 0.5) / math.tan(math.radians(fov_degrees) * 0.5)


def project(pos, target, fov, point, rect, near=0.3):
    """Where a world point lands inside a 4:3 rectangle on screen.

    `rect` is (left, top, width, height) in whatever units the caller draws in;
    the console passes its own buffer, Studio passes a letterboxed region of
    the canvas. Returns None for anything at or behind the near plane, because
    a point behind the eye projects to a perfectly plausible wrong place.
    """
    right, up, depth = view(pos, target, point)
    if depth < near:
        return None
    left, top, width, height = rect
    focal = focal_length(fov, height)
    return (left + width * 0.5 + right * focal / depth,
            top + height * 0.5 - up * focal / depth,
            depth)


def ps2_pixels(pos, target, fov, point, screen=SCREEN, near=0.3):
    """Where a world point lands in the console's frame buffer.

    Offsets from the centre of the buffer, which is what the runtime adds to
    the GS's 2048 origin. This is the one place the non-square pixel
    correction belongs.
    """
    right, up, depth = view(pos, target, point)
    if depth < near:
        return None
    focal = focal_length(fov, screen[1])
    return right * focal * PIXEL_ASPECT / depth, -up * focal / depth, depth


def letterbox(width, height):
    """The largest 4:3 rectangle centred in a width x height area.

    A camera view is a television, not a window. Filling the pane instead
    would mean the framing chosen in the editor changes whenever the docks are
    dragged around.
    """
    tall = min(float(height), width * 3.0 / 4.0)
    wide = tall * 4.0 / 3.0
    return (width - wide) * 0.5, (height - tall) * 0.5, wide, tall
