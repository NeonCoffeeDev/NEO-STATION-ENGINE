/* Shared starter PS2 world pass. Authored data comes from world3d.json.
 *
 * The world is compiled into arrays by ps2materials, and then copied into a
 * mutable list at startup. Authored data says where things begin; it is not
 * where they stay. Spawning, moving and re-materialising objects at runtime is
 * the whole point of an engine, and a renderer that can only draw the arrays
 * the compiler emitted cannot be one.
 */
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

#define NC_WORLD_MAX 24
#define NC_DEG 0.01745329252f

/* Depth written per vertex, for the 16-bit depth buffer. Larger is nearer --
 * the GS test is GREATER -- and the value is 1/z rather than z, which spends
 * the sixteen bits on the distances a player is close enough to notice. */
#define NC_Z_NEAR 0.3f
static unsigned int nc_depth_value(float depth)
{
    float value = 65535.f * NC_Z_NEAR / depth;
    if (value >= 65535.f) return 65535u;
    if (value <= 1.f) return 1u;
    return (unsigned int)value;
}

/* The depth test belongs to the world pass alone. Everything 2D is drawn
 * afterwards at one depth and would fight it, so the pass switches the test on
 * when it starts and hands it back the way it found it. */
static qword_t *nc_depth_test(qword_t *q, int method)
{
    atest_t atest; dtest_t dtest; ztest_t ztest;
    atest.enable = DRAW_ENABLE; atest.method = ATEST_METHOD_GREATER;
    atest.compval = 0x00; atest.keep = ATEST_KEEP_FRAMEBUFFER;
    dtest.enable = DRAW_DISABLE; dtest.pass = 0;
    ztest.enable = DRAW_ENABLE; ztest.method = method;
    return draw_pixel_test(q, 0, &atest, &dtest, &ztest);
}

static texbuffer_t nc_world_tex[NC_MATERIAL_COUNT > 0 ? NC_MATERIAL_COUNT : 1];

typedef struct {
    float pos[3], rot[3], scale[3];
    float spin[3];              /* degrees per frame, applied to rot */
    int material;
    int tint[3];                /* 0..128, modulated with the texture */
    int lit;                    /* 0 draws full bright, ignoring every light */
    int active;
} NCObject;

static NCObject nc_objects[NC_WORLD_MAX];
static int nc_object_count;

/* Runtime render switches. These exist because this cannot be tested from a
 * desk -- when the television disagrees with the preview, the fastest way to
 * find out which half is wrong is to flip one thing at a time on the console
 * and look. */
static int nc_opt_perspective = 1;     /* STQ with 1/z, or plain affine UV */
static int nc_opt_filter = 1;          /* nearest or bilinear; bilinear reads
                                        * better on a real television */
static int nc_opt_lighting = 1;
static int nc_opt_cull = 1;            /* drop faces that point away */
static int nc_opt_wireframe;
static int nc_opt_blend;               /* 0 opaque, 1 alpha, 2 additive */
static int nc_opt_boost;               /* MODULATE past 0x80 brightens */
static int nc_opt_collide = 1;

/* Filled every frame, read by the lab readout. */
static int nc_stat_objects, nc_stat_tris, nc_stat_culled, nc_stat_sprites;
static int nc_stat_faces;              /* considered, before culling */
static int nc_stat_touching;

/* Billboards: a flat picture that always faces the camera, sorted against the
 * boxes rather than drawn over them. This is the whole basis of a sprite
 * character in a 3D world, and the reason it belongs in the same depth sort
 * is that standing behind a pillar has to put the sprite behind the pillar. */
#define NC_SPRITE_MAX 16
typedef struct {
    float pos[3];
    float size[2];
    int material;
    int tint[3];
    int active;
} NCBillboard;

static NCBillboard nc_sprites[NC_SPRITE_MAX];
static int nc_sprite_count;

static int nc_sprite_spawn(float x, float y, float z, float w, float h)
{
    NCBillboard *s;
    if (nc_sprite_count >= NC_SPRITE_MAX) return -1;
    s = &nc_sprites[nc_sprite_count];
    s->pos[0]=x; s->pos[1]=y; s->pos[2]=z;
    s->size[0]=w; s->size[1]=h;
    s->material=0; s->tint[0]=s->tint[1]=s->tint[2]=128; s->active=1;
    return nc_sprite_count++;
}

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
        /* Page alignment, not block. The GS stores a texture swizzled within
         * its pages, so a texture that does not begin on a page boundary is
         * read back with the wrong pattern -- which reads as one flat colour
         * rather than as noise, and so looks like "no texture is loading"
         * rather than like corruption. Every other texture in this project
         * was already page-aligned, which is exactly why every other texture
         * worked. */
        nc_world_tex[i].width=nc_materials[i].width;nc_world_tex[i].psm=GS_PSM_32;
        nc_world_tex[i].address=nc_vram(nc_materials[i].width,nc_materials[i].height,GS_PSM_32);
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

/* ---- the world, as a thing that can change -------------------------- */

static void nc_object_init(NCObject *object) {
    int i;
    for(i=0;i<3;i++){object->pos[i]=0;object->rot[i]=0;object->scale[i]=1;object->spin[i]=0;object->tint[i]=128;}
    object->material=0;object->lit=1;object->active=1;
}

static void nc_world_reset(void) {
    int i,axis;
    nc_object_count=0;
    for(i=0;i<NC_WORLD_OBJECT_COUNT && i<NC_WORLD_MAX;i++) {
        NCObject *object=&nc_objects[nc_object_count++];
        nc_object_init(object);
        for(axis=0;axis<3;axis++) {
            object->pos[axis]=nc_world_pos[i][axis];
            object->rot[axis]=nc_world_rot[i][axis];
            object->scale[axis]=nc_world_scale[i][axis];
        }
        object->material=nc_world_material[i];
    }
}

/* Returns the new object's index, or -1 when the list is full. Refusing at the
 * limit rather than wrapping means a stress test reports a number that is
 * true. */
static int nc_world_spawn(const NCObject *from) {
    if(nc_object_count>=NC_WORLD_MAX) return -1;
    nc_objects[nc_object_count]=*from;
    nc_objects[nc_object_count].active=1;
    return nc_object_count++;
}

static void nc_world_animate(void) {
    int i,axis;
    for(i=0;i<nc_object_count;i++)
        for(axis=0;axis<3;axis++) {
            nc_objects[i].rot[axis]+=nc_objects[i].spin[axis];
            if(nc_objects[i].rot[axis]>=360.f) nc_objects[i].rot[axis]-=360.f;
            if(nc_objects[i].rot[axis]<0.f) nc_objects[i].rot[axis]+=360.f;
        }
}

/* ---- camera ---------------------------------------------------------- */

enum { NC_CAM_AUTHORED, NC_CAM_FOLLOW, NC_CAM_ORBIT, NC_CAM_MODES };
static const char *const NC_CAM_NAMES[NC_CAM_MODES]={"AUTHORED","FOLLOW","ORBIT"};

static int nc_cam_mode=NC_CAM_AUTHORED;
static float nc_cam_pos[3]=NC_WORLD_CAMERA_POS;
static float nc_cam_target[3]=NC_WORLD_CAMERA_TARGET;
static float nc_cam_fov=NC_WORLD_CAMERA_FOV;
static float nc_cam_angle=0.9f, nc_cam_height=6.f, nc_cam_distance=12.f;
static int nc_player=-1;               /* which object the pad drives */

static void nc_camera_update(void) {
    const float authored_pos[3]=NC_WORLD_CAMERA_POS;
    const float authored_target[3]=NC_WORLD_CAMERA_TARGET;
    int axis;
    if(nc_cam_mode==NC_CAM_AUTHORED) {
        for(axis=0;axis<3;axis++){nc_cam_pos[axis]=authored_pos[axis];nc_cam_target[axis]=authored_target[axis];}
        return;
    }
    /* FOLLOW and ORBIT are the same arc; one is centred on the player and the
     * other on the origin, which is what makes it useful to have both when a
     * character has walked out of the authored shot. */
    if(nc_cam_mode==NC_CAM_FOLLOW && nc_player>=0 && nc_player<nc_object_count)
        for(axis=0;axis<3;axis++) nc_cam_target[axis]=nc_objects[nc_player].pos[axis];
    else
        for(axis=0;axis<3;axis++) nc_cam_target[axis]=0.f;
    nc_cam_pos[0]=nc_cam_target[0]+sinf(nc_cam_angle)*nc_cam_distance;
    nc_cam_pos[1]=nc_cam_target[1]+nc_cam_height;
    nc_cam_pos[2]=nc_cam_target[2]-cosf(nc_cam_angle)*nc_cam_distance;
}

/* ---- lighting -------------------------------------------------------- */

/* The six faces of the unit box, and the outward normal of each. Face n's
 * normal is constant in object space, so lighting is six dot products per
 * object rather than one per pixel -- which is the only kind this console
 * gives away for free. */
/* Wound so that (v1-v0) x (v2-v0) points along the face's own outward normal,
 * on every face. The original table was not: three of the six ran the other
 * way round. That cost nothing while all six faces were drawn and sorted by
 * depth, and it makes backface culling impossible, because no single sign of
 * the winding means "facing the camera" for all of them. */
static const int nc_faces[6][4]={{2,3,1,0},{4,5,7,6},{0,1,5,4},{6,7,3,2},{4,6,2,0},{1,3,7,5}};
static const float nc_face_normal[6][3]={{0,0,-1},{0,0,1},{0,-1,0},{0,1,0},{-1,0,0},{1,0,0}};

/* Texture axes per face: which of the vertex's own local signs supplies u and
 * v, and which way round. Taking the texture coordinate from where a vertex
 * *is* rather than from its position in the corner list means the winding can
 * be whatever culling needs without the artwork turning over -- the logo
 * stands upright on all six faces either way. */
static const int nc_face_uv[6][4]={
    /* -Z */ {0, 1, 1,-1}, /* +Z */ {0,-1, 1,-1},
    /* -Y */ {0,-1, 2,-1}, /* +Y */ {0, 1, 2,-1},
    /* -X */ {2,-1, 1,-1}, /* +X */ {2, 1, 1,-1}};

/* The local corner a vertex index stands for: bit 0 is x, bit 1 is y, bit 2
 * is z, each -1 or +1. */
static float nc_corner_sign(int vertex,int axis)
{
    return (vertex & (1<<axis)) ? 1.f : -1.f;
}

/* 0..1 across the face, from the vertex's own position. */
static void nc_face_texcoord(int face,int vertex,float *u,float *v)
{
    *u=(nc_corner_sign(vertex,nc_face_uv[face][0])*(float)nc_face_uv[face][1]+1.f)*.5f;
    *v=(nc_corner_sign(vertex,nc_face_uv[face][2])*(float)nc_face_uv[face][3]+1.f)*.5f;
}

static float nc_face_light[6];
static float nc_face_world[6][3];      /* the face normal after rotation */

static void nc_world_shade(const NCObject *object) {
    float ax=object->rot[0]*NC_DEG, ay=object->rot[1]*NC_DEG, az=object->rot[2]*NC_DEG;
    int f,l;
    for(f=0;f<6;f++) {
        float nx=nc_face_normal[f][0],ny=nc_face_normal[f][1],nz=nc_face_normal[f][2],tx,ty,tz,lit;
        /* Same rotation order the vertices use, so a normal never disagrees
         * with the face it belongs to. Computed even when nothing is lit,
         * because culling needs it too. */
        ty=ny*cosf(ax)-nz*sinf(ax);tz=ny*sinf(ax)+nz*cosf(ax);ny=ty;nz=tz;
        tx=nx*cosf(ay)+nz*sinf(ay);tz=-nx*sinf(ay)+nz*cosf(ay);nx=tx;nz=tz;
        tx=nx*cosf(az)-ny*sinf(az);ty=nx*sinf(az)+ny*cosf(az);nx=tx;ny=ty;
        nc_face_world[f][0]=nx;nc_face_world[f][1]=ny;nc_face_world[f][2]=nz;
        if(!object->lit || !nc_opt_lighting) { nc_face_light[f]=1.f; continue; }
        lit=NC_WORLD_AMBIENT;
        for(l=0;l<NC_WORLD_LIGHT_COUNT;l++) {
            float d=nx*nc_world_light_dir[l][0]+ny*nc_world_light_dir[l][1]+nz*nc_world_light_dir[l][2];
            if(d>0) lit+=d*nc_world_light_power[l];
        }
        nc_face_light[f]=lit<0.f?0.f:(lit>1.f?1.f:lit);
    }
}

/* Boxes only, on X and Z, and floors are left out of it. Enough to stop a
 * character walking through a pillar, which is the question a prototype is
 * actually asking. */
static void nc_world_collide(int who)
{
    NCObject *actor;
    int i;
    nc_stat_touching=0;
    if(!nc_opt_collide || who<0 || who>=nc_object_count) return;
    actor=&nc_objects[who];
    for(i=0;i<nc_object_count;i++) {
        NCObject *other=&nc_objects[i];
        float overlap_x,overlap_z,reach_x,reach_z,dx,dz;
        if(i==who || !other->active) continue;
        if(other->scale[1]<0.3f) continue;            /* a floor is not a wall */
        reach_x=actor->scale[0]+other->scale[0];
        reach_z=actor->scale[2]+other->scale[2];
        dx=actor->pos[0]-other->pos[0];
        dz=actor->pos[2]-other->pos[2];
        overlap_x=reach_x-(dx<0?-dx:dx);
        overlap_z=reach_z-(dz<0?-dz:dz);
        if(overlap_x<=0.f || overlap_z<=0.f) continue;
        nc_stat_touching++;
        /* Push out along whichever axis is least buried, or a character
         * clips through a corner instead of sliding along it. */
        if(overlap_x<overlap_z) actor->pos[0]+=dx<0?-overlap_x:overlap_x;
        else                    actor->pos[2]+=dz<0?-overlap_z:overlap_z;
    }
}

/* ---- drawing --------------------------------------------------------- */

/* Which way a face is wound once projected. For the winding these cubes use,
 * positive faces the camera, so this is the whole of backface culling: no
 * normals, no dot products, and exact rather than an approximation that goes
 * wrong when an object is close to the eye.
 *
 * Which sign meant "towards" was settled by rendering both ways in ps2preview
 * and looking, not by deriving it. The wrong one keeps every face you cannot
 * see and drops every face you can, which draws a hollow box. */
static float nc_face_facing(const int *quad, const float *px, const float *py)
{
    float ax=px[quad[1]]-px[quad[0]], ay=py[quad[1]]-py[quad[0]];
    float bx=px[quad[3]]-px[quad[0]], by=py[quad[3]]-py[quad[0]];
    return ax*by-ay*bx;
}

static qword_t *nc_world_wire(qword_t *q,const NCObject *object,float *px,float *py,int *visible)
{
    /* The twelve edges of a box, as vertex pairs. */
    static const int edge[12][2]={{0,1},{1,3},{3,2},{2,0},{4,5},{5,7},{7,6},{6,4},
                                  {0,4},{1,5},{2,6},{3,7}};
    prim_t prim={0};color_t color={0};int e;
    prim.type=PRIM_LINE;prim.shading=PRIM_SHADE_FLAT;prim.mapping=DRAW_DISABLE;
    prim.blending=nc_opt_blend?DRAW_ENABLE:DRAW_DISABLE;prim.colorfix=PRIM_FIXED;
    color.r=(unsigned char)object->tint[0];color.g=(unsigned char)object->tint[1];
    color.b=(unsigned char)object->tint[2];color.a=0x80;color.q=1.0f;
    for(e=0;e<12;e++) {
        u64 *dw;int n;
        if(!visible[edge[e][0]]||!visible[edge[e][1]])continue;
        dw=(u64*)draw_prim_start(q,0,&prim,&color);
        for(n=0;n<2;n++){
            xyz_t xyz;int v=edge[e][n];
            xyz.x=(u16)ftoi4(2048+px[v]);xyz.y=(u16)ftoi4(2048+py[v]);xyz.z=65535;   /* wireframe shows every edge, so nothing occludes it */
            *dw++=color.rgbaq;*dw++=xyz.xyz;
        }
        q=draw_prim_end((qword_t*)dw,2,DRAW_RGBAQ_REGLIST);
    }
    return q;
}

static qword_t *nc_world_cube(qword_t *q,const NCObject *object,float *px,float *py,
                              float *depth,int *visible) {
    static const int tri[6]={0,1,2,0,2,3};
    prim_t prim={0};color_t color={0};clutbuffer_t clut={0};
    int material=object->material,f,i,order[6]={0,1,2,3,4,5};float face_depth[6];
    int ceiling=nc_opt_boost?0xFF:0x80;
    float far_s,far_t;
    if(nc_opt_wireframe) return nc_world_wire(q,object,px,py,visible);
    if(material<0||material>=NC_MATERIAL_COUNT)return q;
    clut.storage_mode=CLUT_STORAGE_MODE1;clut.load_method=CLUT_NO_LOAD;
    q=draw_texturebuffer(q,0,&nc_world_tex[material],&clut);
    prim.type=PRIM_TRIANGLE;prim.mapping=DRAW_ENABLE;prim.colorfix=PRIM_FIXED;
    prim.blending=nc_opt_blend?DRAW_ENABLE:DRAW_DISABLE;
    /* Perspective correction is not a mode the GS is missing -- it is what it
     * does when a primitive carries ST and a per-vertex Q of 1/z instead of
     * fixed-point UV. Affine is kept alongside it because it is the only way
     * to tell, on a television, whether a wrong-looking floor is the mapping
     * or something else. */
    prim.mapping_type=nc_opt_perspective?PRIM_MAP_ST:PRIM_MAP_UV;
    prim.shading=nc_opt_perspective?PRIM_SHADE_GOURAUD:PRIM_SHADE_FLAT;
    /* Every texel in these materials is fully opaque, so blending source-over
     * at full alpha is indistinguishable from not blending -- which is why
     * OPAQUE and ALPHA looked identical. ALPHA asks for translucency, so it
     * gets some. */
    color.a=nc_opt_blend==1?0x40:0x80;color.q=1.0f;
    /* The artwork occupies the top-left of a power-of-two texture, so the far
     * edge of the picture is not 1.0. */
    far_s=(float)nc_materials[material].used_width/(float)nc_materials[material].width;
    far_t=(float)nc_materials[material].used_height/(float)nc_materials[material].height;
    for(f=0;f<6;f++)face_depth[f]=(depth[nc_faces[f][0]]+depth[nc_faces[f][1]]+depth[nc_faces[f][2]]+depth[nc_faces[f][3]])*.25f;
    for(i=0;i<5;i++)for(f=i+1;f<6;f++)if(face_depth[order[i]]<face_depth[order[f]]){int swap=order[i];order[i]=order[f];order[f]=swap;}
    for(i=0;i<6;i++){u64 *dw;int shade,n;f=order[i];
        if(!visible[nc_faces[f][0]]||!visible[nc_faces[f][1]]||!visible[nc_faces[f][2]]||!visible[nc_faces[f][3]])continue;
        nc_stat_faces++;
        if(nc_opt_cull && nc_face_facing(nc_faces[f],px,py)<=0.f){nc_stat_culled++;continue;}
        /* 0x80 is full brightness through MODULATE, not 0xFF -- which is why
         * going past it brightens rather than overflows, and is the only way
         * to read a dark texture on a television. */
        shade=(int)(nc_face_light[f]*128.f);
        if(nc_opt_boost) shade*=2;
        if(shade>ceiling) shade=ceiling;
        color.r=(object->tint[0]*shade)>>7;if(color.r>ceiling)color.r=ceiling;
        color.g=(object->tint[1]*shade)>>7;if(color.g>ceiling)color.g=ceiling;
        color.b=(object->tint[2]*shade)>>7;if(color.b>ceiling)color.b=ceiling;
        dw=(u64*)draw_prim_start(q,0,&prim,&color);
        for(n=0;n<6;n++){
            int corner=tri[n],v=nc_faces[f][corner];
            float face_u,face_v;
            xyz_t xyz;
            xyz.x=(u16)ftoi4(2048+px[v]);xyz.y=(u16)ftoi4(2048+py[v]);xyz.z=nc_depth_value(depth[v]);
            nc_face_texcoord(f,v,&face_u,&face_v);
            if(nc_opt_perspective) {
                /* ST before RGBAQ: the Q the rasteriser divides by is the one
                 * in the RGBAQ register, so the colour has to be written after
                 * the texture coordinate that belongs with it. Reversing these
                 * two silently pairs each vertex with the previous vertex's
                 * depth, which looks almost right and is not. */
                texel_t st;
                float w=1.f/depth[v];
                st.s=face_u*far_s*w;
                st.t=face_v*far_t*w;
                color.q=w;
                *dw++=st.uv;*dw++=color.rgbaq;*dw++=xyz.xyz;
            } else {
                texel_t uv;
                int u=(int)(face_u*(float)(nc_materials[material].used_width-1));
                int t=(int)(face_v*(float)(nc_materials[material].used_height-1));
                uv.uv=(u64)ftoi4(u)|((u64)ftoi4(t)<<32);
                *dw++=uv.uv;*dw++=xyz.xyz;
            }
        }
        q=nc_opt_perspective?draw_prim_end((qword_t*)dw,3,DRAW_STQ2_REGLIST)
                            :draw_prim_end((qword_t*)dw,2,DRAW_UV_REGLIST);
        nc_stat_tris+=2;
    }return q;
}

/* A billboard is a quad built in screen space at the depth of its anchor, so
 * it faces the camera exactly and costs one projected point instead of four.
 * Scale comes from the same focal length the boxes use, so a sprite two units
 * tall matches a box two units tall standing beside it. */
static qword_t *nc_world_billboard(qword_t *q,const NCBillboard *flat,
                                   float cx,float cy,float depth,float focal)
{
    static const int tri[6]={0,1,2,0,2,3};
    prim_t prim={0};color_t color={0};clutbuffer_t clut={0};
    float half_w,tall,far_s,far_t;int n;u64 *dw;
    int material=flat->material;
    if(material<0||material>=NC_MATERIAL_COUNT||depth<0.3f)return q;
    half_w=flat->size[0]*.5f*focal*NC_PIXEL_ASPECT/depth;
    tall=flat->size[1]*focal/depth;
    clut.storage_mode=CLUT_STORAGE_MODE1;clut.load_method=CLUT_NO_LOAD;
    q=draw_texturebuffer(q,0,&nc_world_tex[material],&clut);
    prim.type=PRIM_TRIANGLE;prim.mapping=DRAW_ENABLE;prim.colorfix=PRIM_FIXED;
    prim.shading=PRIM_SHADE_GOURAUD;prim.mapping_type=PRIM_MAP_ST;
    prim.blending=nc_opt_blend?DRAW_ENABLE:DRAW_DISABLE;
    far_s=(float)nc_materials[material].used_width/(float)nc_materials[material].width;
    far_t=(float)nc_materials[material].used_height/(float)nc_materials[material].height;
    color.r=(unsigned char)flat->tint[0];color.g=(unsigned char)flat->tint[1];
    color.b=(unsigned char)flat->tint[2];color.a=0x80;color.q=1.f/depth;
    dw=(u64*)draw_prim_start(q,0,&prim,&color);
    for(n=0;n<6;n++){
        int corner=tri[n];
        texel_t st;xyz_t xyz;
        float w=1.f/depth;
        float x=cx+((corner==1||corner==2)?half_w:-half_w);
        /* Anchored at the feet: a sprite stands on its position rather than
         * floating centred on it, which is what makes it line up with a box
         * resting on the same floor. */
        float y=cy+((corner>=2)?0.f:-tall);
        st.s=((corner==1||corner==2)?far_s:0.f)*w;
        st.t=((corner>=2)?far_t:0.f)*w;
        color.q=w;
        xyz.x=(u16)ftoi4(2048+x);xyz.y=(u16)ftoi4(2048+y);xyz.z=nc_depth_value(depth);   /* flat: every corner at the anchor depth, so it slots between boxes */
        *dw++=st.uv;*dw++=color.rgbaq;*dw++=xyz.xyz;
    }
    q=draw_prim_end((qword_t*)dw,3,DRAW_STQ2_REGLIST);
    nc_stat_tris+=2;nc_stat_sprites++;
    return q;
}

static qword_t *nc_world_draw(qword_t *q) {
    float dx,dy,dz,yaw,pitch,focal;
    /* One list for boxes and billboards together. Sorting them separately is
     * how a sprite ends up drawn over the pillar it is standing behind. */
    int order[NC_WORLD_MAX+NC_SPRITE_MAX];
    float centre[NC_WORLD_MAX+NC_SPRITE_MAX];
    int drawn=0,slot,i,j;

    nc_camera_update();
    dx=nc_cam_target[0]-nc_cam_pos[0];dy=nc_cam_target[1]-nc_cam_pos[1];dz=nc_cam_target[2]-nc_cam_pos[2];
    yaw=-atan2f(dx,dz);pitch=atan2f(dy,sqrtf(dx*dx+dz*dz));
    focal=((float)SCREEN_H*.5f)/tanf(nc_cam_fov*0.00872664626f);
    nc_stat_tris=0;nc_stat_culled=0;nc_stat_sprites=0;nc_stat_faces=0;
    if(z.enable) q=nc_depth_test(q,ZTEST_METHOD_GREATER);

    /* Sampling is state for the whole drawing context, not a property of a
     * primitive. Setting it once a frame costs less packet than setting it per
     * object, and it makes explicit what was already happening by accident:
     * the choice carries on to the text drawn after the world, which is where
     * bilinear is most visible on a television. */
    {
        lod_t lod={0};
        lod.calculation=LOD_USE_K;
        lod.mag_filter=nc_opt_filter?LOD_MAG_LINEAR:LOD_MAG_NEAREST;
        lod.min_filter=nc_opt_filter?LOD_MIN_LINEAR:LOD_MIN_NEAREST;
        q=draw_texture_sampling(q,0,&lod);
    }

    if(nc_opt_blend) {
        blend_t blend;
        /* (c1-c2)*a>>7 + c3. Alpha is source over destination; additive is the
         * same with nothing subtracted, which is every glow this console
         * ever drew. */
        blend.color1=BLEND_COLOR_SOURCE;
        blend.color2=nc_opt_blend==2?BLEND_COLOR_ZERO:BLEND_COLOR_DEST;
        blend.alpha=BLEND_ALPHA_SOURCE;
        blend.color3=BLEND_COLOR_DEST;
        blend.fixed_alpha=0x80;
        q=draw_alpha_blending(q,0,&blend);
    }

    for(i=0;i<nc_object_count;i++) {
        float ox,oy,oz,flat_z;
        if(!nc_objects[i].active) continue;
        ox=nc_objects[i].pos[0]-nc_cam_pos[0];oy=nc_objects[i].pos[1]-nc_cam_pos[1];oz=nc_objects[i].pos[2]-nc_cam_pos[2];
        /* Deliberately not named rx/rz: test_ps2camera reads the vertex
         * projection out of this file by variable name, and a second `rz`
         * earlier in the function would be the one it found. */
        flat_z=-ox*sinf(yaw)+oz*cosf(yaw);
        centre[drawn]=oy*sinf(pitch)+flat_z*cosf(pitch);
        order[drawn++]=i;
    }
    for(i=0;i<nc_sprite_count;i++) {
        float ox,oy,oz,flat_z;
        if(!nc_sprites[i].active) continue;
        ox=nc_sprites[i].pos[0]-nc_cam_pos[0];oy=nc_sprites[i].pos[1]-nc_cam_pos[1];oz=nc_sprites[i].pos[2]-nc_cam_pos[2];
        flat_z=-ox*sinf(yaw)+oz*cosf(yaw);
        centre[drawn]=oy*sinf(pitch)+flat_z*cosf(pitch);
        order[drawn++]=NC_WORLD_MAX+i;      /* tagged as a billboard */
    }
    for(i=0;i+1<drawn;i++)for(j=i+1;j<drawn;j++)
        if(centre[i]<centre[j]){int s=order[i];float c=centre[i];order[i]=order[j];centre[i]=centre[j];order[j]=s;centre[j]=c;}
    nc_stat_objects=drawn;

    for(slot=0;slot<drawn;slot++){
        float px[8],py[8],depths[8];int visible[8];
        const NCObject *object;
        float ax,ay,az;

        if(order[slot]>=NC_WORLD_MAX) {
            const NCBillboard *flat=&nc_sprites[order[slot]-NC_WORLD_MAX];
            float vx=flat->pos[0]-nc_cam_pos[0];
            float vy=flat->pos[1]-nc_cam_pos[1];
            float vz=flat->pos[2]-nc_cam_pos[2];
            float rx=vx*cosf(yaw)+vz*sinf(yaw),rz=-vx*sinf(yaw)+vz*cosf(yaw);
            float ry=vy*cosf(pitch)-rz*sinf(pitch),depth=vy*sinf(pitch)+rz*cosf(pitch);
            if(depth>=0.3f)
                q=nc_world_billboard(q,flat,rx*focal*NC_PIXEL_ASPECT/depth,
                                     -ry*focal/depth,depth,focal);
            continue;
        }

        object=&nc_objects[order[slot]];
        ax=object->rot[0]*NC_DEG;ay=object->rot[1]*NC_DEG;az=object->rot[2]*NC_DEG;
        nc_world_shade(object);
        for(i=0;i<8;i++){float vx=(i&1)?1:-1,vy=(i&2)?1:-1,vz=(i&4)?1:-1,tx,ty,tz;
            vx*=object->scale[0];vy*=object->scale[1];vz*=object->scale[2];
            ty=vy*cosf(ax)-vz*sinf(ax);tz=vy*sinf(ax)+vz*cosf(ax);vy=ty;vz=tz;
            tx=vx*cosf(ay)+vz*sinf(ay);tz=-vx*sinf(ay)+vz*cosf(ay);vx=tx;vz=tz;
            tx=vx*cosf(az)-vy*sinf(az);ty=vx*sinf(az)+vy*cosf(az);vx=tx;vy=ty;
            vx+=object->pos[0]-nc_cam_pos[0];vy+=object->pos[1]-nc_cam_pos[1];vz+=object->pos[2]-nc_cam_pos[2];
            {float rx=vx*cosf(yaw)+vz*sinf(yaw),rz=-vx*sinf(yaw)+vz*cosf(yaw);
             float ry=vy*cosf(pitch)-rz*sinf(pitch),depth=vy*sinf(pitch)+rz*cosf(pitch);
             visible[i]=depth>=0.3f;depths[i]=depth;
             if(visible[i]){px[i]=rx*focal*NC_PIXEL_ASPECT/depth;py[i]=-ry*focal/depth;}}
        }
        q=nc_world_cube(q,object,px,py,depths,visible);
    }
    if(z.enable) q=nc_depth_test(q,ZTEST_METHOD_ALLPASS);
    return q;
}
