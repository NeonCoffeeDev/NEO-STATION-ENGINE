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

/* Where the built-in debug font goes in VRAM. The two 320x240 framebuffers
 * occupy x 0..639 of rows 0..239, so the right-hand strip is free. */
#define FONT_VRAM_X 960
#define FONT_VRAM_Y 0

/* The view matrix: the inverse of the camera's transform. Identity means the
 * camera sits at the origin looking down +Z. */
static MATRIX view;

/* Screen shake. Magnitude decays a little each frame and the offset is
 * re-rolled, which looks like a jolt settling rather than a vibration. */
static int shake_mag;
static int shake_ox, shake_oy;
static unsigned long shake_rng = 0x2545F491;

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

    /* PSn00bSDK ships a small debug font. It is not pretty, but it puts text on
     * the TV today rather than after the texture work. */
    FntLoad(FONT_VRAM_X, FONT_VRAM_Y);

    nc_camera_reset();
}


void nc_text(int x, int y, const char *text)
{
    char *start, *end;

    if (text == 0)
        return;

    /* FntSort writes one sprite per character and hands back where it stopped,
     * so reserve a generous block and then hand the unused tail back. */
    start = (char *)nc_gfx_alloc(NC_TEXT_BUDGET);
    if (!start)
        return;

    end = (char *)FntSort(db[db_active].ot, start, x, y, text);

    /* Rewind the bump allocator to what was actually used. */
    db_next = end;
}


void nc_camera_reset(void)
{
    VECTOR  zero_p = { 0, 0, 0 };
    SVECTOR zero_r = { 0, 0, 0, 0 };
    nc_camera_set(&zero_p, &zero_r);
}


void nc_camera_set(const VECTOR *pos, const SVECTOR *rot)
{
    MATRIX cam;
    VECTOR neg;
    SVECTOR r = *rot;
    int i, j;

    /* Orientation of the camera itself. */
    RotMatrix(&r, &cam);

    /* A rotation matrix's inverse is its transpose, which is far cheaper than a
     * general inverse and exact in fixed point. */
    for (i = 0; i < 3; i++)
        for (j = 0; j < 3; j++)
            view.m[i][j] = cam.m[j][i];

    /* ...and the translation becomes -(R^T * P), so the world shifts opposite
     * to the camera. */
    neg.vx = -pos->vx;
    neg.vy = -pos->vy;
    neg.vz = -pos->vz;
    ApplyMatrixLV(&view, &neg, &neg);
    view.t[0] = neg.vx;
    view.t[1] = neg.vy;
    view.t[2] = neg.vz;
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

void nc_shake_add(int amount)
{
    /* Strongest wins rather than accumulating: three explosions at once should
     * not multiply into a screen that never settles. */
    if (amount > shake_mag)
        shake_mag = amount;
    if (shake_mag > 16)
        shake_mag = 16;
}


void nc_shake_update(void)
{
    if (shake_mag <= 0) {
        shake_mag = 0;
        shake_ox = shake_oy = 0;
        return;
    }

    shake_rng = shake_rng * 1103515245UL + 12345UL;
    shake_ox = (int)((shake_rng >> 16) % (unsigned long)(shake_mag * 2 + 1))
               - shake_mag;
    shake_rng = shake_rng * 1103515245UL + 12345UL;
    shake_oy = (int)((shake_rng >> 16) % (unsigned long)(shake_mag * 2 + 1))
               - shake_mag;

    shake_mag--;
}


int nc_shake_x(void) { return shake_ox; }
int nc_shake_y(void) { return shake_oy; }


void nc_sprite_draw(uint16_t tpage, uint16_t clut, int x, int y, int w, int h,
                    int u, int v, int fixed)
{
    POLY_FT4 *poly = (POLY_FT4 *)nc_gfx_alloc(sizeof(POLY_FT4));
    if (!poly)
        return;

    if (!fixed) {
        x += shake_ox;
        y += shake_oy;
    }

    setPolyFT4(poly);

    /* 128 is neutral for texture modulation on this hardware -- anything less
     * darkens the sprite, more brightens it. */
    setRGB0(poly, 128, 128, 128);

    poly->x0 = (short)x;         poly->y0 = (short)y;
    poly->x1 = (short)(x + w);   poly->y1 = (short)y;
    poly->x2 = (short)x;         poly->y2 = (short)(y + h);
    poly->x3 = (short)(x + w);   poly->y3 = (short)(y + h);

    setUV4(poly,
           u,             v,
           u + w - 1,     v,
           u,             v + h - 1,
           u + w - 1,     v + h - 1);
    poly->tpage = tpage;
    poly->clut = clut;

    /* Depth 1: in front of everything the 3D pass sorts, behind text at 0. */
    nc_gfx_sort(NC_SPRITE_DEPTH, poly);
}


void nc_mesh_draw(const NC_Mesh *mesh, const SVECTOR *rot, const VECTOR *pos)
{
    MATRIX world, modelview, lmtx;
    int i, z;

    /* Model matrix: where this object sits in the world. */
    RotMatrix((SVECTOR *)rot, &world);
    TransMatrix(&world, (VECTOR *)pos);

    /* Light directions are rotated by the MODEL matrix only, never the camera.
     * That is what keeps lights fixed in the world -- fold the camera in here
     * and every light turns with you, like a miner's lamp. */
    MulMatrix0(&light_mtx, &world, &lmtx);

    /* What the GTE actually transforms by is view * world. */
    CompMatrixLV(&view, &world, &modelview);

    gte_SetRotMatrix(&modelview);
    gte_SetTransMatrix(&modelview);
    gte_SetLightMatrix(&lmtx);

    for (i = 0; i < mesh->quad_count; i++) {
        const NC_Quad *q = &mesh->quads[i];

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

        if (mesh->uvs) {
            /* Textured: a flat-shaded, textured quad. The lit colour modulates
             * the texture, so lighting still applies. */
            const uint8_t *uv = &mesh->uvs[i * 8];
            POLY_FT4 *poly = (POLY_FT4 *)nc_gfx_alloc(sizeof(POLY_FT4));
            if (!poly)
                return;                          /* packet buffer exhausted */

            setPolyFT4(poly);

            gte_stsxy0(&poly->x0);
            gte_stsxy1(&poly->x1);
            gte_stsxy2(&poly->x2);
            gte_ldv0(&mesh->verts[q->v3]);
            gte_rtps();
            gte_stsxy(&poly->x3);

            gte_ldrgb(&poly->r0);
            gte_ldv0(&mesh->norms[i]);
            gte_ncs();
            gte_strgb(&poly->r0);

            setUV4(poly, uv[0], uv[1], uv[2], uv[3],
                   uv[4], uv[5], uv[6], uv[7]);
            poly->tpage = mesh->tpage;
            poly->clut = mesh->clut;

            nc_gfx_sort(z, poly);
        } else {
            POLY_G4 *poly = (POLY_G4 *)nc_gfx_alloc(sizeof(POLY_G4));
            if (!poly)
                return;

            setPolyG4(poly);

            gte_stsxy0(&poly->x0);
            gte_stsxy1(&poly->x1);
            gte_stsxy2(&poly->x2);

            /* The fourth vertex has to go through on its own. */
            gte_ldv0(&mesh->verts[q->v3]);
            gte_rtps();
            gte_stsxy(&poly->x3);

            /* Light it. gte_ldrgb primes the GTE with the primitive code so the
             * result comes back in the right format. */
            gte_ldrgb(&poly->r0);
            gte_ldv0(&mesh->norms[i]);
            gte_ncs();
            gte_strgb(&poly->r0);

            /* POLY_G4 is Gouraud: give the other three corners the same lit
             * colour so the face reads as flat-shaded, not uninitialised. */
            poly->r1 = poly->r2 = poly->r3 = poly->r0;
            poly->g1 = poly->g2 = poly->g3 = poly->g0;
            poly->b1 = poly->b2 = poly->b3 = poly->b0;

            nc_gfx_sort(z, poly);
        }
    }
}
