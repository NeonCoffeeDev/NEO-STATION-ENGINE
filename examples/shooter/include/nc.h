/*
 * Neon Coffee - minimal PS1 runtime
 *
 * This is the seed of the NC runtime described in docs/ARCHITECTURE.md. Right now it
 * is hand-fed C structs; later the same draw path will be fed by a .ncpkg loaded off
 * the disc. Keep the API stable and the loader can change underneath it.
 */

#ifndef NC_H
#define NC_H

#include <stdint.h>
#include <psxgpu.h>
#include <psxgte.h>
#include <psxpad.h>
#include <psxspu.h>
#include <inline_c.h>

#define NC_SCREEN_W   320
#define NC_SCREEN_H   240

/* Ordering table length. The PS1 has no depth buffer: primitives are bucketed by
 * average Z into this table and drawn back-to-front. Longer table = finer depth
 * sorting = more RAM. 1024 entries is 4 KB per buffer. */
#define NC_OT_LEN     1024

/* Per-frame primitive scratch. Every quad you draw is allocated from here and the
 * whole thing is reset on flip, so there is no freeing and no fragmentation. */
#define NC_PACKET_LEN 32768

/* ---- graphics ---------------------------------------------------------- */

void  nc_gfx_init(void);
void  nc_gfx_set_clear(int r, int g, int b);
void *nc_gfx_alloc(int bytes);          /* NULL when the packet buffer is full */
void  nc_gfx_sort(int otz, void *prim); /* bucket a primitive by depth          */
void  nc_gfx_flip(void);                /* wait for vblank, swap, draw          */

/* Draw a line of text over everything else, using the built-in debug font.
 * Screen coordinates, 0,0 top-left. Call between frames like any draw call. */
void  nc_text(int x, int y, const char *text);

/* Draw a textured quad in SCREEN space -- no GTE, no transform, no depth sort.
 * This is the 2D path: sprites are just quads the GPU draws where you say. */
void  nc_sprite_draw(uint16_t tpage, uint16_t clut, int x, int y, int w, int h,
                     int u, int v);

/* Room reserved per nc_text() call before the unused tail is handed back. One
 * sprite per character, so this caps a single line at roughly 120 characters. */
#define NC_TEXT_BUDGET 3072

/* Where sprites land in the ordering table. Text sits at 0 and the 3D pass uses
 * 2 upward, so 1 puts sprites over the world but under the HUD text. */
#define NC_SPRITE_DEPTH 1

/* ---- meshes ------------------------------------------------------------ */

/* A quad face, as four indices into the vertex array. Quads are native on PS1 and
 * cheaper than two triangles, so NC prefers them. */
typedef struct { short v0, v1, v2, v3; } NC_Quad;

typedef struct {
    const SVECTOR *verts;   /* positions, 16-bit ints                       */
    const SVECTOR *norms;   /* one face normal per quad, for lighting       */
    const NC_Quad *quads;
    const uint8_t *uvs;     /* 8 bytes per quad (u,v x4); 0 if untextured   */
    int            quad_count;
    uint16_t       tpage;   /* resolved from the texture at load time       */
    uint16_t       clut;
} NC_Mesh;

/* Transform, light, cull and sort a mesh into this frame's ordering table.
 * Positions are in world space; the camera set by nc_camera_set() is applied. */
void nc_mesh_draw(const NC_Mesh *mesh, const SVECTOR *rot, const VECTOR *pos);

/* ---- camera -------------------------------------------------------------
 *
 * There is no camera in hardware -- "moving the camera" means transforming every
 * object by the inverse of where the camera is. nc_camera_set() builds that
 * inverse once per frame; nc_mesh_draw() then composes it with each object.
 *
 * Call it before drawing anything. The default is the identity: sitting at the
 * origin looking down +Z.
 */
void nc_camera_set(const VECTOR *pos, const SVECTOR *rot);
void nc_camera_reset(void);

/* ---- input ------------------------------------------------------------- */

void nc_input_init(void);
void nc_input_poll(void);               /* call once per frame, before reading */
int  nc_held(uint16_t button);           /* PAD_CROSS, PAD_UP, ...              */
int  nc_pressed(uint16_t button);        /* true only on the frame it went down */


/* ---- packaged data ------------------------------------------------------
 *
 * A .ncpkg holds the meshes and one or more scenes, so a game's content can
 * change without recompiling anything. The package is embedded in the
 * executable and these structures point straight into it -- nothing is copied
 * or parsed at load time.
 */

/* One placed object as it appears in the package. Laid out so every field is
 * naturally aligned and the struct is exactly 32 bytes; the writer in
 * tools/ncc/ncc/ncpkg.py must agree. */
typedef struct {
    uint16_t mesh_id;
    uint16_t flags;
    int32_t  px, py, pz;      /* position                                  */
    int16_t  rx, ry, rz;      /* starting rotation, 4096 = one full turn   */
    int16_t  sx, sy, sz;      /* rotation added per frame                  */
    int16_t  pad0, pad1;
} NC_Instance;

/* A sprite as it appears in the package. 16 bytes; the writer must agree. */
typedef struct {
    uint16_t tex_slot;
    uint16_t flags;
    int16_t  x, y, w, h;
    uint16_t u, v;
} NC_SpriteDef;

typedef struct {
    const NC_Instance *instances;
    int instance_count;
    const NC_SpriteDef *sprites;
    int sprite_count;
    int clear_r, clear_g, clear_b;
    VECTOR  cam_pos;
    SVECTOR cam_rot;
} NC_Scene;

#define NC_MAX_TEXTURES 8
#define NC_MAX_SOUNDS   16
#define NC_MAX_MESHES  64
#define NC_MAX_SCENES  16

/* A texture, once it is in VRAM. tpage and clut are the packed words the GPU
 * wants; the runtime never needs the pixels again after uploading them. */
typedef struct {
    uint16_t tpage, clut;
    int      w, h;
} NC_Texture;

typedef struct {
    NC_Texture textures[NC_MAX_TEXTURES];
    int      texture_count;
    NC_Mesh  meshes[NC_MAX_MESHES];
    int      mesh_count;
    NC_Scene scenes[NC_MAX_SCENES];
    int      scene_count;
} NC_Package;

/* Returns 1 on success, 0 if the blob is not a package this build understands.
 * On failure the reason is printed to TTY. */
int nc_pkg_load(const void *data, NC_Package *pkg);


/* ---- sound ---------------------------------------------------------------
 *
 * Samples are uploaded to the SPU's own 512 KB of RAM once, at load. Playing one
 * is then just pointing a voice at an address -- the CPU does no mixing.
 */
void nc_audio_init(void);
int  nc_audio_add(const void *adpcm, int size, int rate);  /* -> id, or -1   */
void nc_audio_play(int id);
int  nc_audio_count(void);


/* ---- the live scene -----------------------------------------------------
 *
 * The package is read-only, but scripts need to move things. So loading a scene
 * copies its instances into this mutable array; the package stays the pristine
 * original that a scene reload restores from.
 */

#define NC_MAX_OBJECTS 128
#define NC_MAX_SPRITES 64

typedef struct {
    int mesh_id;
    int px, py, pz;           /* position                                  */
    int rx, ry, rz;           /* rotation, 4096 = one full turn            */
    int sx, sy, sz;           /* rotation added per frame                  */
    int visible;
} NC_Object;

/* A sprite in the live scene. Screen coordinates, so 0,0 is the top-left of the
 * 320x240 display and there is no camera involved. */
typedef struct {
    uint16_t tpage, clut;
    int x, y;
    int w, h;
    int u, v;                 /* which part of the texture to show           */
    int visible;
} NC_Sprite;

int  nc_scene_load(const NC_Package *pkg, int index);
void nc_scene_advance(void);      /* apply per-object spin, once per frame  */
void nc_scene_draw(void);         /* set the camera, then draw everything   */

int  nc_scene_object_count(void);
NC_Object *nc_scene_object(int i);   /* NULL if i is out of range           */
int  nc_scene_sprite_count(void);
NC_Sprite *nc_scene_sprite(int i);   /* NULL if i is out of range           */
int  nc_scene_index(void);
int  nc_scene_total(void);

/* Scene changes are deferred to the end of the frame, so a script can call
 * this mid-update without the objects moving under its feet. */
void nc_scene_request(int index);
int  nc_scene_take_request(void);    /* -1 when nothing is pending          */

/* Camera state lives with the scene, since each scene brings its own. */
void nc_scene_camera_set(int x, int y, int z, int rx, int ry, int rz);
void nc_scene_camera_move(int dx, int dy, int dz);
int  nc_scene_camera_get(int axis);  /* 0=x 1=y 2=z 3=yaw                   */
void nc_scene_set_clear(int r, int g, int b);

#endif /* NC_H */
