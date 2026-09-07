/* Diagnostic: cycling background with a centred 200-pixel white square.
 * Hardware validation is pending. A static screen alone does not identify the cause.
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
#define OFF_X (-(SCREEN_W / 2))
#define OFF_Y (-(SCREEN_H / 2))

static const unsigned char CYCLE[4][3] = {
    { 0xE0, 0x20, 0x20 },   /* red   */
    { 0x20, 0xE0, 0x40 },   /* green */
    { 0x20, 0x40, 0xE0 },   /* blue  */
    { 0xFF, 0xB0, 0x3A },   /* amber */
};


int main(void)
{
    framebuffer_t frame;
    zbuffer_t z;
    packet_t *packet;
    qword_t *q;
    int frames = 0;

    /* Initialize GIF and select it for dma_wait_fast, as in PS2SDK samples. */
    dma_channel_initialize(DMA_CHANNEL_GIF, NULL, 0);
    dma_channel_fast_waits(DMA_CHANNEL_GIF);

    printf("@NAME@: starting\n");

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

    graph_initialize(frame.address, frame.width, frame.height, frame.psm, 0, 0);

    packet = packet_init(256, PACKET_NORMAL);
    if (packet == NULL) {
        printf("@NAME@: packet_init failed\n");
        return 1;
    }

    q = packet->data;
    q = draw_setup_environment(q, 0, &frame, &z);
    q = draw_primitive_xyoffset(q, 0, 2048 + OFF_X, 2048 + OFF_Y);
    q = draw_finish(q);
    dma_channel_send_normal(DMA_CHANNEL_GIF, packet->data,
                            q - packet->data, 0, 0);
    dma_wait_fast();

    printf("@NAME@: environment up, entering the loop\n");

    while (1) {
        const unsigned char *c = CYCLE[(frames / 60) % 4];
        rect_t square;

        q = packet->data;
        q = draw_disable_tests(q, 0, &z);
        q = draw_clear(q, 0, OFF_X, OFF_Y, frame.width, frame.height,
                       c[0], c[1], c[2]);

        /* Exactly the coordinates draw_clear was just given, so if the clear
         * lands and this does not, the difference is the call and nothing
         * else. */
        square.v0.x = (float)(OFF_X + 220);
        square.v0.y = (float)(OFF_Y + 124);
        square.v0.z = 0;
        square.v1.x = (float)(OFF_X + 420);
        square.v1.y = (float)(OFF_Y + 324);
        square.v1.z = 0;
        square.color.r = 0xF0;
        square.color.g = 0xF0;
        square.color.b = 0xF0;
        square.color.a = 0x80;
        square.color.q = 1.0f;
        q = draw_rect_filled(q, 0, &square);

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
