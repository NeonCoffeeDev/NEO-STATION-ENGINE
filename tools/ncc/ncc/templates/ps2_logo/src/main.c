/*
 * @NAME@ - the smallest possible PS2 texture test
 *
 * This exists to bisect a black screen, not to be a game.
 *
 * NCPAD -- a coloured box moved with the pad -- runs on hardware. The visual
 * novel, which adds textures and text, does not. Everything between those two
 * is suspect, and guessing which part is wrong from a black screen is not
 * debugging. So this draws exactly one thing: the logo, as a texture, on a
 * cleared screen. No font, no menu, no state, no per-frame text.
 *
 *   It draws the logo   -> the texture path works, and the fault is in what
 *                          the visual novel does with text or packets.
 *   Black screen        -> the texture path itself is wrong: the upload, the
 *                          alpha test, the buffer setup, or VRAM allocation.
 *   A coloured screen   -> the GS came up but the texture did not; the clear
 *                          proves the frame loop is running.
 *
 * The background is deliberately NOT the near-black NC ground, because a black
 * screen and a very dark screen are indistinguishable on a television. It
 * clears to a mid blue, which no failure mode produces by accident.
 */

#include <kernel.h>
#include <stdio.h>
#include <tamtypes.h>

#include <dma.h>
#include <draw.h>
#include <draw2d.h>
#include <graph.h>
#include <gs_psm.h>
#include <packet.h>

#define SCREEN_W 640
#define SCREEN_H 448
#define OFF_X (2048 - (SCREEN_W / 2))
#define OFF_Y (2048 - (SCREEN_H / 2))

extern unsigned int nc_logo[];
extern const int nc_logo_width, nc_logo_height;
extern const int nc_logo_used_w, nc_logo_used_h;

static framebuffer_t frame;
static zbuffer_t z;
static texbuffer_t logo_tex;


int main(void)
{
    packet_t *packet;
    qword_t *q;
    clutbuffer_t clut;
    atest_t atest;
    dtest_t dtest;
    ztest_t ztest;
    lod_t lod;
    int frames = 0;
    int height = 256;
    int width = nc_logo_used_w * height / nc_logo_used_h;

    printf("@NAME@: PS2 texture test starting\n");

    frame.width = SCREEN_W;
    frame.height = SCREEN_H;
    frame.mask = 0;
    frame.psm = GS_PSM_32;
    frame.address = graph_vram_allocate(frame.width, frame.height, frame.psm,
                                        GRAPH_ALIGN_PAGE);

    z.enable = DRAW_DISABLE;
    z.mask = 0;
    z.method = ZTEST_METHOD_ALLPASS;
    z.zsm = GS_ZBUF_32;
    z.address = 0;

    logo_tex.width = nc_logo_width;
    logo_tex.psm = GS_PSM_32;
    logo_tex.address = graph_vram_allocate(nc_logo_width, nc_logo_height,
                                           GS_PSM_32, GRAPH_ALIGN_BLOCK);
    logo_tex.info.width = draw_log2(nc_logo_width);
    logo_tex.info.height = draw_log2(nc_logo_height);
    logo_tex.info.components = TEXTURE_COMPONENTS_RGBA;
    logo_tex.info.function = TEXTURE_FUNCTION_DECAL;

    printf("@NAME@: frame at 0x%x, texture at 0x%x (%dx%d)\n",
           frame.address, logo_tex.address, nc_logo_width, nc_logo_height);

    graph_initialize(frame.address, frame.width, frame.height, frame.psm, 0, 0);

    packet = packet_init(2048, PACKET_NORMAL);
    if (packet == NULL) {
        printf("@NAME@: packet_init failed\n");
        SleepThread();
    }

    /* --- environment ------------------------------------------------- */
    q = packet->data;
    q = draw_setup_environment(q, 0, &frame, &z);
    q = draw_primitive_xyoffset(q, 0, OFF_X, OFF_Y);

    atest.enable = DRAW_ENABLE;
    atest.method = ATEST_METHOD_GREATER;
    atest.compval = 0x00;
    atest.keep = ATEST_KEEP_FRAMEBUFFER;
    dtest.enable = DRAW_DISABLE;
    dtest.pass = 0;
    ztest.enable = DRAW_DISABLE;
    ztest.method = ZTEST_METHOD_ALLPASS;
    q = draw_pixel_test(q, 0, &atest, &dtest, &ztest);

    lod.calculation = LOD_USE_K;
    lod.max_level = 0;
    lod.mag_filter = LOD_MAG_NEAREST;
    lod.min_filter = LOD_MIN_NEAREST;
    lod.l = 0;
    lod.k = 0;
    q = draw_texture_sampling(q, 0, &lod);

    clut.storage_mode = CLUT_STORAGE_MODE1;
    clut.start = 0;
    clut.psm = 0;
    clut.load_method = CLUT_NO_LOAD;
    clut.address = 0;
    q = draw_texturebuffer(q, 0, &logo_tex, &clut);

    q = draw_finish(q);
    dma_channel_send_normal(DMA_CHANNEL_GIF, packet->data,
                            q - packet->data, 0, 0);
    dma_wait_fast();

    /* --- upload ------------------------------------------------------- */
    /* The DMA reads main memory and knows nothing about the EE's cache, so
     * anything the CPU has touched has to be written back first. */
    FlushCache(0);

    q = packet->data;
    q = draw_texture_transfer(q, nc_logo, nc_logo_width, nc_logo_height,
                              GS_PSM_32, logo_tex.address, logo_tex.width);
    q = draw_texture_flush(q);
    dma_channel_send_chain(DMA_CHANNEL_GIF, packet->data,
                           q - packet->data, 0, 0);
    dma_wait_fast();

    printf("@NAME@: texture uploaded, entering the loop\n");

    while (1) {
        texrect_t r;

        q = packet->data;

        /* Mid blue: unmistakable, and impossible to confuse with a dead
         * console the way the near-black NC ground would be. */
        q = draw_clear(q, 0, OFF_X, OFF_Y, frame.width, frame.height,
                       0x20, 0x38, 0x70);

        r.v0.x = ftoi4(OFF_X + (SCREEN_W - width) / 2);
        r.v0.y = ftoi4(OFF_Y + (SCREEN_H - height) / 2);
        r.v0.z = 0;
        r.t0.u = 0.0f;
        r.t0.v = 0.0f;
        r.v1.x = ftoi4(OFF_X + (SCREEN_W + width) / 2);
        r.v1.y = ftoi4(OFF_Y + (SCREEN_H + height) / 2);
        r.v1.z = 0;
        r.t1.u = (float)nc_logo_used_w;
        r.t1.v = (float)nc_logo_used_h;
        r.color.r = r.color.g = r.color.b = 0x80;   /* 0x80 is neutral here */
        r.color.a = 0x80;
        r.color.q = 1.0f;
        q = draw_rect_textured(q, 0, &r);

        q = draw_finish(q);

        dma_wait_fast();
        dma_channel_send_normal(DMA_CHANNEL_GIF, packet->data,
                                q - packet->data, 0, 0);
        draw_wait_finish();
        graph_wait_vsync();

        if ((frames++ % 60) == 0)
            printf("@NAME@: frame %d\n", frames);
    }

    return 0;
}
