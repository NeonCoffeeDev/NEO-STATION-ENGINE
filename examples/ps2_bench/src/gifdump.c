/* What PS2SDK actually puts in the packet.
 *
 * The four-path texture test said something unexpected: a textured rectangle
 * drawn by draw_rect_textured samples the whole texture, and every triangle
 * built with draw_prim_start and hand-written registers samples only the
 * corner -- while the geometry of those triangles is correct. So XYZ arrives
 * and the texture coordinate does not, through three different attempts at
 * the coordinate, which means the thing I do not actually know is how the
 * library formats a primitive at all.
 *
 * Rather than reason about it a fourth time, this builds one of each into a
 * scratch buffer and prints the GIF tags decoded. FLG is the field that
 * settles it: PACKED spreads each register across a whole quadword, REGLIST
 * packs them as bare 64-bit values. Every hand-written vertex in this engine
 * assumes REGLIST. If the library is emitting PACKED, the texture coordinate
 * is being written to the wrong half of the wrong word, and the geometry only
 * survives because XYZ happens to land somewhere legible.
 *
 * The raw quadwords are printed underneath, because a decoded field is a
 * reading and the bytes are the fact.
 */

#include <kernel.h>
#include <stdio.h>
#include <stdarg.h>
#include <string.h>
#include <tamtypes.h>

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

#define CELL 8
#define GLYPH_W 16
#define GLYPH_H 16
#define FIRST_CHAR 32
#define FONT_COLUMNS 32
#define FONT_ROWS 2

extern unsigned int nc_font[];
extern const int nc_font_width, nc_font_height;

static framebuffer_t frame[2];
static int frame_draw;
static zbuffer_t z;
static texbuffer_t font_tex, test_buf;
static packet_t *packet;
static qword_t *packet_limit;
#define DRAW_QWORDS 8192

static unsigned int test_tex[64 * 64] __attribute__((aligned(64)));

/* Somewhere to build a primitive without sending it. */
static qword_t scratch_rect[32] __attribute__((aligned(64)));
static qword_t scratch_tri[32] __attribute__((aligned(64)));
static int rect_qwords, tri_qwords;

static char report[24][40];
static int report_lines;

static void say(const char *fmt, ...)
{
    va_list args;
    if (report_lines >= 24) return;
    va_start(args, fmt);
    vsnprintf(report[report_lines], 40, fmt, args);
    va_end(args);
    report_lines++;
}

/* The GIF tag is 128 bits. These are the fields that decide how everything
 * after it is read. */
static void decode(const char *what, qword_t *tag)
{
    u64 low = *(u64 *)tag;
    u64 high = *((u64 *)tag + 1);
    unsigned int nloop = (unsigned int)(low & 0x7FFF);
    unsigned int pre = (unsigned int)((low >> 46) & 1);
    unsigned int prim = (unsigned int)((low >> 47) & 0x7FF);
    unsigned int flg = (unsigned int)((low >> 58) & 3);
    unsigned int nreg = (unsigned int)((low >> 60) & 0xF);
    static const char *const mode[4] = {"PACKED", "REGLIST", "IMAGE", "?"};
    if (nreg == 0) nreg = 16;
    say("%s NLOOP=%u NREG=%u EOP=%u", what, nloop, nreg,
        (unsigned int)((low >> 15) & 1));
    say("  FLG=%s PRE=%u PRIM=%03X", mode[flg], pre, prim);
    say("  REGS=%08X%08X", (unsigned int)(high >> 32), (unsigned int)high);
    {
        /* The register list, named. 0=PRIM 1=RGBAQ 2=ST 3=UV 5=XYZ2 14=A+D */
        static const char *const reg[16] = {
            "PRIM","RGBAQ","ST","UV","XYZF2","XYZ2","TEX0","CLAMP",
            "FOG","?","XYZF3","XYZ3","?","?","A+D","NOP"};
        char names[40];
        unsigned int slot;
        names[0] = 0;
        for (slot = 0; slot < nreg && slot < 6; slot++) {
            unsigned int which = (unsigned int)((high >> (slot * 4)) & 0xF);
            if (strlen(names) + strlen(reg[which]) + 2 >= sizeof(names)) break;
            if (slot) strcat(names, " ");
            strcat(names, reg[which]);
        }
        say("  %s", names);
    }
}

static void dump(const char *what, qword_t *base, int count, int limit)
{
    int i;
    for (i = 0; i < count && i < limit; i++) {
        u64 low = *(u64 *)&base[i];
        u64 high = *((u64 *)&base[i] + 1);
        say("%s%d H %08X%08X", what, i,
            (unsigned int)(high >> 32), (unsigned int)high);
        say("%s%d L %08X%08X", what, i,
            (unsigned int)(low >> 32), (unsigned int)low);
    }
}

static void build_primitives(void)
{
    texrect_t r;
    prim_t prim = {0};
    color_t color = {0};
    qword_t *end;
    u64 *dw;
    int n;
    static const int tri[6] = {0, 1, 2, 0, 2, 3};

    /* The one that works. */
    r.v0.x = (float)(OFF_X + 16);  r.v0.y = (float)(OFF_Y + 16);  r.v0.z = 0;
    r.t0.u = 0.f;                  r.t0.v = 0.f;
    r.v1.x = (float)(OFF_X + 80);  r.v1.y = (float)(OFF_Y + 80);  r.v1.z = 0;
    r.t1.u = 64.f;                 r.t1.v = 64.f;
    r.color.r = r.color.g = r.color.b = 0x80;
    r.color.a = 0x80; r.color.q = 1.0f;
    end = draw_rect_textured(scratch_rect, 0, &r);
    rect_qwords = (int)(end - scratch_rect);

    /* The one that does not. */
    prim.type = PRIM_TRIANGLE; prim.mapping = DRAW_ENABLE;
    prim.colorfix = PRIM_FIXED; prim.shading = PRIM_SHADE_FLAT;
    prim.mapping_type = PRIM_MAP_UV;
    color.r = color.g = color.b = 0x80; color.a = 0x80; color.q = 1.0f;
    dw = (u64 *)draw_prim_start(scratch_tri, 0, &prim, &color);
    for (n = 0; n < 6; n++) {
        int corner = tri[n];
        int right = (corner == 1 || corner == 2);
        int low = (corner >= 2);
        texel_t uv; xyz_t xyz;
        uv.uv = ((u64)ftoi4(right ? 63 : 0) & 0x3FFF)
              | (((u64)ftoi4(low ? 63 : 0) & 0x3FFF) << 16);
        xyz.x = (u16)ftoi4(2048 + OFF_X + 16 + (right ? 64 : 0));
        xyz.y = (u16)ftoi4(2048 + OFF_Y + 16 + (low ? 64 : 0));
        xyz.z = 32;
        *dw++ = uv.uv; *dw++ = xyz.xyz;
    }
    end = draw_prim_end((qword_t *)dw, 2, DRAW_UV_REGLIST);
    tri_qwords = (int)(end - scratch_tri);

    say("RECT Q=%d", rect_qwords);
    decode("RECT", scratch_rect);
    say("TRI Q=%d  TAG0 THEN TAG3", tri_qwords);
    decode("T0", scratch_tri);
    /* draw_prim_start writes an A+D block setting PRIM and RGBAQ, then leaves
     * a quadword for draw_prim_end to fill in. That second tag is the one the
     * vertex registers are read under, and it is the one never looked at. */
    decode("T3", scratch_tri + 3);
    dump("V", scratch_tri + 4, tri_qwords - 4, 2);
}

/* ---- just enough to show it ------------------------------------------- */

static qword_t *glyph(qword_t *q, int x, int y, int code, int bright)
{
    texrect_t r;
    int index = code - FIRST_CHAR, u, v;
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
    atest_t atest; dtest_t dtest; ztest_t ztest; lod_t lod;
    clutbuffer_t clut = {0};
    qword_t *q;
    int i, x, y;

    dma_channel_initialize(DMA_CHANNEL_GIF, NULL, 0);
    dma_channel_fast_waits(DMA_CHANNEL_GIF);
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
    test_buf.width = 64; test_buf.psm = GS_PSM_32;
    test_buf.address = graph_vram_allocate(64, 64, GS_PSM_32, GRAPH_ALIGN_PAGE);
    test_buf.info.width = draw_log2(64);
    test_buf.info.height = draw_log2(64);
    test_buf.info.components = TEXTURE_COMPONENTS_RGBA;
    test_buf.info.function = TEXTURE_FUNCTION_DECAL;
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

    for (y = 0; y < 64; y++)
        for (x = 0; x < 64; x++) {
            int check = ((x >> 3) + (y >> 3)) & 1;
            unsigned int c = check ? 0x804060F0u : 0x8020C020u;
            test_tex[y * 64 + x] = c;
        }
    q = packet->data;
    FlushCache(0);
    q = draw_texture_transfer(q, nc_font, nc_font_width, nc_font_height,
                              GS_PSM_32, font_tex.address, font_tex.width);
    q = draw_texture_flush(q);
    dma_channel_send_chain(DMA_CHANNEL_GIF, packet->data, q - packet->data, 0, 0);
    dma_wait_fast();

    build_primitives();

    while (1) {
        int line;
        q = packet->data;
        q = draw_framebuffer(q, 0, &frame[frame_draw]);
        q = draw_clear(q, 0, OFF_X, OFF_Y, SCREEN_W, SCREEN_H, 0x0a, 0x0c, 0x12);
        clut.storage_mode = CLUT_STORAGE_MODE1; clut.load_method = CLUT_NO_LOAD;
        q = draw_texturebuffer(q, 0, &font_tex, &clut);
        for (line = 0; line < report_lines; line++)
            q = text(q, 12, 10 + line * 18, report[line], 0x80);
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
