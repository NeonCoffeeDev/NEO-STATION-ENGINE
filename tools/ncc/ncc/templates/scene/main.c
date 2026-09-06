/*
 * @NAME@ - a Neon Coffee PS1 project
 *
 * Several objects at once: one spinning body in the middle and three smaller
 * ones orbiting it. This is the step up from the "cube" template -- it shows
 * how to reuse one mesh at many transforms, and how to do circular motion on a
 * machine with no floating point.
 *
 *   D-pad left/right   swing the camera around
 *   D-pad up/down      raise / lower the camera
 *   L1 / R1            zoom out / in
 *   X                  reset the view
 *   START              pause the orbits
 */

#include <stdio.h>

#include "nc.h"

/* ---- geometry ---------------------------------------------------------- */

/* Two shapes sharing one topology: same faces and normals, different corner
 * positions. A flatter box is just a cube with a smaller Y. */

static const SVECTOR box_verts[] = {
    { -100, -100, -100, 0 }, {  100, -100, -100, 0 },
    { -100,  100, -100, 0 }, {  100,  100, -100, 0 },
    {  100, -100,  100, 0 }, { -100, -100,  100, 0 },
    {  100,  100,  100, 0 }, { -100,  100,  100, 0 },
};

static const SVECTOR slab_verts[] = {
    { -60, -26, -60, 0 }, {  60, -26, -60, 0 },
    { -60,  26, -60, 0 }, {  60,  26, -60, 0 },
    {  60, -26,  60, 0 }, { -60, -26,  60, 0 },
    {  60,  26,  60, 0 }, { -60,  26,  60, 0 },
};

/* One outward normal per quad. ONE (4096) is 1.0 in 20.12 fixed point. */
static const SVECTOR box_norms[] = {
    {    0,    0, -ONE, 0 }, {    0,    0,  ONE, 0 },
    {    0, -ONE,    0, 0 }, {    0,  ONE,    0, 0 },
    { -ONE,    0,    0, 0 }, {  ONE,    0,    0, 0 },
};

/* Winding order decides which way a face points, and so whether backface
 * culling keeps it. Reverse one and that face disappears. */
static const NC_Quad box_quads[] = {
    { 0, 1, 2, 3 }, { 4, 5, 6, 7 }, { 5, 4, 0, 1 },
    { 6, 7, 3, 2 }, { 0, 2, 5, 7 }, { 3, 1, 6, 4 },
};

#define BOX_QUADS (sizeof(box_quads) / sizeof(box_quads[0]))

static const NC_Mesh mesh_box  = { box_verts,  box_norms, box_quads, BOX_QUADS };
static const NC_Mesh mesh_slab = { slab_verts, box_norms, box_quads, BOX_QUADS };

/* ---- the orbiting bodies ----------------------------------------------- */

typedef struct {
    int radius;      /* distance from the center                        */
    int speed;       /* angle units added per frame                     */
    int phase;       /* starting offset, so they do not line up         */
    int height;      /* fixed Y offset                                  */
    int spin;        /* how fast the body turns on its own axis         */
} Orbiter;

static const Orbiter orbiters[] = {
    { 320,  40,      0,  -60, 40 },
    { 480,  26,  43690,   30, -28 },
    { 620,  17,  87380,  110, 18 },
};

#define ORBITER_COUNT (sizeof(orbiters) / sizeof(orbiters[0]))

/* isin()/icos() take an angle where 131072 is a full turn, and return 20.12
 * fixed point where 4096 is 1.0. RotMatrix angles use a different scale --
 * 4096 is a full turn there -- so do not mix the two up. */
#define FULL_TURN 131072

int main(void)
{
    SVECTOR rot = { 0, 0, 0, 0 };
    VECTOR  pos = { 0, 0, 0 };

    int orbit_angle = 0;
    int self_angle = 0;
    int cam_yaw = 0;
    int cam_height = 0;
    int cam_dist = 1100;
    int paused = 0;
    unsigned int i;

    nc_gfx_init();
    nc_input_init();
    nc_gfx_set_clear(18, 14, 34);

    printf("@NAME@ starting: %d orbiters\n", (int)ORBITER_COUNT);

    while (1) {
        nc_input_poll();

        if (nc_held(PAD_LEFT))  cam_yaw -= 700;
        if (nc_held(PAD_RIGHT)) cam_yaw += 700;
        if (nc_held(PAD_UP)   && cam_height >  -600) cam_height -= 10;
        if (nc_held(PAD_DOWN) && cam_height <   600) cam_height += 10;
        if (nc_held(PAD_L1)   && cam_dist   <  2600) cam_dist   += 14;
        if (nc_held(PAD_R1)   && cam_dist   >   500) cam_dist   -= 14;

        if (nc_pressed(PAD_START)) paused = !paused;
        if (nc_pressed(PAD_CROSS)) {
            cam_yaw = 0;
            cam_height = 0;
            cam_dist = 1100;
        }

        if (!paused) {
            orbit_angle = (orbit_angle + 1) & (FULL_TURN - 1);
            self_angle += 1;
        }

        /* Center body. It sits at the origin, pushed away from the camera. */
        rot.vx = 0;
        rot.vy = (short)(self_angle * 12);
        rot.vz = (short)(self_angle * 5);
        pos.vx = 0;
        pos.vy = cam_height;
        pos.vz = cam_dist;
        nc_mesh_draw(&mesh_box, &rot, &pos);

        /* Orbiters. Circular motion without floating point: take the sine and
         * cosine of the angle in 20.12, multiply by the radius, then shift
         * right by 12 to get back to plain integer units. */
        for (i = 0; i < ORBITER_COUNT; i++) {
            const Orbiter *o = &orbiters[i];

            /* Swinging the camera around the scene is the same as swinging the
             * scene the other way, so cam_yaw folds straight into the angle. */
            int a = (orbit_angle * o->speed + o->phase + cam_yaw) & (FULL_TURN - 1);
            int x = (icos(a) * o->radius) >> 12;
            int z = (isin(a) * o->radius) >> 12;

            rot.vx = 0;
            rot.vy = (short)(self_angle * o->spin);
            rot.vz = 0;

            pos.vx = x;
            pos.vy = cam_height + o->height;
            pos.vz = cam_dist + z;

            /* Objects behind the camera would project to nonsense. The render
             * path culls by depth, but skipping them here saves the work. */
            if (pos.vz > 200)
                nc_mesh_draw(&mesh_slab, &rot, &pos);
        }

        nc_gfx_flip();
    }

    return 0;
}
