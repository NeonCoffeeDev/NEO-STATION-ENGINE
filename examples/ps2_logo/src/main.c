/*
 * @NAME@ - the smallest possible PS2 texture test
 *
 * This exists to bisect a black screen, not to be a game.
 *
 * The first round told us a lot: NCPAD (an untextured box) runs, and this
 * cleared to blue but drew no logo. So the GS comes up, the frame loop runs,
 * DMA works, untextured rectangles work -- and only the textured quad shows
 * nothing.
 *
 * Two things could cause exactly that, and rather than guess again this draws
 * the same texture four times, differing only in those two:
 *
 *   TOP LEFT      texel coordinates (0..128),   alpha test on
 *   TOP RIGHT     normalised coordinates (0..1), alpha test on
 *   BOTTOM LEFT   texel coordinates,             alpha test off
 *   BOTTOM RIGHT  normalised coordinates,        alpha test off
 *
 * Whichever quadrant shows the logo is the answer. Each sits on its own dark
 * plate -- an untextured rectangle, which is already known to work -- so an
 * empty quadrant is visibly empty rather than merely blue.
 *
 * The leading suspect is the coordinate convention. texrect_t carries a union
 * that is both s/t and u/v, and if draw_rect_textured emits normalised ST then
 * feeding it 0..128 samples far off the edge of the texture; clamped, that is
 * the transparent border, which the alpha test then discards -- producing
 * precisely a clean blue screen.
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
        rect_t marker;
        int qw = 256, qh = 176;
        int col, row, variant;

        q = packet->data;
        q = draw_clear(q, 0, OFF_X, OFF_Y, frame.width, frame.height,
                       0x20, 0x38, 0x70);

        /* Four attempts at the same texture, differing only in the two things
         * that could plausibly be wrong. Whichever quadrant shows the logo is
         * the answer, and one boot settles it.
         *
         *   0  top left      texel coordinates,      alpha test on
         *   1  top right     normalised coordinates, alpha test on
         *   2  bottom left   texel coordinates,      alpha test off
         *   3  bottom right  normalised coordinates, alpha test off
         */
        for (variant = 0; variant < 4; variant++) {
            int normalised = variant & 1;
            int no_atest = variant & 2;
            int x, y;

            col = variant & 1;
            row = (variant >> 1) & 1;
            x = 32 + col * (qw + 64);
            y = 32 + row * (qh + 48);

            atest.enable = no_atest ? DRAW_DISABLE : DRAW_ENABLE;
            atest.method = ATEST_METHOD_GREATER;
            atest.compval = 0x00;
            atest.keep = ATEST_KEEP_FRAMEBUFFER;
            q = draw_pixel_test(q, 0, &atest, &dtest, &ztest);

            /* A dark plate behind each quadrant, so an empty one is obviously
             * empty rather than just blue. This is an untextured rect, which
             * NCPAD already proved works. */
            marker.v0.x = ftoi4(OFF_X + x - 4);
            marker.v0.y = ftoi4(OFF_Y + y - 4);
            marker.v0.z = 0;
            marker.v1.x = ftoi4(OFF_X + x + qw + 4);
            marker.v1.y = ftoi4(OFF_Y + y + qh + 4);
            marker.v1.z = 0;
            marker.color.r = 0x10 + variant * 0x08;
            marker.color.g = 0x10;
            marker.color.b = 0x18;
            marker.color.a = 0x80;
            marker.color.q = 1.0f;
            q = draw_rect_filled(q, 0, &marker);

            r.v0.x = ftoi4(OFF_X + x);
            r.v0.y = ftoi4(OFF_Y + y);
            r.v0.z = 0;
            r.v1.x = ftoi4(OFF_X + x + qw);
            r.v1.y = ftoi4(OFF_Y + y + qh);
            r.v1.z = 0;
            if (normalised) {
                r.t0.u = 0.0f;
                r.t0.v = 0.0f;
                r.t1.u = 1.0f;
                r.t1.v = 1.0f;
            } else {
                r.t0.u = 0.0f;
                r.t0.v = 0.0f;
                r.t1.u = (float)nc_logo_used_w;
                r.t1.v = (float)nc_logo_used_h;
            }
            r.color.r = r.color.g = r.color.b = 0x80;
            r.color.a = 0x80;
            r.color.q = 1.0f;
            q = draw_rect_textured(q, 0, &r);
        }

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
