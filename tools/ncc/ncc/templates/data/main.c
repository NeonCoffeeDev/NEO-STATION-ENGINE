/*
 * @NAME@ - a Neon Coffee PS1 project
 *
 * This one has no geometry in it. The meshes and the scene layout come from
 * scene.json, which `ncc build` compiles into a .ncpkg and embeds in the
 * executable. To change what you see, edit scene.json and rebuild -- you should
 * not need to touch this file at all.
 *
 * That is the point: it is what lets an editor drive the game.
 *
 *   START   pause
 *   X       jump back to frame 0
 */

#include <stdio.h>

#include "nc.h"

/* The package, linked in by CMake from scene.ncpkg. The symbol name is set in
 * CMakeLists.txt via psn00bsdk_target_incbin(). */
extern const unsigned long nc_package[];

int main(void)
{
    NC_Package pkg;
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
    printf("@NAME@ ready\n");

    while (1) {
        nc_input_poll();

        if (nc_pressed(PAD_START))
            paused = !paused;
        if (nc_pressed(PAD_CROSS))
            frame = 0;
        if (!paused)
            frame++;

        nc_pkg_draw(&pkg, frame);
        nc_gfx_flip();
    }

    return 0;
}
