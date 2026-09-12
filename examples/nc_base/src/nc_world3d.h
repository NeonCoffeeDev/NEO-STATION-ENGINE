/* Shared starter PS2 world pass. Authored data comes from world3d.json. */
#pragma once
#include <math.h>
#include "nc_materials.h"

/* A 640x448 buffer is stretched to a 4:3 television, so the picture is
 * squeezed horizontally on the way out: 640/448 is 1.4286 but the screen is
 * 1.3333. Drawing 1/0.9333 wider in buffer pixels cancels it, and a cube
 * authored as a cube arrives as a cube. Every squeeze correction lives here,
 * on the side that actually has non-square pixels -- NC Studio's viewport
 * draws a plain 4:3 rectangle and needs no factor of its own. */
#define NC_PIXEL_ASPECT 1.0714286f

static texbuffer_t nc_world_tex[NC_MATERIAL_COUNT > 0 ? NC_MATERIAL_COUNT : 1];

static void nc_world_upload(void) {
    int i;
    for(i=0;i<NC_MATERIAL_COUNT;i++) {
        packet_t *upload; qword_t *q;
        /* draw_texture_transfer writes the pixels themselves into the packet,
         * so the packet has to be as large as the texture plus its GIF tags.
         * Sizing it by material count instead pushed a 128x128 texture --
         * 4096 quadwords -- through a 72 quadword buffer, which is how a
         * textured cube became a flat wrong colour and why memory after the
         * packet was being written through. */
        int qwords = (nc_materials[i].width * nc_materials[i].height) / 4 + 64;
        nc_world_tex[i].width=nc_materials[i].width;nc_world_tex[i].psm=GS_PSM_32;
        nc_world_tex[i].address=graph_vram_allocate(nc_materials[i].width,nc_materials[i].height,GS_PSM_32,GRAPH_ALIGN_BLOCK);
        nc_world_tex[i].info.width=draw_log2(nc_materials[i].width);nc_world_tex[i].info.height=draw_log2(nc_materials[i].height);
        nc_world_tex[i].info.components=TEXTURE_COMPONENTS_RGBA;nc_world_tex[i].info.function=TEXTURE_FUNCTION_MODULATE;
        upload=packet_init(qwords,PACKET_NORMAL);
        if(!upload) continue;
        FlushCache(0);
        q=upload->data;
        q=draw_texture_transfer(q,nc_materials[i].pixels,nc_materials[i].width,nc_materials[i].height,GS_PSM_32,nc_world_tex[i].address,nc_world_tex[i].width);
        q=draw_texture_flush(q);
        dma_channel_send_chain(DMA_CHANNEL_GIF,upload->data,q-upload->data,0,0);
        dma_wait_fast();
        packet_free(upload);
    }
}

/* The six faces of the unit box, and the outward normal of each. Face n's
 * normal is constant in object space, so lighting is six dot products per
 * object rather than one per pixel -- which is the only kind this console
 * gives away for free. */
static const int nc_faces[6][4]={{0,1,3,2},{4,5,7,6},{0,1,5,4},{2,3,7,6},{0,2,6,4},{1,3,7,5}};
static const float nc_face_normal[6][3]={{0,0,-1},{0,0,1},{0,-1,0},{0,1,0},{-1,0,0},{1,0,0}};

/* How lit each face of the current object is, 0..1. Filled per object by
 * nc_world_shade so the face loop can stay a straight run of primitives. */
static float nc_face_light[6];

static void nc_world_shade(int object) {
    float ax=nc_world_rot[object][0]*0.01745329252f;
    float ay=nc_world_rot[object][1]*0.01745329252f;
    float az=nc_world_rot[object][2]*0.01745329252f;
    int f,l;
    for(f=0;f<6;f++) {
        float nx=nc_face_normal[f][0],ny=nc_face_normal[f][1],nz=nc_face_normal[f][2],tx,ty,tz,lit;
        /* Same rotation order the vertices use, so a normal never disagrees
         * with the face it belongs to. */
        ty=ny*cosf(ax)-nz*sinf(ax);tz=ny*sinf(ax)+nz*cosf(ax);ny=ty;nz=tz;
        tx=nx*cosf(ay)+nz*sinf(ay);tz=-nx*sinf(ay)+nz*cosf(ay);nx=tx;nz=tz;
        tx=nx*cosf(az)-ny*sinf(az);ty=nx*sinf(az)+ny*cosf(az);nx=tx;ny=ty;
        lit=NC_WORLD_AMBIENT;
        for(l=0;l<NC_WORLD_LIGHT_COUNT;l++) {
            float d=nx*nc_world_light_dir[l][0]+ny*nc_world_light_dir[l][1]+nz*nc_world_light_dir[l][2];
            if(d>0) lit+=d*nc_world_light_power[l];
        }
        nc_face_light[f]=lit<0.f?0.f:(lit>1.f?1.f:lit);
    }
}

static qword_t *nc_world_cube(qword_t *q,float *px,float *py,float *depth,int *visible,int material) {
    static const int tri[6]={0,1,2,0,2,3};
    prim_t prim={0};color_t color={0};clutbuffer_t clut={0};lod_t lod={0};int f,i,order[6]={0,1,2,3,4,5};float face_depth[6];
    if(material<0||material>=NC_MATERIAL_COUNT)return q;
    lod.calculation=LOD_USE_K;lod.mag_filter=LOD_MAG_NEAREST;lod.min_filter=LOD_MIN_NEAREST;clut.storage_mode=CLUT_STORAGE_MODE1;clut.load_method=CLUT_NO_LOAD;
    q=draw_texture_sampling(q,0,&lod);q=draw_texturebuffer(q,0,&nc_world_tex[material],&clut);
    prim.type=PRIM_TRIANGLE;prim.shading=PRIM_SHADE_FLAT;prim.mapping=DRAW_ENABLE;prim.mapping_type=PRIM_MAP_UV;prim.colorfix=PRIM_FIXED;color.a=0x80;color.q=1.0f;
    for(f=0;f<6;f++)face_depth[f]=(depth[nc_faces[f][0]]+depth[nc_faces[f][1]]+depth[nc_faces[f][2]]+depth[nc_faces[f][3]])*.25f;
    for(i=0;i<5;i++)for(f=i+1;f<6;f++)if(face_depth[order[i]]<face_depth[order[f]]){int swap=order[i];order[i]=order[f];order[f]=swap;}
    for(i=0;i<6;i++){u64 *dw;int shade;f=order[i];if(!visible[nc_faces[f][0]]||!visible[nc_faces[f][1]]||!visible[nc_faces[f][2]]||!visible[nc_faces[f][3]])continue;
        /* 0x80 is full brightness through MODULATE, not 0xFF. */
        shade=(int)(nc_face_light[f]*128.f);if(shade>0x80)shade=0x80;
        color.r=color.g=color.b=shade;dw=(u64*)draw_prim_start(q,0,&prim,&color);
        {int n;for(n=0;n<6;n++){int corner=tri[n],v=nc_faces[f][corner];int u=(corner==1||corner==2)?nc_materials[material].used_width-1:0;int t=corner>=2?nc_materials[material].used_height-1:0;texel_t uv;xyz_t xyz;
            uv.uv=(u64)ftoi4(u)|((u64)ftoi4(t)<<32);xyz.x=(u16)ftoi4(2048+px[v]);xyz.y=(u16)ftoi4(2048+py[v]);xyz.z=32;*dw++=uv.uv;*dw++=xyz.xyz;}}
        q=draw_prim_end((qword_t*)dw,2,DRAW_UV_REGLIST);
    }return q;
}

static qword_t *nc_world_draw(qword_t *q) {
    const float camera_pos[3]=NC_WORLD_CAMERA_POS,camera_target[3]=NC_WORLD_CAMERA_TARGET;
    float dx=camera_target[0]-camera_pos[0],dy=camera_target[1]-camera_pos[1],dz=camera_target[2]-camera_pos[2];
    float yaw=-atan2f(dx,dz),pitch=atan2f(dy,sqrtf(dx*dx+dz*dz));int object,i;
    for(object=0;object<NC_WORLD_OBJECT_COUNT;object++){
        float px[8],py[8],depths[8];int visible[8];
        nc_world_shade(object);
        for(i=0;i<8;i++){float vx=(i&1)?1:-1,vy=(i&2)?1:-1,vz=(i&4)?1:-1,tx,ty,tz;
            float ax=nc_world_rot[object][0]*0.01745329252f,ay=nc_world_rot[object][1]*0.01745329252f,az=nc_world_rot[object][2]*0.01745329252f;
            vx*=nc_world_scale[object][0];vy*=nc_world_scale[object][1];vz*=nc_world_scale[object][2];
            ty=vy*cosf(ax)-vz*sinf(ax);tz=vy*sinf(ax)+vz*cosf(ax);vy=ty;vz=tz;tx=vx*cosf(ay)+vz*sinf(ay);tz=-vx*sinf(ay)+vz*cosf(ay);vx=tx;vz=tz;tx=vx*cosf(az)-vy*sinf(az);ty=vx*sinf(az)+vy*cosf(az);vx=tx;vy=ty;
            vx+=nc_world_pos[object][0]-camera_pos[0];vy+=nc_world_pos[object][1]-camera_pos[1];vz+=nc_world_pos[object][2]-camera_pos[2];
            {float rx=vx*cosf(yaw)+vz*sinf(yaw),rz=-vx*sinf(yaw)+vz*cosf(yaw),ry=vy*cosf(pitch)-rz*sinf(pitch),depth=vy*sinf(pitch)+rz*cosf(pitch);float focal=((float)SCREEN_H*.5f)/tanf(NC_WORLD_CAMERA_FOV*0.00872664626f);
             visible[i]=depth>=0.3f;depths[i]=depth;if(visible[i]){px[i]=rx*focal*NC_PIXEL_ASPECT/depth;py[i]=-ry*focal/depth;}}
        }
        q=nc_world_cube(q,px,py,depths,visible,nc_world_material[object]);
    }return q;
}
