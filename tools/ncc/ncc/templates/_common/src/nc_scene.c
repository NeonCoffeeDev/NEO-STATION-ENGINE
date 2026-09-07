/*
 * Neon Coffee - the live scene
 *
 * The package is read-only data embedded in the executable, but scripts need to
 * move things around. So loading a scene copies its instances into a mutable
 * array here. The package stays the pristine original, which is what makes
 * restarting a scene a single memcpy rather than bookkeeping.
 *
 * Camera state lives here too, because each scene brings its own.
 */

#include <stdio.h>

#include "nc.h"

static const NC_Package *loaded;
static NC_Object objects[NC_MAX_OBJECTS];
static int object_count;

static NC_Sprite sprites[NC_MAX_SPRITES];
static int sprite_count;

static int scene_index;
static int pending_scene = -1;

static VECTOR  cam_pos;
static SVECTOR cam_rot;

/* The 2D view offset. Sprites live in world coordinates and this is subtracted
 * as they are drawn, so a level can be larger than the screen without collision
 * or script logic ever knowing the view moved. */
static int scroll_x, scroll_y;


int nc_scene_load(const NC_Package *pkg, int index)
{
    const NC_Scene *sc;
    int i, n;

    if (pkg == 0 || index < 0 || index >= pkg->scene_count) {
        printf("nc_scene: no scene %d (package has %d)\n",
               index, pkg ? pkg->scene_count : 0);
        return 0;
    }

    loaded = pkg;
    scene_index = index;
    pending_scene = -1;
    sc = &pkg->scenes[index];

    n = sc->instance_count;
    if (n > NC_MAX_OBJECTS) {
        printf("nc_scene: scene %d has %d objects, capping at %d\n",
               index, n, NC_MAX_OBJECTS);
        n = NC_MAX_OBJECTS;
    }

    for (i = 0; i < n; i++) {
        const NC_Instance *in = &sc->instances[i];
        NC_Object *o = &objects[i];
        o->mesh_id = in->mesh_id;
        o->px = in->px;  o->py = in->py;  o->pz = in->pz;
        o->rx = in->rx;  o->ry = in->ry;  o->rz = in->rz;
        o->sx = in->sx;  o->sy = in->sy;  o->sz = in->sz;
        o->visible = 1;
    }
    object_count = n;

    n = sc->sprite_count;
    if (n > NC_MAX_SPRITES) {
        printf("nc_scene: scene %d has %d sprites, capping at %d\n",
               index, n, NC_MAX_SPRITES);
        n = NC_MAX_SPRITES;
    }
    for (i = 0; i < n; i++) {
        const NC_SpriteDef *sd = &sc->sprites[i];
        NC_Sprite *sp = &sprites[i];
        sp->x = sd->x;  sp->y = sd->y;
        sp->w = sd->w;  sp->h = sd->h;
        sp->u = sd->u;  sp->v = sd->v;
        sp->visible = 1;
        sp->fixed = (sd->flags & NC_SPRITE_FIXED) ? 1 : 0;
        sp->solid = (sd->flags & NC_SPRITE_SOLID) ? 1 : 0;
        sp->flip = 0;
        sp->bx = sd->bx;  sp->by = sd->by;
        sp->bw = sd->bw;  sp->bh = sd->bh;
        /* Physics state is per-run, not per-package: reloading a scene should
         * put a character back where it started, standing still. */
        sp->vx = sp->vy = 0;
        sp->sub_x = sp->sub_y = 0;
        sp->touch = 0;
        if (sd->tex_slot < NC_MAX_TEXTURES) {
            sp->tpage = pkg->textures[sd->tex_slot].tpage;
            sp->clut = pkg->textures[sd->tex_slot].clut;
        } else {
            sp->visible = 0;      /* references a texture that is not there */
        }
    }
    sprite_count = n;

    cam_pos = sc->cam_pos;
    cam_rot = sc->cam_rot;
    scroll_x = scroll_y = 0;      /* a new scene starts at the origin */
    nc_gfx_set_clear(sc->clear_r, sc->clear_g, sc->clear_b);

    return 1;
}


void nc_scene_advance(void)
{
    int i;
    for (i = 0; i < object_count; i++) {
        NC_Object *o = &objects[i];
        /* Rotation is a 16-bit angle where 4096 is a full turn, so letting it
         * run past 4096 is harmless -- RotMatrix wraps it for us. */
        o->rx += o->sx;
        o->ry += o->sy;
        o->rz += o->sz;
    }
}


void nc_scene_draw(void)
{
    SVECTOR rot;
    VECTOR pos;
    int i;

    nc_camera_set(&cam_pos, &cam_rot);

    for (i = 0; i < object_count; i++) {
        const NC_Object *o = &objects[i];

        if (!o->visible)
            continue;
        if (loaded == 0 || o->mesh_id < 0 || o->mesh_id >= loaded->mesh_count)
            continue;                    /* scene referenced a missing mesh */

        rot.vx = (short)o->rx;
        rot.vy = (short)o->ry;
        rot.vz = (short)o->rz;
        rot.pad = 0;

        pos.vx = o->px;
        pos.vy = o->py;
        pos.vz = o->pz;

        nc_mesh_draw(&loaded->meshes[o->mesh_id], &rot, &pos);
    }

    /* Sprites last: they are screen-space, so they need no camera and simply
     * sit in front of whatever the 3D pass produced. */
    for (i = 0; i < sprite_count; i++) {
        const NC_Sprite *sp = &sprites[i];
        int x = sp->x, y = sp->y;
        if (!sp->visible)
            continue;
        /* World to screen. Fixed sprites are exempt, which is what keeps a HUD
         * and side panels still while the world slides underneath them. */
        if (!sp->fixed) {
            x -= scroll_x;
            y -= scroll_y;
        }
        nc_sprite_draw(sp->tpage, sp->clut, x, y, sp->w, sp->h,
                       sp->u, sp->v, sp->fixed, sp->flip);
    }
}


int nc_scene_sprite_count(void)
{
    return sprite_count;
}


NC_Sprite *nc_scene_sprite(int i)
{
    if (i < 0 || i >= sprite_count)
        return 0;
    return &sprites[i];
}


int nc_scene_object_count(void)
{
    return object_count;
}


NC_Object *nc_scene_object(int i)
{
    if (i < 0 || i >= object_count)
        return 0;
    return &objects[i];
}


int nc_scene_index(void)
{
    return scene_index;
}


int nc_scene_total(void)
{
    return loaded ? loaded->scene_count : 0;
}


void nc_scene_request(int index)
{
    pending_scene = index;
}


int nc_scene_take_request(void)
{
    int p = pending_scene;
    pending_scene = -1;
    return p;
}


void nc_scene_camera_set(int x, int y, int z, int rx, int ry, int rz)
{
    cam_pos.vx = x;   cam_pos.vy = y;   cam_pos.vz = z;
    cam_rot.vx = (short)rx;
    cam_rot.vy = (short)ry;
    cam_rot.vz = (short)rz;
    cam_rot.pad = 0;
}


void nc_scene_camera_move(int dx, int dy, int dz)
{
    cam_pos.vx += dx;
    cam_pos.vy += dy;
    cam_pos.vz += dz;
}


int nc_scene_camera_get(int axis)
{
    switch (axis) {
    case 0: return cam_pos.vx;
    case 1: return cam_pos.vy;
    case 2: return cam_pos.vz;
    case 3: return cam_rot.vy;
    default: return 0;
    }
}


void nc_scene_set_clear(int r, int g, int b)
{
    nc_gfx_set_clear(r, g, b);
}


/* ---- the 2D view -------------------------------------------------------- */

void nc_scroll_set(int x, int y)
{
    scroll_x = x;
    scroll_y = y;
}


void nc_scroll_by(int dx, int dy)
{
    scroll_x += dx;
    scroll_y += dy;
}


int nc_scroll_x(void) { return scroll_x; }
int nc_scroll_y(void) { return scroll_y; }


void nc_scroll_follow(int index, int dead_w, int dead_h)
{
    const NC_Sprite *sp = nc_scene_sprite(index);
    int cx, cy, half_w, half_h, want_x, want_y;

    if (!sp)
        return;

    /* Where the sprite sits on screen right now, and how far it is allowed to
     * stray from the middle before the view starts moving. Tracking exactly is
     * nauseating to play; a dead zone is what makes it feel like a camera
     * rather than like the world being dragged. */
    cx = sp->x + sp->w / 2 - scroll_x;
    cy = sp->y + sp->h / 2 - scroll_y;
    half_w = dead_w / 2;
    half_h = dead_h / 2;

    want_x = NC_SCREEN_W / 2;
    want_y = NC_SCREEN_H / 2;

    if (cx > want_x + half_w)
        scroll_x += cx - (want_x + half_w);
    else if (cx < want_x - half_w)
        scroll_x -= (want_x - half_w) - cx;

    if (cy > want_y + half_h)
        scroll_y += cy - (want_y + half_h);
    else if (cy < want_y - half_h)
        scroll_y -= (want_y - half_h) - cy;
}
