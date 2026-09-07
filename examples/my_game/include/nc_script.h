/*
 * Neon Coffee - the API available to NCScript.
 *
 * Your script is transpiled to C at build time and compiled natively, so calling
 * these costs exactly what calling a C function costs. Nothing is interpreted.
 *
 * The list here must match tools/ncc/ncc/ncscript_api.py. If they drift apart
 * the build fails at link time, which is the right place to find out.
 */

#ifndef NC_SCRIPT_H
#define NC_SCRIPT_H

#include "nc.h"

/* Array access, bounds-checked.
 *
 * There is no MMU on this machine: an out-of-range write does not fault, it
 * quietly corrupts whatever happens to be next in memory and the console locks
 * up somewhere unrelated minutes later. So a bad index reads as 0 and writes
 * nowhere -- the same forgiving rule the object and sprite calls follow.
 *
 * At -O2 these inline to a compare and a branch.
 */
static inline int nc_arr_get(const int *a, int n, int i)
{
    return (i >= 0 && i < n) ? a[i] : 0;
}

static inline void nc_arr_set(int *a, int n, int i, int v)
{
    if (i >= 0 && i < n)
        a[i] = v;
}

/* Implemented by your script (or stubbed out by the transpiler if you did not
 * define them). */
void nc_script_ready(void);
void nc_script_update(void);

/* --- output --- */
void nc_s_print(const char *msg);
void nc_s_print_num(int value);
int  nc_s_draw_text(int x, int y, const char *msg);
int  nc_s_draw_num(int x, int y, int value);

/* --- sound --- */
int  nc_s_play_sound(int id);
int  nc_s_sound_count(void);
int  nc_s_play_music(int track);
int  nc_s_stop_music(void);
int  nc_s_shake(int amount);
int  nc_s_save_get(int slot);
int  nc_s_save_set(int slot, int value);
int  nc_s_save_write(void);
int  nc_s_save_read(void);
int  nc_s_save_erase(void);

/* --- input --- */
int  nc_s_btn_held(int button);
int  nc_s_btn_pressed(int button);

/* --- objects, addressed by index within the current scene --- */
int  nc_s_count(void);
int  nc_s_get_x(int id);
int  nc_s_get_y(int id);
int  nc_s_get_z(int id);
int  nc_s_set_pos(int id, int x, int y, int z);
int  nc_s_move(int id, int dx, int dy, int dz);
int  nc_s_set_rot(int id, int x, int y, int z);
int  nc_s_spin(int id, int x, int y, int z);
int  nc_s_show(int id);
int  nc_s_hide(int id);

/* --- sprites --- */
int  nc_s_sprite_count(void);
int  nc_s_sprite_x(int id);
int  nc_s_sprite_y(int id);
int  nc_s_sprite_set_pos(int id, int x, int y);
int  nc_s_sprite_move(int id, int dx, int dy);
int  nc_s_sprite_frame(int id, int u, int v);
int  nc_s_sprite_show(int id);
int  nc_s_sprite_hide(int id);

/* --- 2D physics ---
 *
 * Velocity is 20.12 fixed point: 4096 is one pixel per frame. Positions are
 * whole pixels; the remainder lives in the sprite so that fractional speeds
 * accumulate instead of rounding to nothing.
 */
int  nc_s_sprite_set_solid(int id, int on);
int  nc_s_sprite_set_vel(int id, int vx, int vy);
int  nc_s_sprite_vx(int id);
int  nc_s_sprite_vy(int id);
int  nc_s_move_and_slide(int id, int dx, int dy);
int  nc_s_physics_step(int id);
int  nc_s_on_floor(int id);
int  nc_s_on_ceiling(int id);
int  nc_s_on_wall(int id);
int  nc_s_set_gravity(int g);
int  nc_s_set_terminal(int v);
int  nc_s_touching(int a, int b);

/* --- the 2D view and sprite mirroring --- */
int  nc_s_scroll_set(int x, int y);
int  nc_s_scroll_by(int dx, int dy);
int  nc_s_scroll_x(void);
int  nc_s_scroll_y(void);
int  nc_s_scroll_follow(int id, int dead_w, int dead_h);
int  nc_s_sprite_set_flip(int id, int on);

/* --- prototyping helpers ---
 *
 * None of these is clever. They are here because writing them by hand in every
 * game is where the sign errors and the off-by-ones come from. */
int  nc_s_draw_text_center(int y, const char *msg);
int  nc_s_sign(int v);
int  nc_s_approach(int value, int target, int step);
int  nc_s_lerp(int a, int b, int t);
int  nc_s_rand_range(int lo, int hi);
int  nc_s_dist(int x1, int y1, int x2, int y2);
int  nc_s_every(int n);

/* --- camera --- */
int  nc_s_camera_set(int x, int y, int z, int rx, int ry, int rz);
int  nc_s_camera_move(int dx, int dy, int dz);
int  nc_s_camera_turn(int d);
int  nc_s_camera_x(void);
int  nc_s_camera_y(void);
int  nc_s_camera_z(void);
int  nc_s_camera_yaw(void);

/* --- scenes --- */
int  nc_s_goto_scene(int index);
int  nc_s_scene(void);
int  nc_s_scene_count(void);

/* --- misc --- */
int  nc_s_frame(void);
int  nc_s_set_clear(int r, int g, int b);
int  nc_s_abs(int v);
int  nc_s_min(int a, int b);
int  nc_s_max(int a, int b);
int  nc_s_clamp(int v, int lo, int hi);
int  nc_s_rand(int n);
int  nc_s_sin(int angle);
int  nc_s_cos(int angle);

/* Called by main.c, not by scripts. */
void nc_script_set_frame(int f);

#endif /* NC_SCRIPT_H */
