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

/* ---- meshes ------------------------------------------------------------ */

/* A quad face, as four indices into the vertex array. Quads are native on PS1 and
 * cheaper than two triangles, so NC prefers them. */
typedef struct { short v0, v1, v2, v3; } NC_Quad;

typedef struct {
    const SVECTOR *verts;   /* positions, 16-bit ints                       */
    const SVECTOR *norms;   /* one face normal per quad, for lighting       */
    const NC_Quad *quads;
    int            quad_count;
} NC_Mesh;

/* Transform, light, cull and sort a mesh into this frame's ordering table. */
void nc_mesh_draw(const NC_Mesh *mesh, const SVECTOR *rot, const VECTOR *pos);

/* ---- input ------------------------------------------------------------- */

void nc_input_init(void);
void nc_input_poll(void);               /* call once per frame, before reading */
int  nc_held(uint16_t button);           /* PAD_CROSS, PAD_UP, ...              */
int  nc_pressed(uint16_t button);        /* true only on the frame it went down */


/* ---- packaged data ------------------------------------------------------
 *
 * A .ncpkg holds the meshes and the scene, so a game's content can change
 * without recompiling anything. The package is embedded in the executable and
 * the structures below point straight into it -- nothing is copied or parsed
 * at load time.
 */

/* One placed object. Laid out so every field is naturally aligned and the
 * struct is exactly 32 bytes; the writer in tools/ncc/ncc/ncpkg.py must agree. */
typedef struct {
    uint16_t mesh_id;
    uint16_t flags;
    int32_t  px, py, pz;      /* position                                  */
    int16_t  rx, ry, rz;      /* starting rotation, 4096 = one full turn   */
    int16_t  sx, sy, sz;      /* rotation added per frame                  */
    int16_t  pad0, pad1;
} NC_Instance;

typedef struct {
    const NC_Instance *instances;
    int instance_count;
    int clear_r, clear_g, clear_b;
} NC_Scene;

#define NC_MAX_MESHES 64

typedef struct {
    NC_Mesh  meshes[NC_MAX_MESHES];
    int      mesh_count;
    NC_Scene scene;
} NC_Package;

/* Returns 1 on success, 0 if the blob is not a package this build understands.
 * On failure the reason is printed to TTY. */
int  nc_pkg_load(const void *data, NC_Package *pkg);

/* Draw every instance. `frame` advances the per-instance spin. */
void nc_pkg_draw(const NC_Package *pkg, int frame);

#endif /* NC_H */
