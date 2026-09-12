/* NC Bench -- one boot, the whole cost model.
 *
 * Every question about what this console can afford has been answered so far
 * by shipping a build, photographing a television, and reasoning from one
 * number. That is a slow way to be wrong. This runs every measurement that
 * matters back to back in a single boot and prints them as a table, so the
 * cost of a vertex, a triangle, a divide, a cache miss and a screen of fill
 * are all known at once and a scene can be costed on paper afterwards.
 *
 * Each result is ticks for the whole run and ticks per operation. The tick is
 * the EE's cycle counter, which runs at half the 294.912 MHz core -- so one
 * tick is two CPU cycles, and a 59.94 Hz field is 2460060 of them.
 *
 * The loop-overhead row is subtracted from nothing automatically. It is there
 * so that a row worth 20 ticks an operation can be read as what it is rather
 * than as the measurement floor.
 */

#include <kernel.h>
#include <stdio.h>
#include <string.h>
#include <math.h>
#include <tamtypes.h>
#include <timer.h>

#include <dma.h>
#include <draw.h>
#include <draw2d.h>
#include <graph.h>
#include <gs_psm.h>
#include <packet.h>

#define SCREEN_W 640
#define SCREEN_H 448
#define OFF_X (-(SCREEN_W / 2))
#define OFF_Y (-(SCREEN_H / 2))
#define FRAME_PSM GS_PSM_16S

/* Matches the engine, so a number measured here means the same thing there. */
#define TICKS_PER_SECOND 147456000
#define TICKS_PER_FIELD  2460060

extern unsigned int nc_font[];
extern const int nc_font_width, nc_font_height;
extern const int nc_font_used_w, nc_font_used_h;

static framebuffer_t frame[2];
static int frame_draw;
static zbuffer_t z;
static texbuffer_t font_tex;
static packet_t *packet;
static qword_t *packet_limit;
#define DRAW_QWORDS 24576

/* ---- the work being measured ------------------------------------------ */

/* A synthetic model, big enough that per-vertex costs dominate the loop and
 * small enough to be honest about a character rather than a city. */
#define BENCH_VERTS 1024
#define BENCH_TRIS  512
#define BENCH_BONES 24

static float bench_pos[BENCH_VERTS * 3];
static float bench_nrm[BENCH_VERTS * 3];
static float bench_uv[BENCH_VERTS * 2];
static unsigned char bench_bone[BENCH_VERTS];
static unsigned short bench_index[BENCH_TRIS * 3];
static float bench_matrix[BENCH_BONES][12];

static float out_x[BENCH_VERTS];
static float out_y[BENCH_VERTS];
static float out_w[BENCH_VERTS];
static float out_depth[BENCH_VERTS];
static unsigned char out_vis[BENCH_VERTS];
static unsigned char out_shade[BENCH_VERTS];

static float scratch[8192];

static void bench_build(void)
{
    int i;
    for (i = 0; i < BENCH_VERTS; i++) {
        float t = (float)i * 0.0613f;
        bench_pos[i * 3 + 0] = sinf(t) * 1.5f;
        bench_pos[i * 3 + 1] = 0.9f + cosf(t * 0.7f) * 0.8f;
        bench_pos[i * 3 + 2] = cosf(t) * 1.5f;
        bench_nrm[i * 3 + 0] = sinf(t);
        bench_nrm[i * 3 + 1] = 0.3f;
        bench_nrm[i * 3 + 2] = cosf(t);
        bench_uv[i * 2 + 0] = (float)(i & 15) / 15.f;
        bench_uv[i * 2 + 1] = (float)((i >> 4) & 15) / 15.f;
        bench_bone[i] = (unsigned char)(i % BENCH_BONES);
    }
    for (i = 0; i < BENCH_TRIS; i++) {
        bench_index[i * 3 + 0] = (unsigned short)((i * 2) % BENCH_VERTS);
        bench_index[i * 3 + 1] = (unsigned short)((i * 2 + 1) % BENCH_VERTS);
        bench_index[i * 3 + 2] = (unsigned short)((i * 2 + 5) % BENCH_VERTS);
    }
    for (i = 0; i < BENCH_BONES; i++) {
        int k;
        for (k = 0; k < 12; k++) bench_matrix[i][k] = (k % 5 == 0) ? 1.f : 0.02f;
    }
    for (i = 0; i < 8192; i++) scratch[i] = (float)i * 0.001f;
}

/* The engine's own vertex pass, with the parts it can do without removed one
 * at a time -- which is what says where the time is rather than that it is
 * somewhere in here. */
static void pass_project(int skin, int light)
{
    float cy = 0.8253f, sy = 0.5646f, cp = 0.9689f, sp = 0.2474f;
    float focal = 388.0f;
    int i;
    for (i = 0; i < BENCH_VERTS; i++) {
        const float *p = &bench_pos[i * 3];
        const float *n = &bench_nrm[i * 3];
        float sx, sy2, sz, nx, ny, nz;
        float rx, rz, ry, depth, w, lit;
        int shade;

        if (skin) {
            const float *m = bench_matrix[bench_bone[i]];
            sx  = m[0] * p[0] + m[1] * p[1] + m[2] * p[2] + m[3];
            sy2 = m[4] * p[0] + m[5] * p[1] + m[6] * p[2] + m[7];
            sz  = m[8] * p[0] + m[9] * p[1] + m[10] * p[2] + m[11];
            nx  = m[0] * n[0] + m[1] * n[1] + m[2] * n[2];
            ny  = m[4] * n[0] + m[5] * n[1] + m[6] * n[2];
            nz  = m[8] * n[0] + m[9] * n[1] + m[10] * n[2];
        } else {
            sx = p[0]; sy2 = p[1]; sz = p[2];
            nx = n[0]; ny = n[1]; nz = n[2];
        }

        rx = sx * cy + sz * sy;
        rz = -sx * sy + sz * cy;
        ry = sy2 * cp - rz * sp;
        depth = sy2 * sp + rz * cp;

        out_depth[i] = depth;
        out_vis[i] = depth >= 0.3f;
        if (out_vis[i]) {
            w = 1.f / depth;
            out_w[i] = w;
            out_x[i] = rx * focal * w;
            out_y[i] = -ry * focal * w;
        } else {
            out_w[i] = 0.f;
        }

        lit = 0.4f;
        if (light) {
            float d = nx * 0.3f + ny * 0.9f + nz * 0.3f;
            if (d > 0) lit += d * 0.7f;
        }
        shade = (int)(lit * 128.f);
        if (shade > 255) shade = 255;
        out_shade[i] = (unsigned char)shade;
    }
}

/* The emit half: registers written into the packet, nothing computed. */
static qword_t *pass_emit(qword_t *q, int triangles)
{
    prim_t prim = {0};
    color_t color = {0};
    int done = 0;

    prim.type = PRIM_TRIANGLE; prim.mapping = DRAW_ENABLE;
    prim.colorfix = PRIM_FIXED; prim.shading = PRIM_SHADE_GOURAUD;
    prim.mapping_type = PRIM_MAP_ST;
    color.a = 0x80; color.q = 1.0f;

    while (done < triangles) {
        int batch = triangles - done;
        int corner, total;
        u64 *dw;
        if (batch > 96) batch = 96;
        batch &= ~1;                        /* even, for quadword alignment */
        if (!batch) break;
        total = batch * 3;
        if (q + total * 2 + 32 >= packet_limit) break;
        dw = (u64 *)draw_prim_start(q, 0, &prim, &color);
        for (corner = 0; corner < total; corner++) {
            int v = bench_index[(done * 3 + corner) % (BENCH_TRIS * 3)];
            float w = out_w[v];
            texel_t st; xyz_t xyz;
            st.s = bench_uv[v * 2] * w;
            st.t = bench_uv[v * 2 + 1] * w;
            color.r = color.g = color.b = out_shade[v];
            color.q = w;
            xyz.x = (u16)ftoi4(2048 + out_x[v]);
            xyz.y = (u16)ftoi4(2048 + out_y[v]);
            xyz.z = 32;
            *dw++ = st.uv; *dw++ = color.rgbaq; *dw++ = xyz.xyz;
        }
        q = draw_prim_end((qword_t *)dw, 3, DRAW_STQ2_REGLIST);
        done += batch;
    }
    return q;
}

/* ---- results ----------------------------------------------------------- */

#define MAX_ROWS 16
static const char *row_name[MAX_ROWS];
static unsigned int row_ticks[MAX_ROWS];
static int row_ops[MAX_ROWS];
static int row_count;

static void record(const char *name, unsigned int ticks, int ops)
{
    if (row_count >= MAX_ROWS) return;
    row_name[row_count] = name;
    row_ticks[row_count] = ticks;
    row_ops[row_count] = ops;
    row_count++;
}

/* Everything is run several times and the best kept. A single run catches
 * whatever the cache and the DMA happened to be doing; the best of several is
 * the cost of the work itself. */
#define REPEATS 8

static void run_benchmarks(void)
{
    unsigned int mark, best;
    int r, i;
    volatile float sink = 0.f;

    best = 0xFFFFFFFFu;
    for (r = 0; r < REPEATS; r++) {
        mark = cpu_ticks();
        for (i = 0; i < BENCH_VERTS; i++) sink += 1.f;
        { unsigned int d = cpu_ticks() - mark; if (d < best) best = d; }
    }
    record("LOOP FLOOR", best, BENCH_VERTS);

    best = 0xFFFFFFFFu;
    for (r = 0; r < REPEATS; r++) {
        mark = cpu_ticks(); pass_project(0, 0);
        { unsigned int d = cpu_ticks() - mark; if (d < best) best = d; }
    }
    record("PROJECT", best, BENCH_VERTS);

    best = 0xFFFFFFFFu;
    for (r = 0; r < REPEATS; r++) {
        mark = cpu_ticks(); pass_project(0, 1);
        { unsigned int d = cpu_ticks() - mark; if (d < best) best = d; }
    }
    record("PROJ+LIGHT", best, BENCH_VERTS);

    best = 0xFFFFFFFFu;
    for (r = 0; r < REPEATS; r++) {
        mark = cpu_ticks(); pass_project(1, 1);
        { unsigned int d = cpu_ticks() - mark; if (d < best) best = d; }
    }
    record("PROJ+LGT+SKIN", best, BENCH_VERTS);

    best = 0xFFFFFFFFu;
    for (r = 0; r < REPEATS; r++) {
        qword_t *q = packet->data;
        mark = cpu_ticks(); q = pass_emit(q, BENCH_TRIS);
        { unsigned int d = cpu_ticks() - mark; if (d < best) best = d; }
        (void)q;
    }
    record("EMIT TRI", best, BENCH_TRIS);

    best = 0xFFFFFFFFu;
    for (r = 0; r < REPEATS; r++) {
        float acc = 1.f;
        mark = cpu_ticks();
        for (i = 1; i <= 4096; i++) acc += 1.f / (float)i;
        { unsigned int d = cpu_ticks() - mark; if (d < best) best = d; }
        sink += acc;
    }
    record("FLOAT DIVIDE", best, 4096);

    best = 0xFFFFFFFFu;
    for (r = 0; r < REPEATS; r++) {
        float acc = 0.f;
        mark = cpu_ticks();
        for (i = 0; i < 1024; i++) acc += cosf((float)i * 0.01f);
        { unsigned int d = cpu_ticks() - mark; if (d < best) best = d; }
        sink += acc;
    }
    record("COSF", best, 1024);

    best = 0xFFFFFFFFu;
    for (r = 0; r < REPEATS; r++) {
        float acc = 0.f;
        mark = cpu_ticks();
        for (i = 0; i < 8192; i++) acc += scratch[i];
        { unsigned int d = cpu_ticks() - mark; if (d < best) best = d; }
        sink += acc;
    }
    record("READ SEQ", best, 8192);

    /* 16 floats apart is 64 bytes: one cache line per access, so every read
     * misses. The gap between this and the row above is what a cache miss
     * costs on this machine. */
    best = 0xFFFFFFFFu;
    for (r = 0; r < REPEATS; r++) {
        float acc = 0.f;
        mark = cpu_ticks();
        for (i = 0; i < 8192; i += 16) acc += scratch[i];
        { unsigned int d = cpu_ticks() - mark; if (d < best) best = d; }
        sink += acc;
    }
    record("READ STRIDE64", best, 8192 / 16);

    (void)sink;
}

/* ---- the rest is just enough engine to show the answers ---------------- */

static void upload_font(void)
{
    qword_t *q = packet->data;
    FlushCache(0);
    q = draw_texture_transfer(q, nc_font, nc_font_width, nc_font_height,
                              GS_PSM_32, font_tex.address, font_tex.width);
    q = draw_texture_flush(q);
    dma_channel_send_chain(DMA_CHANNEL_GIF, packet->data, q - packet->data, 0, 0);
    dma_wait_fast();
}

/* The sheet is 256x16 holding 8x8 cells in a 32 by 2 grid, and every glyph is
 * drawn at twice that so it can be read from a sofa. Guessing this layout --
 * one row of 8x16 cells -- is what produced a screen of scrambled blocks the
 * first time, so the numbers here are the engine's own. */
#define CELL 8
#define GLYPH_W 16
#define GLYPH_H 16
#define FIRST_CHAR 32
#define FONT_COLUMNS 32
#define FONT_ROWS 2

static qword_t *glyph(qword_t *q, int x, int y, int code, int bright)
{
    texrect_t r;
    int index = code - FIRST_CHAR;
    int u, v;
    if (index < 0 || index >= FONT_COLUMNS * FONT_ROWS || code == ' ') return q;
    if (q + 16 >= packet_limit) return q;
    u = (index % FONT_COLUMNS) * CELL;
    v = (index / FONT_COLUMNS) * CELL;
    r.v0.x = (float)(OFF_X + x); r.v0.y = (float)(OFF_Y + y); r.v0.z = 0;
    r.t0.u = (float)u;           r.t0.v = (float)v;
    r.v1.x = (float)(OFF_X + x + GLYPH_W);
    r.v1.y = (float)(OFF_Y + y + GLYPH_H); r.v1.z = 0;
    r.t1.u = (float)(u + CELL);  r.t1.v = (float)(v + CELL);
    r.color.r = r.color.g = r.color.b = bright;
    r.color.a = 0x80; r.color.q = 1.0f;
    return draw_rect_textured(q, 0, &r);
}

static qword_t *text(qword_t *q, int x, int y, const char *s, int bright)
{
    while (*s) {
        char c = *s++;
        if (c >= 'a' && c <= 'z') c = (char)(c - 32);
        q = glyph(q, x, y, c, bright);
        x += GLYPH_W;
    }
    return q;
}

int main(void)
{
    int i;
    atest_t atest; dtest_t dtest; ztest_t ztest; lod_t lod;
    qword_t *q;

    dma_channel_initialize(DMA_CHANNEL_GIF, NULL, 0);
    dma_channel_fast_waits(DMA_CHANNEL_GIF);
    printf("nc_bench: measuring\n");

    packet = packet_init(DRAW_QWORDS, PACKET_NORMAL);
    if (!packet) return 1;
    packet_limit = packet->data + DRAW_QWORDS;

    for (i = 0; i < 2; i++) {
        frame[i].width = SCREEN_W; frame[i].height = SCREEN_H;
        frame[i].mask = 0; frame[i].psm = FRAME_PSM;
        frame[i].address = graph_vram_allocate(SCREEN_W, SCREEN_H, FRAME_PSM,
                                               GRAPH_ALIGN_PAGE);
    }
    z.enable = DRAW_DISABLE; z.mask = 0; z.method = ZTEST_METHOD_ALLPASS;
    z.zsm = GS_ZBUF_16; z.address = 0;
    font_tex.width = nc_font_width; font_tex.psm = GS_PSM_32;
    font_tex.address = graph_vram_allocate(nc_font_width,
                                           (nc_font_height + 31) & ~31,
                                           GS_PSM_32, GRAPH_ALIGN_PAGE);
    font_tex.info.width = draw_log2(nc_font_width);
    font_tex.info.height = draw_log2(nc_font_height);
    font_tex.info.components = TEXTURE_COMPONENTS_RGBA;
    font_tex.info.function = TEXTURE_FUNCTION_DECAL;
    graph_initialize(frame[0].address, SCREEN_W, SCREEN_H, FRAME_PSM, 0, 0);
    frame_draw = 1;

    q = packet->data;
    q = draw_setup_environment(q, 0, &frame[0], &z);
    q = draw_primitive_xyoffset(q, 0, 2048 + OFF_X, 2048 + OFF_Y);
    atest.enable = DRAW_ENABLE; atest.method = ATEST_METHOD_GREATER;
    atest.compval = 0x00; atest.keep = ATEST_KEEP_FRAMEBUFFER;
    dtest.enable = DRAW_DISABLE; dtest.pass = 0;
    ztest.enable = DRAW_DISABLE; ztest.method = ZTEST_METHOD_ALLPASS;
    q = draw_pixel_test(q, 0, &atest, &dtest, &ztest);
    lod.calculation = LOD_USE_K; lod.max_level = 0;
    lod.mag_filter = LOD_MAG_NEAREST; lod.min_filter = LOD_MIN_NEAREST;
    lod.l = 0; lod.k = 0;
    q = draw_texture_sampling(q, 0, &lod);
    q = draw_finish(q);
    dma_channel_send_normal(DMA_CHANNEL_GIF, packet->data, q - packet->data, 0, 0);
    dma_wait_fast();

    upload_font();
    bench_build();
    run_benchmarks();

    while (1) {
        clutbuffer_t clut = {0};
        char line[64];
        int row;

        q = packet->data;
        q = draw_framebuffer(q, 0, &frame[frame_draw]);
        q = draw_clear(q, 0, OFF_X, OFF_Y, SCREEN_W, SCREEN_H, 0x0a, 0x0c, 0x12);
        clut.storage_mode = CLUT_STORAGE_MODE1; clut.load_method = CLUT_NO_LOAD;
        q = draw_texturebuffer(q, 0, &font_tex, &clut);

        q = text(q, 16, 10, "NC BENCH  FIELD=2460060 TK", 0x80);
        q = text(q, 16, 30, "ROW              TOTAL   TK/OP", 0x50);
        for (row = 0; row < row_count; row++) {
            int y = 50 + row * 20;
            unsigned int per = row_ops[row] ? row_ticks[row] / row_ops[row] : 0;
            unsigned int frac = row_ops[row]
                ? (row_ticks[row] * 100u / (unsigned)row_ops[row]) % 100 : 0;
            sprintf(line, "%-14s%8u%4u.%02u",
                    row_name[row], row_ticks[row], per, frac);
            q = text(q, 16, y, line, 0x80);
        }
        sprintf(line, "FIELD=%u VTX",
                row_count > 3 && row_ticks[3]
                    ? (unsigned int)((u64)TICKS_PER_FIELD * BENCH_VERTS / row_ticks[3])
                    : 0);
        q = text(q, 16, 50 + row_count * 20 + 12, line, 0x70);
        sprintf(line, "FIELD=%u TRI",
                row_count > 4 && row_ticks[4]
                    ? (unsigned int)((u64)TICKS_PER_FIELD * BENCH_TRIS / row_ticks[4])
                    : 0);
        q = text(q, 16, 50 + row_count * 20 + 32, line, 0x70);

        q = draw_finish(q);
        dma_wait_fast();
        dma_channel_send_normal(DMA_CHANNEL_GIF, packet->data,
                                q - packet->data, 0, 0);
        draw_wait_finish();
        graph_wait_vsync();
        graph_set_framebuffer_filtered(frame[frame_draw].address, SCREEN_W,
                                       FRAME_PSM, 0, 0);
        frame_draw ^= 1;
    }
    return 0;
}
