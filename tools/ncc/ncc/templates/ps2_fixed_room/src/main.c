/* PS2 3D wireframe prototype. See README.md for capabilities. */
#include <math.h>
#include <kernel.h>
#include <stdio.h>
#include <string.h>
#include <tamtypes.h>

#include <dma.h>
#include <draw.h>
#include <draw2d.h>
#include <draw3d.h>
#include <graph.h>
#include <gs_psm.h>
#include <libpad.h>
#include <packet.h>
#include <sifrpc.h>
#include <loadfile.h>
#include "nc_materials.h"

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
static texbuffer_t material_tex[NC_MATERIAL_COUNT > 0 ? NC_MATERIAL_COUNT : 1];


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
#include "nc_room_layout.h"
static float player_x=ROOM_PLAYER_X, player_z=ROOM_PLAYER_Z, door_angle=0;
static int camera_id=0, has_key=0, door_open=0, won=0;
static float move_start_x, move_start_z, move_goal_x, move_goal_z;
static int move_frame, move_duration;
static int nc_move_arrived;
static void nc_move_to(float x, float z, int frames) {
    move_start_x=player_x;move_start_z=player_z;
    move_goal_x=x;move_goal_z=z;move_frame=0;move_duration=frames;
}
static void nc_action(int action, int value) {
    if(action==3) {move_duration=0;nc_move_arrived=0;}
    if(action==0) camera_id=value<0?0:(value>=ROOM_CAMERA_COUNT?ROOM_CAMERA_COUNT-1:value);
    if(action==2) {nc_move_arrived=0;move_duration=0;player_x=ROOM_PLAYER_X;player_z=ROOM_PLAYER_Z;camera_id=0;has_key=door_open=won=0;door_angle=0;}
    if(action==1) {
        if(!has_key && fabsf(player_x-ROOM_KEY_X)<0.8f && fabsf(player_z-ROOM_KEY_Z)<0.8f) has_key=1;
        if(has_key && fabsf(player_x-ROOM_DOOR_X)<0.9f && fabsf(player_z-ROOM_DOOR_Z)<1.0f) door_open=1;
    }
}
#include "nc_events.h"
static int project_point(float x,float y,float z,float *sx,float *sy) {
    const float *eye=room_camera_pos[camera_id],*target=room_camera_target[camera_id];
    float fx=target[0]-eye[0],fy=target[1]-eye[1],fz=target[2]-eye[2];
    float fl=sqrtf(fx*fx+fy*fy+fz*fz),rxv=-fz,rzv=fx,rl;
    float ux,uy,uz,dx=x-eye[0],dy=y-eye[1],dz=z-eye[2],rx,ry,depth,focal;
    if(fl<0.001f)return 0;fx/=fl;fy/=fl;fz/=fl;
    rl=sqrtf(rxv*rxv+rzv*rzv);if(rl<0.001f){rxv=1;rzv=0;rl=1;}rxv/=rl;rzv/=rl;
    ux=-fy*rzv;uy=fz*rxv-fx*rzv;uz=fy*rxv;
    rx=dx*rxv+dz*rzv;ry=dx*ux+dy*uy+dz*uz;depth=dx*fx+dy*fy+dz*fz;
    if(depth<0.3f)return 0;
    focal=224.0f/tanf(room_camera_fov[camera_id]*0.00872664626f);
    *sx=rx*focal/depth;*sy=-ry*focal/depth;return 1;
}

static void load_materials(void)
{
    int i;
    packet_t *upload = packet_init(64 + NC_MATERIAL_COUNT * 8, PACKET_NORMAL);
    qword_t *q;
    if (!upload) return;
    q = upload->data;
    for (i = 0; i < NC_MATERIAL_COUNT; i++) {
        material_tex[i].width = nc_materials[i].width;
        material_tex[i].psm = GS_PSM_32;
        material_tex[i].address = graph_vram_allocate(nc_materials[i].width,
            nc_materials[i].height, GS_PSM_32, GRAPH_ALIGN_BLOCK);
        material_tex[i].info.width = draw_log2(nc_materials[i].width);
        material_tex[i].info.height = draw_log2(nc_materials[i].height);
        material_tex[i].info.components = TEXTURE_COMPONENTS_RGBA;
        material_tex[i].info.function = TEXTURE_FUNCTION_MODULATE;
        q = draw_texture_transfer(q, nc_materials[i].pixels,
            nc_materials[i].width, nc_materials[i].height, GS_PSM_32,
            material_tex[i].address, material_tex[i].width);
    }
    q = draw_texture_flush(q);
    dma_channel_send_chain(DMA_CHANNEL_GIF, upload->data, q-upload->data, 0, 0);
    dma_wait_fast();
    packet_free(upload);
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
static qword_t *textured_box(qword_t *q,float x,float y,float z,float w,float h,float d,float angle,int material) {
    static const int faces[6][4]={{0,1,3,2},{4,5,7,6},{0,1,5,4},{2,3,7,6},{0,2,6,4},{1,3,7,5}};
    static const int tri[6]={0,1,2,0,2,3};
    float sx[8],sy[8];int good[8],i,f;
    prim_t prim={0};color_t color={0};clutbuffer_t clut={0};lod_t lod={0};
    if(material<0||material>=NC_MATERIAL_COUNT)return q;
    for(i=0;i<8;i++) {
        float vx=(i&1)?w:-w,vz=(i&4)?d:-d;
        good[i]=project_point(x+vx*cosf(angle)+vz*sinf(angle),y+((i&2)?h:-h),z-vx*sinf(angle)+vz*cosf(angle),&sx[i],&sy[i]);
    }
    lod.calculation=LOD_USE_K;lod.max_level=0;lod.mag_filter=LOD_MAG_NEAREST;lod.min_filter=LOD_MIN_NEAREST;
    clut.storage_mode=CLUT_STORAGE_MODE1;clut.load_method=CLUT_NO_LOAD;
    q=draw_texture_sampling(q,0,&lod);q=draw_texturebuffer(q,0,&material_tex[material],&clut);
    prim.type=PRIM_TRIANGLE;prim.shading=PRIM_SHADE_FLAT;prim.mapping=DRAW_ENABLE;
    prim.fogging=DRAW_DISABLE;prim.blending=DRAW_DISABLE;prim.antialiasing=DRAW_DISABLE;
    prim.mapping_type=PRIM_MAP_UV;prim.colorfix=PRIM_FIXED;
    color.a=0x80;color.q=1.0f;
    for(f=0;f<6;f++) {
        u64 *dw;
        if(!good[faces[f][0]]||!good[faces[f][1]]||!good[faces[f][2]]||!good[faces[f][3]])continue;
        color.r=color.g=color.b=(f==3?0x80:(f==5?0x68:0x50));
        dw=(u64*)draw_prim_start(q,0,&prim,&color);
        for(i=0;i<6;i++) {
            int corner=tri[i],vertex=faces[f][corner];
            int u=(corner==1||corner==2)?nc_materials[material].used_width-1:0;
            int v=(corner>=2)?nc_materials[material].used_height-1:0;
            xyz_t xyz;texel_t uv;
            uv.uv=(u64)ftoi4(u)|((u64)ftoi4(v)<<32);
            xyz.x=(u16)ftoi4(2048.0f+sx[vertex]);xyz.y=(u16)ftoi4(2048.0f+sy[vertex]);xyz.z=32;
            *dw++=uv.uv;*dw++=xyz.xyz;
        }
        q=draw_prim_end((qword_t*)dw,2,DRAW_UV_REGLIST);
    }
    return q;
}
int main(void) {
    framebuffer_t frame;zbuffer_t z;packet_t *packet;qword_t *q;
    struct padButtonStatus pad;unsigned int buttons=0,last=0,pressed;int tick=0,previous_zone=-1;
    dma_channel_initialize(DMA_CHANNEL_GIF,NULL,0);dma_channel_fast_waits(DMA_CHANNEL_GIF);
    load_pad_modules();padInit(0);padPortOpen(0,0,pad_buffer);
    packet=packet_init(2048,PACKET_NORMAL);if(!packet)return 1;
    init_screen(&frame,&z,packet);load_materials();nc_events(1,0,-1);
    for(;;) {
        int state=padGetState(0,0),zone,moving=0;
        buttons=0;
        if((state==PAD_STATE_STABLE||state==PAD_STATE_FINDCTP1)&&padRead(0,0,&pad)) buttons=0xffff^pad.btns;
        pressed=buttons&~last;last=buttons;
        nc_move_arrived=0;
        if (!won && move_duration>0) {
            float t=(float)(++move_frame)/(float)move_duration;
            player_x=move_start_x+(move_goal_x-move_start_x)*t;
            player_z=move_start_z+(move_goal_z-move_start_z)*t;
            moving=1;
            if(move_frame>=move_duration) {move_duration=0;nc_move_arrived=1;}
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
        if(door_angle>1.4f&&player_x>ROOM_DOOR_X+0.7f&&fabsf(player_z-ROOM_DOOR_Z)<0.6f)won=1;
        /* Wait before drawing into the single displayed buffer. A future
         * textured renderer should use explicit double buffering. */
        graph_wait_vsync();
        q=packet->data;q=draw_disable_tests(q,0,&z);
        q=draw_clear(q,0,OFFSET_X,OFFSET_Y,frame.width,frame.height,won?20:CLEAR_R,won?60:CLEAR_G,CLEAR_B);
        q=textured_box(q,0,-0.5f,0,3.2f,0.02f,2.2f,0,NC_MATERIAL_w_floor);
        q=textured_box(q,0,1.5f,2.2f,3.2f,2.0f,0.04f,0,NC_MATERIAL_w_back_wall);
        q=textured_box(q,-3.2f,1.0f,0,0.04f,1.5f,2.2f,0,NC_MATERIAL_w_side_wall);
        q=textured_box(q,player_x,moving?0.05f*sinf(tick*0.3f):0,player_z,0.22f,0.5f,0.22f,0,NC_MATERIAL_o_player);
        if(!has_key)q=textured_box(q,ROOM_KEY_X,0,ROOM_KEY_Z,0.15f,0.15f,0.15f,tick*0.03f,NC_MATERIAL_o_key);
        q=textured_box(q,ROOM_DOOR_X,0.3f,ROOM_DOOR_Z,0.08f,0.8f,0.65f,door_angle,NC_MATERIAL_o_door);
        q=draw_finish(q);dma_wait_fast();dma_channel_send_normal(DMA_CHANNEL_GIF,packet->data,q-packet->data,0,0);draw_wait_finish();tick++;
    }
}
