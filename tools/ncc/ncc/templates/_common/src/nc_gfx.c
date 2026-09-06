/*
 * Neon Coffee - graphics
 *
 * Double-buffered rendering with GTE transforms, based on PSn00bSDK's `graphics/gte`
 * example. The PS1 draws from an "ordering table": a linked list of primitives
 * bucketed by depth and walked back-to-front, because there is no Z-buffer.
 */

#include "nc.h"

typedef struct {
    DISPENV  disp;
    DRAWENV  draw;
    uint32_t ot[NC_OT_LEN];      /* depth buckets                    */
    char     p[NC_PACKET_LEN];   /* primitive scratch for this frame */
} NC_DrawBuffer;

static NC_DrawBuffer db[2];
static int   db_active;
static char *db_next;            /* bump allocator into db[active].p */

/* Light source colors. Each *column* is one light's RGB contribution; ONE (4096)
 * is 1.0. A column of zeroes disables that light. */
static MATRIX color_mtx = {
    ONE * 3 / 4, 0, 0,   /* red   */
    ONE * 3 / 4, 0, 0,   /* green */
    ONE * 3 / 4, 0, 0,   /* blue  */
};

/* Light directions. Each *row* is one light's direction vector. */
static MATRIX light_mtx = {
    -2048, -2048, -2048,
        0,     0,     0,
        0,     0,     0,
};

static int clear_r = 24, clear_g = 16, clear_b = 48;

static void setup_buffer(int i, int x)
{
    SetDefDispEnv(&db[i].disp, x, 0, NC_SCREEN_W, NC_SCREEN_H);
    /* Draw into the half of VRAM we are not currently displaying. */
    SetDefDrawEnv(&db[i].draw, NC_SCREEN_W - x, 0, NC_SCREEN_W, NC_SCREEN_H);
    setRGB0(&db[i].draw, clear_r, clear_g, clear_b);
    db[i].draw.isbg = 1;   /* clear the draw area each frame */
    db[i].draw.dtd  = 1;   /* dither, to hide 16-bit color banding */
}

void nc_gfx_set_clear(int r, int g, int b)
{
    clear_r = r; clear_g = g; clear_b = b;
    setRGB0(&db[0].draw, r, g, b);
    setRGB0(&db[1].draw, r, g, b);
}

void nc_gfx_init(void)
{
    ResetGraph(0);

    setup_buffer(0, 0);
    setup_buffer(1, NC_SCREEN_W);

    PutDrawEnv(&db[0].draw);

    ClearOTagR(db[0].ot, NC_OT_LEN);
    ClearOTagR(db[1].ot, NC_OT_LEN);

    db_active = 0;
    db_next   = db[0].p;

    InitGeom();                                  /* GTE */
    gte_SetGeomOffset(NC_SCREEN_W / 2, NC_SCREEN_H / 2);
    gte_SetGeomScreen(NC_SCREEN_W / 2);          /* projection distance ~= FOV */

    gte_SetBackColor(63, 63, 63);                /* ambient */
    gte_SetColorMatrix(&color_mtx);
}

void *nc_gfx_alloc(int bytes)
{
    char *base  = db[db_active].p;
    char *start = db_next;

    if ((start + bytes) > (base + NC_PACKET_LEN))
        return 0;                                /* out of packet space this frame */

    db_next = start + bytes;
    return start;
}

void nc_gfx_sort(int otz, void *prim)
{
    if (otz < 0 || otz >= NC_OT_LEN)
        return;                                  /* outside the depth range */
    addPrim(db[db_active].ot + otz, prim);
}

void nc_gfx_flip(void)
{
    DrawSync(0);
    VSync(0);

    db_active ^= 1;
    db_next    = db[db_active].p;

    ClearOTagR(db[db_active].ot, NC_OT_LEN);

    PutDrawEnv(&db[db_active].draw);
    PutDispEnv(&db[db_active].disp);
    SetDispMask(1);

    /* Draw the frame we just finished building, walking the OT back-to-front. */
    DrawOTag(db[1 - db_active].ot + (NC_OT_LEN - 1));
}

void nc_mesh_draw(const NC_Mesh *mesh, const SVECTOR *rot, const VECTOR *pos)
{
    MATRIX mtx, lmtx;
    int i, z;

    /* Build the model matrix, then rotate the light directions by it so the lighting
     * stays fixed in world space instead of turning with the model. */
    RotMatrix((SVECTOR *)rot, &mtx);
    TransMatrix(&mtx, (VECTOR *)pos);
    MulMatrix0(&light_mtx, &mtx, &lmtx);

    gte_SetRotMatrix(&mtx);
    gte_SetTransMatrix(&mtx);
    gte_SetLightMatrix(&lmtx);

    for (i = 0; i < mesh->quad_count; i++) {
        const NC_Quad *q = &mesh->quads[i];
        POLY_G4 *poly;

        /* Transform the first three vertices as a batch. */
        gte_ldv3(&mesh->verts[q->v0], &mesh->verts[q->v1], &mesh->verts[q->v2]);
        gte_rtpt();

        /* Backface cull: the cross product's sign tells us which way the face
         * points once projected. */
        gte_nclip();
        gte_stopz(&z);
        if (z < 0)
            continue;

        /* Average Z of the four corners decides which depth bucket we land in. */
        gte_avsz4();
        gte_stotz(&z);
        z >>= 2;
        if (z <= 0 || z >= NC_OT_LEN)
            continue;

        poly = (POLY_G4 *)nc_gfx_alloc(sizeof(POLY_G4));
        if (!poly)
            return;                              /* packet buffer exhausted */

        setPolyG4(poly);

        gte_stsxy0(&poly->x0);
        gte_stsxy1(&poly->x1);
        gte_stsxy2(&poly->x2);

        /* The fourth vertex has to go through on its own. */
        gte_ldv0(&mesh->verts[q->v3]);
        gte_rtps();
        gte_stsxy(&poly->x3);

        /* Light it. gte_ldrgb primes the GTE with the primitive code so the result
         * comes back in the right format. */
        gte_ldrgb(&poly->r0);
        gte_ldv0(&mesh->norms[i]);
        gte_ncs();
        gte_strgb(&poly->r0);

        /* POLY_G4 is Gouraud: give the other three corners the same lit color so the
         * face reads as flat-shaded rather than uninitialized. */
        poly->r1 = poly->r2 = poly->r3 = poly->r0;
        poly->g1 = poly->g2 = poly->g3 = poly->g0;
        poly->b1 = poly->b2 = poly->b3 = poly->b0;

        nc_gfx_sort(z, poly);
    }
}
