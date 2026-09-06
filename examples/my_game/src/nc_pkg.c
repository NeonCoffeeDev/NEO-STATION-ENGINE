/*
 * Neon Coffee - .ncpkg loader
 *
 * Reads the package produced by tools/ncc/ncc/ncpkg.py. The point of this file is
 * that game content stops being C: meshes and scene layout come from data, so an
 * editor can change what the game looks like without anyone touching source.
 *
 * Nothing is copied here. NC_Mesh and NC_Scene point into the embedded blob,
 * which on a 2 MB machine matters -- the data would otherwise be resident twice.
 * The mutable copy happens later, per scene, in nc_scene.c.
 */

#include <stdio.h>

#include "nc.h"

#define NC_PKG_VERSION 6

/* Mirrors the writer's layout exactly. Both sides must change together, which
 * is what the version field is for. */
typedef struct {
    char     magic[4];
    uint16_t version;
    uint16_t target;
    uint32_t chunk_count;
    uint32_t total_size;
} PkgHeader;

typedef struct {
    char     fourcc[4];
    uint32_t offset;
    uint32_t size;
    uint32_t id;
} PkgEntry;

typedef struct {
    uint16_t vert_count;
    uint16_t quad_count;
    uint16_t flags;             /* bit 0: textured                        */
    uint16_t tex_slot;
} MeshHeader;

#define MESH_TEXTURED 1

/* Where a texture and its palette go in VRAM. The packer decides the layout and
 * ships it here, so the placement rules live in exactly one place --
 * tools/ncc/ncc/textures.py -- instead of being duplicated on both sides. */
typedef struct {
    uint16_t slot, w, h, pad;
    RECT     tex_rect;
    RECT     clut_rect;
} TexHeader;

typedef struct {
    uint16_t id, pad;
    uint32_t rate;
    uint32_t size;
} SoundHeader;

typedef struct {
    uint16_t instance_count;
    uint16_t sprite_count;
    uint8_t  clear_r, clear_g, clear_b, pad0;
    int32_t  cam_px, cam_py, cam_pz;
    int16_t  cam_rx, cam_ry, cam_rz, pad1;
} SceneHeader;                              /* 28 bytes */


static int fourcc_is(const char *a, const char *b)
{
    return a[0] == b[0] && a[1] == b[1] && a[2] == b[2] && a[3] == b[3];
}


int nc_pkg_load(const void *data, NC_Package *pkg)
{
    const uint8_t *base = (const uint8_t *)data;
    const PkgHeader *hdr = (const PkgHeader *)base;
    const PkgEntry *table;
    uint32_t i;

    pkg->mesh_count = 0;
    pkg->scene_count = 0;
    pkg->texture_count = 0;

    if (!fourcc_is(hdr->magic, "NCPK")) {
        printf("nc_pkg: bad magic -- not a .ncpkg\n");
        return 0;
    }
    if (hdr->version != NC_PKG_VERSION) {
        printf("nc_pkg: version %d, expected %d. Rebuild the package.\n",
               hdr->version, NC_PKG_VERSION);
        return 0;
    }

    table = (const PkgEntry *)(base + sizeof(PkgHeader));

    for (i = 0; i < hdr->chunk_count; i++) {
        const PkgEntry *e = &table[i];
        const uint8_t *p = base + e->offset;

        if (fourcc_is(e->fourcc, "TEX0")) {
            const TexHeader *th = (const TexHeader *)p;
            const uint32_t *pixels;
            const uint32_t *palette;
            uint32_t pixel_bytes;
            NC_Texture *t;

            if (th->slot >= NC_MAX_TEXTURES) {
                printf("nc_pkg: texture slot %d is out of range\n", th->slot);
                continue;
            }

            pixels = (const uint32_t *)(p + sizeof(TexHeader));
            pixel_bytes = (uint32_t)th->w * th->h;
            pixel_bytes = (pixel_bytes + 3) & ~3u;      /* packer pads to 4 */
            palette = (const uint32_t *)((const uint8_t *)pixels + pixel_bytes);

            /* Upload both to VRAM. DrawSync waits for the GPU to be idle --
             * uploading underneath an in-flight draw corrupts it. */
            DrawSync(0);
            LoadImage(&th->tex_rect, pixels);
            DrawSync(0);
            LoadImage(&th->clut_rect, palette);
            DrawSync(0);

            t = &pkg->textures[th->slot];
            /* 1 = 8-bit CLUT, 0 = no semi-transparency blending. */
            t->tpage = getTPage(1, 0, th->tex_rect.x, th->tex_rect.y);
            t->clut = getClut(th->clut_rect.x, th->clut_rect.y);
            t->w = th->w;
            t->h = th->h;
            if ((int)th->slot >= pkg->texture_count)
                pkg->texture_count = th->slot + 1;

        } else if (fourcc_is(e->fourcc, "SND0")) {
            const SoundHeader *sh = (const SoundHeader *)p;
            nc_audio_add(p + sizeof(SoundHeader), (int)sh->size,
                         (int)sh->rate);

        } else if (fourcc_is(e->fourcc, "MESH")) {
            const MeshHeader *mh = (const MeshHeader *)p;
            const uint8_t *cursor = p + sizeof(MeshHeader);
            NC_Mesh *m;

            if (pkg->mesh_count >= NC_MAX_MESHES) {
                printf("nc_pkg: more than %d meshes, ignoring the rest\n",
                       NC_MAX_MESHES);
                continue;
            }

            /* Chunk ids are assigned in order by the writer, so a mesh's id is
             * its slot here. Guarding anyway: a mismatch would silently draw
             * the wrong model, which is a miserable bug to chase. */
            if (e->id != (uint32_t)pkg->mesh_count) {
                printf("nc_pkg: mesh id %d arrived out of order (slot %d)\n",
                       (int)e->id, pkg->mesh_count);
                return 0;
            }

            m = &pkg->meshes[pkg->mesh_count++];
            m->verts = (const SVECTOR *)cursor;
            cursor += (size_t)mh->vert_count * sizeof(SVECTOR);
            m->norms = (const SVECTOR *)cursor;
            cursor += (size_t)mh->quad_count * sizeof(SVECTOR);
            m->quads = (const NC_Quad *)cursor;
            cursor += (size_t)mh->quad_count * sizeof(NC_Quad);
            m->quad_count = mh->quad_count;

            if (mh->flags & MESH_TEXTURED) {
                /* Textures are packed before meshes, so the slot is already
                 * uploaded and its tpage/clut resolved. */
                m->uvs = cursor;
                if (mh->tex_slot < NC_MAX_TEXTURES) {
                    m->tpage = pkg->textures[mh->tex_slot].tpage;
                    m->clut = pkg->textures[mh->tex_slot].clut;
                } else {
                    printf("nc_pkg: mesh %d wants missing texture slot %d\n",
                           pkg->mesh_count - 1, mh->tex_slot);
                    m->uvs = 0;
                }
            } else {
                m->uvs = 0;
                m->tpage = 0;
                m->clut = 0;
            }

        } else if (fourcc_is(e->fourcc, "SCN0")) {
            const SceneHeader *sh = (const SceneHeader *)p;
            NC_Scene *sc;

            if (pkg->scene_count >= NC_MAX_SCENES) {
                printf("nc_pkg: more than %d scenes, ignoring the rest\n",
                       NC_MAX_SCENES);
                continue;
            }

            sc = &pkg->scenes[pkg->scene_count++];
            sc->instances = (const NC_Instance *)(p + sizeof(SceneHeader));
            sc->instance_count = sh->instance_count;

            /* Sprites follow the instances in the same chunk. */
            sc->sprites = (const NC_SpriteDef *)
                ((const uint8_t *)sc->instances
                 + (size_t)sh->instance_count * sizeof(NC_Instance));
            sc->sprite_count = sh->sprite_count;
            sc->clear_r = sh->clear_r;
            sc->clear_g = sh->clear_g;
            sc->clear_b = sh->clear_b;
            sc->cam_pos.vx = sh->cam_px;
            sc->cam_pos.vy = sh->cam_py;
            sc->cam_pos.vz = sh->cam_pz;
            sc->cam_rot.vx = sh->cam_rx;
            sc->cam_rot.vy = sh->cam_ry;
            sc->cam_rot.vz = sh->cam_rz;
            sc->cam_rot.pad = 0;
        }
        /* Unknown chunk types are skipped on purpose, so a newer package with
         * extra sections still loads on an older runtime. */
    }

    /* No meshes is fine -- a purely 2D game has sprites and nothing else. */
    if (pkg->scene_count == 0) {
        printf("nc_pkg: package contains no scenes\n");
        return 0;
    }

    printf("nc_pkg: %d mesh(es), %d texture(s), %d scene(s)\n",
           pkg->mesh_count, pkg->texture_count, pkg->scene_count);
    return 1;
}
