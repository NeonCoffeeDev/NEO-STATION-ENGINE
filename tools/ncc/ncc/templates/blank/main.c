/*
 * @NAME@ - a Neon Coffee PS1 project
 *
 * The smallest thing that runs: set up graphics and input, then loop forever.
 * Nothing is drawn. Start here when you want to build something from scratch
 * rather than edit a demo.
 *
 * The engine lives beside this file:
 *   nc_gfx.c    rendering -- read nc_mesh_draw() first
 *   nc_input.c  controller
 *   nc.h        the API you call
 */

#include <stdio.h>

#include "nc.h"

int main(void)
{
    nc_gfx_init();
    nc_input_init();

    /* Background color, 0-255 per channel. */
    nc_gfx_set_clear(24, 16, 48);

    /* printf goes to the PS1's TTY. DuckStation writes it to
     * %LOCALAPPDATA%\DuckStation\duckstation.log as "I/TTY:" lines.
     * With no debugger attached, this is your main instrument. */
    printf("@NAME@ starting\n");

    while (1) {
        nc_input_poll();

        /* --- your update code goes here ---------------------------------
         *
         * Read input:
         *     if (nc_held(PAD_UP))        ... held down this frame
         *     if (nc_pressed(PAD_CROSS))  ... went down on THIS frame only
         *
         * Buttons: PAD_UP/DOWN/LEFT/RIGHT, PAD_CROSS/CIRCLE/SQUARE/TRIANGLE,
         *          PAD_L1/L2/R1/R2, PAD_START, PAD_SELECT.
         */

        /* --- your drawing code goes here ---------------------------------
         *
         * Declare a mesh (see the "cube" template for a full example):
         *     static const SVECTOR verts[] = { { -100, -100, -100, 0 }, ... };
         *     static const SVECTOR norms[] = { { 0, 0, -ONE, 0 }, ... };
         *     static const NC_Quad  quads[] = { { 0, 1, 2, 3 }, ... };
         *     static const NC_Mesh  mesh    = { verts, norms, quads, 6 };
         *
         * Then each frame:
         *     SVECTOR rot = { 0, 0, 0, 0 };
         *     VECTOR  pos = { 0, 0, 450 };
         *     nc_mesh_draw(&mesh, &rot, &pos);
         *
         * Remember there is no floating point on this machine. Positions and
         * angles are integers; 4096 is one full turn for rotation.
         */

        /* Wait for vblank, swap buffers, draw the frame. Always last. */
        nc_gfx_flip();
    }

    return 0;
}
