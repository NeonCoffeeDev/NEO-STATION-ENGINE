/*
 * @NAME@ - Neon Coffee on the PlayStation 2
 *
 * Something you can hold a controller and interact with, on real hardware.
 *
 *   D-pad / left stick   move the box
 *   X                    change its colour
 *   L1 / R1              resize it
 *   TRIANGLE             recentre
 *   START                reset everything
 *
 * This is not the NC runtime -- that is M6. It is the smallest thing that
 * proves the whole PS2 path works end to end: toolchain, build, display,
 * controller, and a frame loop that responds to you.
 *
 * The PS2 is not a faster PS1, which is why the runtime cannot simply be
 * ported. A 294 MHz core with two vector units, a real FPU, 32 MB of RAM, 4 MB
 * of VRAM, and a GPU with a depth buffer -- so the ordering table the whole PS1
 * renderer is built around has no counterpart, and fixed-point 20.12 stops
 * being necessary. That is a second renderer, not a translation.
 *
 * Running it, with FreeMcBoot:
 *
 *   Copy game.elf to a USB stick and launch it from uLaunchELF or OPL's app
 *   list. No disc, no burning, no patching. Format the stick FAT32.
 *
 *   In PCSX2 it also needs a PS2 BIOS dumped from your own console -- unlike
 *   the PS1 there is no open replacement for it.
 */

#include <kernel.h>
#include <stdio.h>
#include <string.h>
#include <tamtypes.h>

#include <dma.h>
#include <draw.h>
#include <draw2d.h>
#include <graph.h>
#include <gs_psm.h>
#include <libpad.h>
#include <packet.h>
#include <sifrpc.h>
#include <loadfile.h>

/* 640x448 is the safe NTSC full-screen mode. The PS1 runtime's 320x240 is a
 * quarter of this, which is the most visible difference between the two
 * machines before a single triangle is drawn. */
#define SCREEN_W 640
#define SCREEN_H 448

/* The GS addresses primitives in a 4096-wide space with the screen centred in
 * it, so every on-screen coordinate carries this offset. */
#define OFFSET_X (2048 - (SCREEN_W / 2))
#define OFFSET_Y (2048 - (SCREEN_H / 2))

/* The Neon Coffee ground, the same colour the PS1 side clears to. */
#define CLEAR_R 0x14
#define CLEAR_G 0x18
#define CLEAR_B 0x1a

#define BOX_MIN 16
#define BOX_MAX 320
#define SPEED    4

/* The pad driver DMAs into this, so it has to be 64-byte aligned and it must
 * not be in the stack frame. */
static char pad_buffer[256] __attribute__((aligned(64)));

/* A handful of colours to cycle through with X. Cyan, amber, green, magenta --
 * the NC Studio accents, so the two look like the same product. */
static const unsigned char palette[][3] = {
    { 0x5f, 0xd4, 0xd0 },
    { 0xff, 0xb0, 0x3a },
    { 0x7f, 0xd9, 0x8c },
    { 0xff, 0x6b, 0x5e },
};
#define PALETTE_COUNT (int)(sizeof(palette) / sizeof(palette[0]))


static void load_pad_modules(void)
{
    /* Both of these live in the console's ROM, so nothing has to be shipped
     * alongside the ELF. The IOP is a separate processor with its own memory:
     * the controller is its hardware, and the EE talks to it over RPC. */
    SifInitRpc(0);
    /* Console models disagree about the names: later ones ship the X variants.
     * Trying the plain pair first and falling back costs nothing and is the
     * difference between working on your console and working on mine. */
    if (SifLoadModule("rom0:SIO2MAN", 0, NULL) < 0)
        SifLoadModule("rom0:XSIO2MAN", 0, NULL);
    if (SifLoadModule("rom0:PADMAN", 0, NULL) < 0)
        SifLoadModule("rom0:XPADMAN", 0, NULL);
}


static int wait_pad_ready(int port, int slot)
{
    int state;
    /* padGetState reports what the driver is doing with the port. Reading
     * buttons before it settles gives you garbage, and a controller unplugged
     * mid-session lands in DISCONN rather than hanging. */
    do {
        state = padGetState(port, slot);
        if (state == PAD_STATE_DISCONN)
            return 0;
    } while (state != PAD_STATE_STABLE && state != PAD_STATE_FINDCTP1);
    return 1;
}


static void init_screen(framebuffer_t *frame, zbuffer_t *z, packet_t *packet)
{
    qword_t *q;

    frame->width = SCREEN_W;
    frame->height = SCREEN_H;
    frame->mask = 0;
    frame->psm = GS_PSM_32;
    frame->address = graph_vram_allocate(frame->width, frame->height,
                                         frame->psm, GRAPH_ALIGN_PAGE);

    /* No z-buffer. Nothing here is 3D, and allocating one would only spend
     * VRAM to say so. */
    z->enable = DRAW_DISABLE;
    z->mask = 0;
    z->method = ZTEST_METHOD_ALLPASS;
    z->zsm = GS_ZBUF_32;
    z->address = 0;

    graph_initialize(frame->address, frame->width, frame->height,
                     frame->psm, 0, 0);

    q = packet->data;
    q = draw_setup_environment(q, 0, frame, z);
    q = draw_primitive_xyoffset(q, 0, OFFSET_X, OFFSET_Y);
    q = draw_finish(q);
    dma_channel_send_normal(DMA_CHANNEL_GIF, packet->data,
                            q - packet->data, 0, 0);
    dma_wait_fast();
}


int main(void)
{
    framebuffer_t frame;
    zbuffer_t z;
    packet_t *packet;
    qword_t *q;

    struct padButtonStatus pad;
    unsigned int buttons = 0, last = 0, pressed;
    int have_pad;

    int x = SCREEN_W / 2, y = SCREEN_H / 2;
    int size = 96;
    int colour = 0;
    int frames = 0;

    printf("@NAME@: Neon Coffee, PlayStation 2\n");
    printf("@NAME@: d-pad moves, X recolours, L1/R1 resize, START resets\n");

    load_pad_modules();
    padInit(0);
    padPortOpen(0, 0, pad_buffer);
    have_pad = wait_pad_ready(0, 0);
    if (!have_pad)
        printf("@NAME@: no controller in port 1 -- the box will just sit there\n");

    packet = packet_init(60, PACKET_NORMAL);
    init_screen(&frame, &z, packet);

    while (1) {
        if (have_pad && padRead(0, 0, &pad) != 0) {
            /* Buttons are reported active-low, so invert to get the friendlier
             * 1 = pressed. Same convention as the PS1 side. */
            buttons = 0xFFFF ^ pad.btns;
        }
        pressed = buttons & ~last;
        last = buttons;

        if (buttons & PAD_LEFT)  x -= SPEED;
        if (buttons & PAD_RIGHT) x += SPEED;
        if (buttons & PAD_UP)    y -= SPEED;
        if (buttons & PAD_DOWN)  y += SPEED;

        if (pressed & PAD_CROSS)
            colour = (colour + 1) % PALETTE_COUNT;
        if (buttons & PAD_R1)
            size += 2;
        if (buttons & PAD_L1)
            size -= 2;
        if (pressed & PAD_TRIANGLE) {
            x = SCREEN_W / 2;
            y = SCREEN_H / 2;
        }
        if (pressed & PAD_START) {
            x = SCREEN_W / 2;
            y = SCREEN_H / 2;
            size = 96;
            colour = 0;
        }

        if (size < BOX_MIN) size = BOX_MIN;
        if (size > BOX_MAX) size = BOX_MAX;
        if (x < size / 2) x = size / 2;
        if (x > SCREEN_W - size / 2) x = SCREEN_W - size / 2;
        if (y < size / 2) y = size / 2;
        if (y > SCREEN_H - size / 2) y = SCREEN_H - size / 2;

        q = packet->data;
        q = draw_disable_tests(q, 0, &z);
        q = draw_clear(q, 0, OFFSET_X, OFFSET_Y, frame.width, frame.height,
                       CLEAR_R, CLEAR_G, CLEAR_B);

        {
            rect_t box;
            /* Coordinates are fixed point with four fractional bits, which is
             * what ftoi4 is for. Passing raw pixels here draws the box at a
             * sixteenth of its size, which is a confusing first bug to hit. */
            box.v0.x = ftoi4(OFFSET_X + x - size / 2);
            box.v0.y = ftoi4(OFFSET_Y + y - size / 2);
            box.v0.z = 0;
            box.v1.x = ftoi4(OFFSET_X + x + size / 2);
            box.v1.y = ftoi4(OFFSET_Y + y + size / 2);
            box.v1.z = 0;
            box.color.r = palette[colour][0];
            box.color.g = palette[colour][1];
            box.color.b = palette[colour][2];
            box.color.a = 0x80;              /* 0x80 is opaque on this hardware */
            box.color.q = 1.0f;
            q = draw_rect_filled(q, 0, &box);
        }

        q = draw_finish(q);

        dma_wait_fast();
        dma_channel_send_normal(DMA_CHANNEL_GIF, packet->data,
                                q - packet->data, 0, 0);
        draw_wait_finish();
        graph_wait_vsync();

        /* Once a second, so a TTY log shows it alive rather than hung. */
        if ((frames++ % 60) == 0)
            printf("@NAME@: frame %d  box %d,%d size %d\n", frames, x, y, size);
    }

    packet_free(packet);
    return 0;
}
