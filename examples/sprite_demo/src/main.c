/*
 * sprite_demo - a Neon Coffee PS1 game
 *
 * You should not need to edit this file. It is the harness that ties the pieces
 * together:
 *
 *   scene.json   what exists  -- meshes, objects, scenes, cameras
 *                (build it visually in godot/ and press "Export to NC")
 *   script.ncs   what happens -- your game logic, transpiled to C at build time
 *   this file    the loop that runs them
 *
 * If you find yourself wanting to change something here, it probably belongs in
 * script.ncs instead.
 */

#include <stdio.h>

#include "nc.h"
#include "nc_script.h"

/* The package, linked in by CMake from scene.ncpkg. */
extern const unsigned long nc_package[];

int main(void)
{
    NC_Package pkg;
    int frame = 0;

    nc_gfx_init();
    nc_input_init();

    if (!nc_pkg_load(nc_package, &pkg)) {
        /* A red screen means the data did not load. The reason is on TTY --
         * check the PS1 TTY pane in NC Studio. */
        nc_gfx_set_clear(90, 10, 10);
        while (1)
            nc_gfx_flip();
    }

    nc_scene_load(&pkg, 0);
    nc_script_set_frame(0);
    nc_script_ready();

    while (1) {
        int requested;

        nc_input_poll();

        nc_script_set_frame(frame);
        nc_script_update();

        /* Scene changes are deferred to here so a script can call goto_scene()
         * in the middle of its logic without objects shifting under it. */
        requested = nc_scene_take_request();
        if (requested >= 0 && requested != nc_scene_index()) {
            if (nc_scene_load(&pkg, requested)) {
                frame = 0;
                nc_script_set_frame(0);
                nc_script_ready();
            }
        }

        nc_scene_advance();
        nc_scene_draw();
        nc_gfx_flip();

        frame++;
    }

    return 0;
}
