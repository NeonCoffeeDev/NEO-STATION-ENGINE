/* PS2 3D wireframe prototype. See README.md for capabilities. */
#include <math.h>
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

/* libdraw adds the GS origin internally. Convert screen pixels to centred
 * coordinates here; only XYOFFSET receives the 2048 hardware origin. */
#define OFFSET_X (-(SCREEN_W / 2))
#define OFFSET_Y (-(SCREEN_H / 2))

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
    q = draw_primitive_xyoffset(q, 0, 2048 + OFFSET_X, 2048 + OFFSET_Y);
    q = draw_finish(q);
    dma_channel_send_normal(DMA_CHANNEL_GIF, packet->data,
                            q - packet->data, 0, 0);
    dma_wait_fast();
}


#include "nc_objects.h"
static int nc_palette_override = -1;
static void nc_action(int action,int value) {
    if(action==5) nc_palette_override=value;
    if(action==2) { memcpy(nc_object_pos,nc_object_initial,sizeof(nc_object_pos));nc_palette_override=-1; }
}
#include "nc_events.h"

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
    const float camera_pos[3] = NC_GAME_CAMERA_POS;
    const float camera_target[3] = NC_GAME_CAMERA_TARGET;
    float dx=camera_target[0]-camera_pos[0];
    float dy=camera_target[1]-camera_pos[1];
    float dz=camera_target[2]-camera_pos[2];
    float camera_yaw=-atan2f(dx,dz);
    float camera_pitch=atan2f(dy,sqrtf(dx*dx+dz*dz));
    float yaw = camera_yaw, pitch = camera_pitch;

    /* Initialize GIF and select it for dma_wait_fast, as in PS2SDK samples. */
    dma_channel_initialize(DMA_CHANNEL_GIF, NULL, 0);
    dma_channel_fast_waits(DMA_CHANNEL_GIF);

    printf("ps2_3d_lab: Neon Coffee, PlayStation 2\n");
    printf("ps2_3d_lab: d-pad moves, X recolours, L1/R1 resize, START resets\n");

    load_pad_modules();
    padInit(0);
    padPortOpen(0, 0, pad_buffer);
    have_pad = wait_pad_ready(0, 0);
    if (!have_pad)
        printf("ps2_3d_lab: no controller in port 1 -- the box will just sit there\n");

    packet = packet_init(2048, PACKET_NORMAL);
    if (packet == NULL) return 1;
    init_screen(&frame, &z, packet);
    nc_events(1,0,-1);

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

        nc_events(0,pressed,-1);
        if(nc_palette_override>=0) colour=nc_palette_override;
        q = packet->data;
        q = draw_disable_tests(q, 0, &z);
        q = draw_clear(q, 0, OFFSET_X, OFFSET_Y, frame.width, frame.height,
                       CLEAR_R, CLEAR_G, CLEAR_B);

        /* CPU perspective projection: a small wireframe 3D bring-up scene.
         * D-pad orbits, shoulders zoom, X changes colour, START resets.
         * No depth buffer or hidden-line removal is claimed by this test.
         */
        {
            static const int edges[12][2] = {
                {0,1},{1,3},{3,2},{2,0},{4,5},{5,7},{7,6},{6,4},
                {0,4},{1,5},{2,6},{3,7}
            };
            float px[8], py[8];
            int i,object;
            if (buttons & PAD_LEFT) yaw -= 0.035f;
            if (buttons & PAD_RIGHT) yaw += 0.035f;
            if (buttons & PAD_UP) pitch -= 0.035f;
            if (buttons & PAD_DOWN) pitch += 0.035f;
            if (pressed & PAD_START) { yaw = camera_yaw; pitch = camera_pitch; }
            for(object=0;object<NC_OBJECT_COUNT;object++) {
            int visible[8];
            for (i=0;i<8;i++) {
                float vx=(i&1)?1.0f:-1.0f, vy=(i&2)?1.0f:-1.0f;
                float vz=(i&4)?1.0f:-1.0f;
                float ax=nc_object_rot[object][0]*0.01745329252f;
                float ay=nc_object_rot[object][1]*0.01745329252f;
                float az=nc_object_rot[object][2]*0.01745329252f;
                float tx,ty,tz;
                vx*=nc_object_scale[object][0];
                vy*=nc_object_scale[object][1];
                vz*=nc_object_scale[object][2];
                ty=vy*cosf(ax)-vz*sinf(ax);tz=vy*sinf(ax)+vz*cosf(ax);vy=ty;vz=tz;
                tx=vx*cosf(ay)+vz*sinf(ay);tz=-vx*sinf(ay)+vz*cosf(ay);vx=tx;vz=tz;
                tx=vx*cosf(az)-vy*sinf(az);ty=vx*sinf(az)+vy*cosf(az);vx=tx;vy=ty;
                float focal=((float)SCREEN_H*.5f)/tanf(NC_GAME_CAMERA_FOV*0.00872664626f);
                vx+=nc_object_pos[object][0]-camera_pos[0];
                vy+=nc_object_pos[object][1]-camera_pos[1];
                vz+=nc_object_pos[object][2]-camera_pos[2];
                float rx=vx*cosf(yaw)+vz*sinf(yaw);
                float rz=-vx*sinf(yaw)+vz*cosf(yaw);
                float ry=vy*cosf(pitch)-rz*sinf(pitch);
                float depth=vy*sinf(pitch)+rz*cosf(pitch);
                visible[i]=depth>=0.3f;
                if(!visible[i])continue;
                px[i]=rx*(focal*((float)size/96.0f))/depth;
                py[i]=ry*(focal*((float)size/96.0f))/depth;
            }
            for(i=0;i<12;i++) {
                line_t line = {0};
                int a=edges[i][0], b=edges[i][1];
                if(!visible[a]||!visible[b])continue;
                line.v0.x=px[a]; line.v0.y=py[a];
                line.v1.x=px[b]; line.v1.y=py[b];
                line.color.r=palette[colour][0];
                line.color.g=palette[colour][1];
                line.color.b=palette[colour][2];
                line.color.a=0x80; line.color.q=1.0f;
                q=draw_line(q,0,&line);
            }
            } /* all placed objects */
        }
        q = draw_finish(q);

        dma_wait_fast();
        dma_channel_send_normal(DMA_CHANNEL_GIF, packet->data,
                                q - packet->data, 0, 0);
        draw_wait_finish();
        graph_wait_vsync();

        /* Once a second, so a TTY log shows it alive rather than hung. */
        if ((frames++ % 60) == 0)
            printf("ps2_3d_lab: frame %d  box %d,%d size %d\n", frames, x, y, size);
    }

    packet_free(packet);
    return 0;
}
