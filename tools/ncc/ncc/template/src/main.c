/*
 * @NAME@ - a Neon Coffee PS1 project
 *
 * This is your game. Edit it freely; the files next to it (nc_gfx.c, nc_input.c)
 * are the engine and are meant to grow into the NC runtime.
 *
 *   D-pad      rotate the cube
 *   X          reset rotation
 *   L1 / R1    move it away / closer
 */

#include "nc.h"

/* A cube, 200 units across, centered on the origin. SVECTOR components are 16-bit
 * integers -- there is no floating point on this machine. */
static const SVECTOR cube_verts[] = {
    { -100, -100, -100, 0 },
    {  100, -100, -100, 0 },
    { -100,  100, -100, 0 },
    {  100,  100, -100, 0 },
    {  100, -100,  100, 0 },
    { -100, -100,  100, 0 },
    {  100,  100,  100, 0 },
    { -100,  100,  100, 0 },
};

/* One outward-facing normal per quad, for lighting. ONE is 4096 == 1.0. */
static const SVECTOR cube_norms[] = {
    {     0,     0, -ONE, 0 },
    {     0,     0,  ONE, 0 },
    {     0, -ONE,     0, 0 },
    {     0,  ONE,     0, 0 },
    { -ONE,      0,     0, 0 },
    {  ONE,      0,     0, 0 },
};

/* Winding order decides which way a face points, and therefore whether it survives
 * backface culling. Reverse a quad here and that face turns invisible. */
static const NC_Quad cube_quads[] = {
    { 0, 1, 2, 3 },
    { 4, 5, 6, 7 },
    { 5, 4, 0, 1 },
    { 6, 7, 3, 2 },
    { 0, 2, 5, 7 },
    { 3, 1, 6, 4 },
};

static const NC_Mesh cube = {
    cube_verts,
    cube_norms,
    cube_quads,
    sizeof(cube_quads) / sizeof(cube_quads[0]),
};

int main(void)
{
    SVECTOR rot = { 0, 0, 0, 0 };
    VECTOR  pos = { 0, 0, 450 };

    nc_gfx_init();
    nc_input_init();
    nc_gfx_set_clear(24, 16, 48);

    while (1) {
        nc_input_poll();

        if (nc_held(PAD_UP))    rot.vx -= 24;
        if (nc_held(PAD_DOWN))  rot.vx += 24;
        if (nc_held(PAD_LEFT))  rot.vy -= 24;
        if (nc_held(PAD_RIGHT)) rot.vy += 24;

        if (nc_held(PAD_L1) && pos.vz < 2000) pos.vz += 8;
        if (nc_held(PAD_R1) && pos.vz >  250) pos.vz -= 8;

        if (nc_pressed(PAD_CROSS)) {
            rot.vx = rot.vy = rot.vz = 0;
            pos.vz = 450;
        }

        /* Idle spin, so it is obviously alive with no controller attached. */
        rot.vy += 8;
        rot.vz += 4;

        nc_mesh_draw(&cube, &rot, &pos);
        nc_gfx_flip();
    }

    return 0;
}
