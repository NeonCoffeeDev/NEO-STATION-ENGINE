/*
 * Neon Coffee - 2D collision and gravity
 *
 * Axis-aligned boxes, moved one axis at a time. That is not a simplification
 * for its own sake: resolving X and Y together is what makes a character catch
 * on the seam between two floor tiles, and separating them is the standard fix.
 * Move in X, push out of anything you are now inside; then the same in Y. The
 * result is that walking into a wall stops you horizontally and leaves your
 * vertical motion alone, which is what "slide" means here.
 *
 * What this is not: there is no sub-stepping, so a sprite moving faster than a
 * wall is thick will pass through it in a single frame. On a machine with no
 * FPU and a 33 MHz CPU, sweeping every mover against every solid every frame is
 * a cost with a real frame-rate price, and the games this is for do not need
 * it. Keep speeds below your wall thickness.
 *
 * Positions stay whole pixels because that is what the GPU draws. Velocity is
 * 20.12 fixed point -- 4096 is one pixel per frame -- and the remainder is
 * carried in the sprite, so half a pixel per frame moves you one pixel every
 * other frame instead of rounding to nothing.
 */

#include "nc.h"

#define ONE_PX 4096

/* Defaults chosen against a 32-pixel character at 60 Hz: about a third of a
 * pixel of acceleration per frame, and a fall that tops out at six pixels a
 * frame -- fast enough to feel weighty, slow enough not to tunnel through a
 * 16-pixel platform. */
static int gravity = 1400;
static int terminal = 6 * ONE_PX;


void nc_phys_set_gravity(int g)
{
    gravity = g;
}


void nc_phys_set_terminal(int v)
{
    terminal = v;
}


/* Collision uses the sprite's box, not its drawn rectangle. Art has margins:
 * a 16-pixel character in a 32-pixel cell would otherwise stop seven pixels
 * short of every wall, which reads as broken collision rather than as padding.
 */
static int box_l(const NC_Sprite *s) { return s->x + s->bx; }
static int box_t(const NC_Sprite *s) { return s->y + s->by; }
static int box_r(const NC_Sprite *s) { return s->x + s->bx + s->bw; }
static int box_b(const NC_Sprite *s) { return s->y + s->by + s->bh; }


static int boxes_overlap(const NC_Sprite *a, const NC_Sprite *b)
{
    /* Touching edges do not count as overlapping. If they did, a character
     * resting exactly on a platform would be considered inside it and get
     * pushed out again every frame. */
    if (box_r(a) <= box_l(b)) return 0;
    if (box_r(b) <= box_l(a)) return 0;
    if (box_b(a) <= box_t(b)) return 0;
    if (box_b(b) <= box_t(a)) return 0;
    return 1;
}


int nc_phys_overlap(int ai, int bi)
{
    const NC_Sprite *a = nc_scene_sprite(ai);
    const NC_Sprite *b = nc_scene_sprite(bi);
    if (!a || !b)
        return 0;
    return boxes_overlap(a, b);
}


/* Move one axis and push back out of whatever we ended up inside.
 *
 * Snapping to the blocker's edge rather than stepping back a pixel at a time is
 * what keeps this cheap, and it is also what makes the result exact: you end up
 * flush against the wall regardless of how fast you were going.
 */
static int resolve_axis(int index, NC_Sprite *sp, int dx, int dy)
{
    int count = nc_scene_sprite_count();
    int hit = 0;
    int i;

    if (dx == 0 && dy == 0)
        return 0;

    sp->x += dx;
    sp->y += dy;

    for (i = 0; i < count; i++) {
        NC_Sprite *other;

        if (i == index)
            continue;
        other = nc_scene_sprite(i);
        if (!other || !other->solid || !other->visible)
            continue;
        if (!boxes_overlap(sp, other))
            continue;

        /* Snap so the boxes are flush, then convert back to a sprite position
         * by removing the box offset. */
        if (dx > 0) {
            sp->x = box_l(other) - sp->bx - sp->bw;
            hit |= NC_TOUCH_RIGHT;
        } else if (dx < 0) {
            sp->x = box_r(other) - sp->bx;
            hit |= NC_TOUCH_LEFT;
        } else if (dy > 0) {
            sp->y = box_t(other) - sp->by - sp->bh;
            hit |= NC_TOUCH_FLOOR;
        } else {
            sp->y = box_b(other) - sp->by;
            hit |= NC_TOUCH_CEILING;
        }
    }

    return hit;
}


/* Is there solid ground directly under us?
 *
 * This has to be a separate test rather than something the move reports, and
 * the reason is worth stating: standing still, gravity adds a fraction of a
 * pixel per frame, the sprite does not actually move, nothing is collided with,
 * and a floor flag set only by collisions would flicker off. A character that
 * is "on the ground" every other frame cannot jump reliably.
 *
 * One pixel of tolerance, because resolution leaves the sprite flush at gap
 * zero but a script that nudged it by hand may be a pixel clear.
 */
static int grounded(int index, const NC_Sprite *sp)
{
    int count = nc_scene_sprite_count();
    int i;

    for (i = 0; i < count; i++) {
        const NC_Sprite *o;
        int gap;

        if (i == index)
            continue;
        o = nc_scene_sprite(i);
        if (!o || !o->solid || !o->visible)
            continue;
        if (box_r(sp) <= box_l(o) || box_r(o) <= box_l(sp))
            continue;                       /* no horizontal overlap */

        gap = box_t(o) - box_b(sp);
        if (gap >= 0 && gap <= 1)
            return 1;
    }
    return 0;
}


int nc_phys_move(int index, int dx, int dy)
{
    NC_Sprite *sp = nc_scene_sprite(index);
    int hit;

    if (!sp)
        return 0;

    hit = resolve_axis(index, sp, dx, 0);
    hit |= resolve_axis(index, sp, 0, dy);

    /* Not while moving up: a sprite that has just jumped is still flush with
     * the ground on that first frame, and reporting a floor there would let a
     * script jump again out of mid-air. */
    if (sp->vy >= 0 && grounded(index, sp))
        hit |= NC_TOUCH_FLOOR;

    sp->touch = hit;
    return hit;
}


int nc_phys_step(int index)
{
    NC_Sprite *sp = nc_scene_sprite(index);
    int dx, dy, hit;

    if (!sp)
        return 0;

    sp->vy += gravity;
    if (sp->vy > terminal)
        sp->vy = terminal;

    /* Carry the fractional part across frames rather than truncating it away.
     * Without this, any speed under one pixel per frame is simply zero. */
    sp->sub_x += sp->vx;
    sp->sub_y += sp->vy;

    dx = sp->sub_x / ONE_PX;
    dy = sp->sub_y / ONE_PX;
    sp->sub_x -= dx * ONE_PX;
    sp->sub_y -= dy * ONE_PX;

    hit = nc_phys_move(index, dx, dy);

    /* Landing or hitting your head ends the fall. Leaving vy alone would let it
     * grow all the way to terminal while standing still, so the first step off
     * a ledge would drop like a stone.
     *
     * Only downward speed is cancelled on the floor -- zeroing it outright
     * would eat a jump on the frame it starts. */
    if (hit & NC_TOUCH_CEILING) {
        sp->vy = 0;
        sp->sub_y = 0;
    }
    if ((hit & NC_TOUCH_FLOOR) && sp->vy > 0) {
        sp->vy = 0;
        sp->sub_y = 0;
    }
    if (hit & (NC_TOUCH_LEFT | NC_TOUCH_RIGHT)) {
        sp->vx = 0;
        sp->sub_x = 0;
    }

    return hit;
}
