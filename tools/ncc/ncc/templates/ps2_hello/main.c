/*
 * @NAME@ - a Neon Coffee PlayStation 2 project
 *
 * This builds a real .elf. It is not the NC runtime -- that is M6 -- it is the
 * smallest thing that proves the PS2 path works end to end: toolchain, build,
 * and something on the television.
 *
 * The PS2 is not a faster PS1, which is why the runtime cannot simply be
 * ported. A 294 MHz MIPS core with two vector units, a real FPU, 32 MB of RAM,
 * 4 MB of VRAM -- and a GPU with a depth buffer, so the ordering table that the
 * whole PS1 renderer is built around has no counterpart here. Fixed-point 20.12
 * arithmetic stops being necessary. The GTE does not exist. That is a second
 * renderer, not a translation.
 *
 * Running it:
 *
 *   On hardware, with FreeMcBoot: copy game.elf to a USB stick and launch it
 *   from uLaunchELF or OPL's app list. No disc, no burning, no patching -- an
 *   ELF from USB is exactly what that setup is for.
 *
 *   In PCSX2: it needs a PS2 BIOS, which is copyrighted and has no open
 *   replacement the way OpenBIOS covers the PS1. Dump it from your own console
 *   -- FMCB ships a BIOS dumper -- and point PCSX2 at it.
 */

#include <kernel.h>
#include <stdio.h>
#include <tamtypes.h>

#include <dma.h>
#include <draw.h>
#include <graph.h>
#include <gs_psm.h>
#include <packet.h>

/* 640x448 is the safe NTSC full-screen mode. The PS1 runtime's 320x240 is a
 * quarter of this, which is the single most visible difference between the two
 * machines before a triangle is ever drawn. */
#define SCREEN_W 640
#define SCREEN_H 448

/* The Neon Coffee background, the same colour the PS1 side clears to. GS
 * colours are 0..255 per channel. */
#define CLEAR_R 0x14
#define CLEAR_G 0x18
#define CLEAR_B 0x1a


int main(void)
{
    framebuffer_t frame;
    zbuffer_t z;
    packet_t *packet;
    qword_t *q;
    int frames = 0;

    printf("@NAME@: Neon Coffee, PlayStation 2\n");

    frame.width = SCREEN_W;
    frame.height = SCREEN_H;
    frame.mask = 0;
    frame.psm = GS_PSM_32;
    frame.address = graph_vram_allocate(frame.width, frame.height, frame.psm,
                                        GRAPH_ALIGN_PAGE);

    /* No z-buffer. Nothing here is 3D yet, and allocating one would only take
     * VRAM to say so. */
    z.enable = DRAW_DISABLE;
    z.mask = 0;
    z.method = ZTEST_METHOD_ALLPASS;
    z.zsm = GS_ZBUF_32;
    z.address = 0;

    graph_initialize(frame.address, frame.width, frame.height, frame.psm, 0, 0);

    packet = packet_init(50, PACKET_NORMAL);

    q = packet->data;
    q = draw_setup_environment(q, 0, &frame, &z);
    q = draw_primitive_xyoffset(q, 0, 2048 - (frame.width / 2),
                                2048 - (frame.height / 2));
    q = draw_finish(q);
    dma_channel_send_normal(DMA_CHANNEL_GIF, packet->data,
                            q - packet->data, 0, 0);
    dma_wait_fast();

    while (1) {
        q = packet->data;
        q = draw_disable_tests(q, 0, &z);
        q = draw_clear(q, 0,
                       2048 - (frame.width / 2), 2048 - (frame.height / 2),
                       frame.width, frame.height,
                       CLEAR_R, CLEAR_G, CLEAR_B);
        q = draw_finish(q);

        dma_wait_fast();
        dma_channel_send_normal(DMA_CHANNEL_GIF, packet->data,
                                q - packet->data, 0, 0);
        draw_wait_finish();

        graph_wait_vsync();

        /* Once a second, so a TTY log shows it is alive rather than hung. */
        if ((frames++ % 60) == 0)
            printf("@NAME@: frame %d\n", frames);
    }

    packet_free(packet);
    return 0;
}
