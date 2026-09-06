/*
 * data_demo - a Neon Coffee PS1 project
 *
 * This file has no geometry in it. The meshes, the scene layout and the starting
 * camera all come from scene.json, which `ncc build` compiles into a .ncpkg and
 * embeds in the executable. To change what you see, edit scene.json -- or build
 * the scene visually in godot/ and press "Export to NC".
 *
 * The only thing here is the camera, because moving the viewpoint is a decision
 * about how the game plays, not about what the scene contains.
 *
 *   D-pad      walk forward / back / strafe
 *   L1 / R1    turn
 *   L2 / R2    rise / drop
 *   START      pause the animation
 *   X          snap back to where the scene started
 */

#include <stdio.h>

#include "nc.h"

/* The package, linked in by CMake from scene.ncpkg. The symbol name is set in
 * CMakeLists.txt via psn00bsdk_target_incbin(). */
extern const unsigned long nc_package[];

#define MOVE_SPEED 14
#define TURN_SPEED 28
#define LIFT_SPEED 10

/* Rotation is a 16-bit angle where 4096 is a full turn. isin()/icos() use a
 * different scale -- 131072 for a full turn -- so converting between the two
 * means multiplying by 32. Mixing them up is the classic way to get a camera
 * that turns 32 times too fast. */
#define ROT_TO_TRIG 32

int main(void)
{
    NC_Package pkg;
    VECTOR  cam_pos;
    SVECTOR cam_rot;
    int frame = 0;
    int paused = 0;

    nc_gfx_init();
    nc_input_init();

    if (!nc_pkg_load(nc_package, &pkg)) {
        /* A red screen means the package did not load. The reason is on TTY --
         * check the PS1 TTY pane in NC Studio. */
        nc_gfx_set_clear(90, 10, 10);
        while (1)
            nc_gfx_flip();
    }

    nc_gfx_set_clear(pkg.scene.clear_r, pkg.scene.clear_g, pkg.scene.clear_b);

    cam_pos = pkg.scene.cam_pos;
    cam_rot = pkg.scene.cam_rot;

    printf("data_demo ready, camera at %d,%d,%d\n",
           (int)cam_pos.vx, (int)cam_pos.vy, (int)cam_pos.vz);

    while (1) {
        int a, fwd, side;

        nc_input_poll();

        if (nc_held(PAD_L1)) cam_rot.vy -= TURN_SPEED;
        if (nc_held(PAD_R1)) cam_rot.vy += TURN_SPEED;
        if (nc_held(PAD_L2)) cam_pos.vy -= LIFT_SPEED;
        if (nc_held(PAD_R2)) cam_pos.vy += LIFT_SPEED;

        /* Walk in the direction the camera faces rather than along the world
         * axes, which is what makes the controls feel attached to the view. */
        a = ((int)cam_rot.vy * ROT_TO_TRIG) & 131071;
        fwd = 0;
        side = 0;
        if (nc_held(PAD_UP))    fwd += MOVE_SPEED;
        if (nc_held(PAD_DOWN))  fwd -= MOVE_SPEED;
        if (nc_held(PAD_RIGHT)) side += MOVE_SPEED;
        if (nc_held(PAD_LEFT))  side -= MOVE_SPEED;

        if (fwd || side) {
            int s = isin(a);
            int c = icos(a);
            cam_pos.vx += (s * fwd + c * side) >> 12;
            cam_pos.vz += (c * fwd - s * side) >> 12;
        }

        if (nc_pressed(PAD_START))
            paused = !paused;
        if (nc_pressed(PAD_CROSS)) {
            cam_pos = pkg.scene.cam_pos;
            cam_rot = pkg.scene.cam_rot;
        }
        if (!paused)
            frame++;

        /* Set the camera before drawing anything -- it applies to every object
         * sorted into this frame. */
        nc_camera_set(&cam_pos, &cam_rot);
        nc_pkg_draw(&pkg, frame);
        nc_gfx_flip();
    }

    return 0;
}
