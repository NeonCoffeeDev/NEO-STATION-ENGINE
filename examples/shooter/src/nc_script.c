/*
 * Neon Coffee - implementation of the NCScript API.
 *
 * Thin wrappers over the engine. They exist so scripts get a small, stable,
 * hard-to-misuse surface: every id is bounds-checked, so a script that indexes
 * a missing object does nothing instead of corrupting memory. On a machine with
 * no MMU that difference is the difference between a bug and a lockup.
 *
 * Every function returns int, even the ones with nothing to say, so the
 * transpiler can emit any call as an expression without special cases.
 */

#include <stdio.h>

#include "nc_script.h"

static int current_frame;
static unsigned long rng_state = 0x13579BDF;


void nc_script_set_frame(int f)
{
    current_frame = f;
}


/* --- output --- */

void nc_s_print(const char *msg)
{
    printf("%s\n", msg);
}


void nc_s_print_num(int value)
{
    printf("%d\n", value);
}


int nc_s_draw_text(int x, int y, const char *msg)
{
    nc_text(x, y, msg);
    return 0;
}


int nc_s_draw_num(int x, int y, int value)
{
    /* A fixed buffer, because there is no allocator here and a 32-bit int
     * never needs more than 11 characters plus a terminator. */
    char buf[16];
    sprintf(buf, "%d", value);
    nc_text(x, y, buf);
    return 0;
}


/* --- sound --- */

int nc_s_play_sound(int id)
{
    nc_audio_play(id);
    return 0;
}


int nc_s_sound_count(void)
{
    return nc_audio_count();
}


/* --- input --- */

int nc_s_btn_held(int button)
{
    return nc_held((uint16_t)button);
}


int nc_s_btn_pressed(int button)
{
    return nc_pressed((uint16_t)button);
}


/* --- objects --- */

int nc_s_count(void)
{
    return nc_scene_object_count();
}


int nc_s_get_x(int id)
{
    NC_Object *o = nc_scene_object(id);
    return o ? o->px : 0;
}


int nc_s_get_y(int id)
{
    NC_Object *o = nc_scene_object(id);
    return o ? o->py : 0;
}


int nc_s_get_z(int id)
{
    NC_Object *o = nc_scene_object(id);
    return o ? o->pz : 0;
}


int nc_s_set_pos(int id, int x, int y, int z)
{
    NC_Object *o = nc_scene_object(id);
    if (o) {
        o->px = x;
        o->py = y;
        o->pz = z;
    }
    return 0;
}


int nc_s_move(int id, int dx, int dy, int dz)
{
    NC_Object *o = nc_scene_object(id);
    if (o) {
        o->px += dx;
        o->py += dy;
        o->pz += dz;
    }
    return 0;
}


int nc_s_set_rot(int id, int x, int y, int z)
{
    NC_Object *o = nc_scene_object(id);
    if (o) {
        o->rx = x;
        o->ry = y;
        o->rz = z;
    }
    return 0;
}


int nc_s_spin(int id, int x, int y, int z)
{
    NC_Object *o = nc_scene_object(id);
    if (o) {
        o->sx = x;
        o->sy = y;
        o->sz = z;
    }
    return 0;
}


int nc_s_show(int id)
{
    NC_Object *o = nc_scene_object(id);
    if (o)
        o->visible = 1;
    return 0;
}


int nc_s_hide(int id)
{
    NC_Object *o = nc_scene_object(id);
    if (o)
        o->visible = 0;
    return 0;
}


/* --- sprites --- */

int nc_s_sprite_count(void)
{
    return nc_scene_sprite_count();
}


int nc_s_sprite_x(int id)
{
    NC_Sprite *sp = nc_scene_sprite(id);
    return sp ? sp->x : 0;
}


int nc_s_sprite_y(int id)
{
    NC_Sprite *sp = nc_scene_sprite(id);
    return sp ? sp->y : 0;
}


int nc_s_sprite_set_pos(int id, int x, int y)
{
    NC_Sprite *sp = nc_scene_sprite(id);
    if (sp) {
        sp->x = x;
        sp->y = y;
    }
    return 0;
}


int nc_s_sprite_move(int id, int dx, int dy)
{
    NC_Sprite *sp = nc_scene_sprite(id);
    if (sp) {
        sp->x += dx;
        sp->y += dy;
    }
    return 0;
}


int nc_s_sprite_frame(int id, int u, int v)
{
    /* Move the window into the texture. This is how animation works: lay the
     * frames out in one image and step u across them. */
    NC_Sprite *sp = nc_scene_sprite(id);
    if (sp) {
        sp->u = u & 0xFF;
        sp->v = v & 0xFF;
    }
    return 0;
}


int nc_s_sprite_show(int id)
{
    NC_Sprite *sp = nc_scene_sprite(id);
    if (sp)
        sp->visible = 1;
    return 0;
}


int nc_s_sprite_hide(int id)
{
    NC_Sprite *sp = nc_scene_sprite(id);
    if (sp)
        sp->visible = 0;
    return 0;
}


/* --- camera --- */

int nc_s_camera_set(int x, int y, int z, int rx, int ry, int rz)
{
    nc_scene_camera_set(x, y, z, rx, ry, rz);
    return 0;
}


int nc_s_camera_move(int dx, int dy, int dz)
{
    nc_scene_camera_move(dx, dy, dz);
    return 0;
}


int nc_s_camera_turn(int d)
{
    nc_scene_camera_set(nc_scene_camera_get(0), nc_scene_camera_get(1),
                        nc_scene_camera_get(2), 0,
                        nc_scene_camera_get(3) + d, 0);
    return 0;
}


int nc_s_camera_x(void)   { return nc_scene_camera_get(0); }
int nc_s_camera_y(void)   { return nc_scene_camera_get(1); }
int nc_s_camera_z(void)   { return nc_scene_camera_get(2); }
int nc_s_camera_yaw(void) { return nc_scene_camera_get(3); }


/* --- scenes --- */

int nc_s_goto_scene(int index)
{
    /* Deferred: main.c picks this up at the end of the frame, so a script can
     * call it mid-update without the objects changing under its feet. */
    nc_scene_request(index);
    return 0;
}


int nc_s_scene(void)
{
    return nc_scene_index();
}


int nc_s_scene_count(void)
{
    return nc_scene_total();
}


/* --- misc --- */

int nc_s_frame(void)
{
    return current_frame;
}


int nc_s_set_clear(int r, int g, int b)
{
    nc_scene_set_clear(r, g, b);
    return 0;
}


int nc_s_abs(int v)
{
    return v < 0 ? -v : v;
}


int nc_s_min(int a, int b)
{
    return a < b ? a : b;
}


int nc_s_max(int a, int b)
{
    return a > b ? a : b;
}


int nc_s_clamp(int v, int lo, int hi)
{
    if (v < lo) return lo;
    if (v > hi) return hi;
    return v;
}


int nc_s_rand(int n)
{
    /* A plain linear congruential generator. Not good randomness, but it needs
     * no division and no state beyond a word, which is the right trade here. */
    rng_state = rng_state * 1103515245UL + 12345UL;
    if (n <= 0)
        return 0;
    return (int)((rng_state >> 16) % (unsigned long)n);
}


/* Scripts use angles where 4096 is a full turn, matching rotations. isin()
 * wants 131072 for a full turn, hence the shift. Keeping the script-facing
 * unit consistent avoids the single most common mix-up in this codebase. */
int nc_s_sin(int angle)
{
    return isin((angle << 5) & 131071);
}


int nc_s_cos(int angle)
{
    return icos((angle << 5) & 131071);
}
