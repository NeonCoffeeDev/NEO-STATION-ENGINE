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



/* Object animation and fixed-camera adapter. Wireframe geometry is intentional:
 * no hidden-surface or skeletal-animation support is implied by this test. */
static float player_x=-2, player_z=0, door_angle=0;
static int camera_id=0, has_key=0, door_open=0, won=0;
static float move_start_x, move_start_z, move_goal_x, move_goal_z;
static int move_frame, move_duration;
static void nc_move_to(float x, float z, int frames) {
    move_start_x=player_x;move_start_z=player_z;
    move_goal_x=x;move_goal_z=z;move_frame=0;move_duration=frames;
}
static void nc_action(int action, int value) {
    if(action==0) camera_id=value;
    if(action==2) {move_duration=0;player_x=-2;player_z=0;camera_id=0;has_key=door_open=won=0;door_angle=0;}
    if(action==1) {
        if(!has_key && fabsf(player_x+2)<0.8f && fabsf(player_z-1.5f)<0.8f) has_key=1;
        if(has_key && fabsf(player_x-2)<0.9f && fabsf(player_z)<1.0f) door_open=1;
    }
}
#include "nc_events.h"
static int project_point(float x,float y,float z,float *sx,float *sy) {
    static const float yaw[3]={0.45f,-0.65f,0.0f};
    float a=yaw[camera_id],rx=x*cosf(a)+z*sinf(a),rz=-x*sinf(a)+z*cosf(a);
    float pitch=0.5f,ry=y*cosf(pitch)-rz*sinf(pitch);
    float depth=y*sinf(pitch)+rz*cosf(pitch)+10;
    if(depth<0.3f)return 0;
    *sx=rx*430/depth;*sy=-ry*430/depth;return 1;
}
static qword_t *wire(qword_t *q,float x,float y,float z,float w,float h,float d,float angle,int color) {
    static const int edges[12][2]={{0,1},{1,3},{3,2},{2,0},{4,5},{5,7},{7,6},{6,4},{0,4},{1,5},{2,6},{3,7}};
    float sx[8],sy[8];int good[8],i;
    for(i=0;i<8;i++) {
        float vx=(i&1)?w:-w,vz=(i&4)?d:-d;
        good[i]=project_point(x+vx*cosf(angle)+vz*sinf(angle),y+((i&2)?h:-h),z-vx*sinf(angle)+vz*cosf(angle),&sx[i],&sy[i]);
    }
    for(i=0;i<12;i++) {
        int a=edges[i][0],b=edges[i][1];line_t line={0};
        if(!good[a]||!good[b])continue;
        line.v0.x=sx[a];line.v0.y=sy[a];line.v1.x=sx[b];line.v1.y=sy[b];
        line.color.r=palette[color][0];line.color.g=palette[color][1];line.color.b=palette[color][2];line.color.a=0x80;line.color.q=1;
        q=draw_line(q,0,&line);
    }
    return q;
}
int main(void) {
    framebuffer_t frame;zbuffer_t z;packet_t *packet;qword_t *q;
    struct padButtonStatus pad;unsigned int buttons=0,last=0,pressed;int tick=0,previous_zone=-1;
    dma_channel_initialize(DMA_CHANNEL_GIF,NULL,0);dma_channel_fast_waits(DMA_CHANNEL_GIF);
    load_pad_modules();padInit(0);padPortOpen(0,0,pad_buffer);
    packet=packet_init(2048,PACKET_NORMAL);if(!packet)return 1;
    init_screen(&frame,&z,packet);nc_events(1,0,-1);
    for(;;) {
        int state=padGetState(0,0),zone,moving=0;
        buttons=0;
        if((state==PAD_STATE_STABLE||state==PAD_STATE_FINDCTP1)&&padRead(0,0,&pad)) buttons=0xffff^pad.btns;
        pressed=buttons&~last;last=buttons;
        if (!won && move_duration>0) {
            float t=(float)(++move_frame)/(float)move_duration;
            player_x=move_start_x+(move_goal_x-move_start_x)*t;
            player_z=move_start_z+(move_goal_z-move_start_z)*t;
            moving=1;
            if(move_frame>=move_duration) move_duration=0;
        } else if(!won) {
            if(buttons&PAD_LEFT){player_x-=0.045f;moving=1;}
            if(buttons&PAD_RIGHT){player_x+=0.045f;moving=1;}
            if(buttons&PAD_UP){player_z+=0.045f;moving=1;}
            if(buttons&PAD_DOWN){player_z-=0.045f;moving=1;}
        }
        if(player_x< -3)player_x=-3;if(player_x>3)player_x=3;
        if(player_z< -2)player_z=-2;if(player_z>2)player_z=2;
        zone=player_x>0?1:0;
        nc_events(0,pressed,zone!=previous_zone?zone:-1);previous_zone=zone;
        if(door_open&&door_angle<1.5f)door_angle+=0.025f;
        if(door_angle>1.4f&&player_x>2.7f&&fabsf(player_z)<0.6f)won=1;
        /* Wait before drawing into the single displayed buffer. A future
         * textured renderer should use explicit double buffering. */
        graph_wait_vsync();
        q=packet->data;q=draw_disable_tests(q,0,&z);
        q=draw_clear(q,0,OFFSET_X,OFFSET_Y,frame.width,frame.height,won?20:CLEAR_R,won?60:CLEAR_G,CLEAR_B);
        q=wire(q,0,-0.5f,0,3.2f,0.02f,2.2f,0,0);
        q=wire(q,player_x,moving?0.05f*sinf(tick*0.3f):0,player_z,0.22f,0.5f,0.22f,0,2);
        if(!has_key)q=wire(q,-2,0,1.5f,0.15f,0.15f,0.15f,tick*0.03f,1);
        q=wire(q,2,0.3f,0,0.08f,0.8f,0.65f,door_angle,has_key?2:3);
        q=draw_finish(q);dma_wait_fast();dma_channel_send_normal(DMA_CHANNEL_GIF,packet->data,q-packet->data,0,0);draw_wait_finish();tick++;
    }
}
