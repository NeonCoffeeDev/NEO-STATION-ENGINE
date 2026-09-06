/*
 * Neon Coffee - .ncpkg loader
 *
 * Reads the package produced by tools/ncc/ncc/ncpkg.py. The point of this file is
 * that game content stops being C: meshes and scene layout come from data, so an
 * editor can change what the game looks like without anyone touching source.
 *
 * Nothing is copied. NC_Mesh just points into the embedded blob, which on a
 * 2 MB machine matters -- a package of any size would otherwise be resident twice.
 */

#include <stdio.h>
#include <string.h>

#include "nc.h"

#define NC_PKG_VERSION 1

/* Mirrors the writer's layout exactly. Both sides must change together. */
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
    uint16_t flags;
    uint16_t pad;
} MeshHeader;

typedef struct {
    uint16_t instance_count;
    uint16_t pad;
    uint8_t  clear_r, clear_g, clear_b, pad2;
} SceneHeader;


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
    pkg->scene.instances = 0;
    pkg->scene.instance_count = 0;
    pkg->scene.clear_r = 24;
    pkg->scene.clear_g = 16;
    pkg->scene.clear_b = 48;

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

        if (fourcc_is(e->fourcc, "MESH")) {
            const MeshHeader *mh = (const MeshHeader *)p;
            const uint8_t *cursor = p + sizeof(MeshHeader);
            NC_Mesh *m;

            if (pkg->mesh_count >= NC_MAX_MESHES) {
                printf("nc_pkg: more than %d meshes, ignoring the rest\n",
                       NC_MAX_MESHES);
                continue;
            }

            /* Chunk ids are assigned in order by the writer, so the mesh id is
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
            m->quad_count = mh->quad_count;

        } else if (fourcc_is(e->fourcc, "SCN0")) {
            const SceneHeader *sh = (const SceneHeader *)p;
            pkg->scene.instances =
                (const NC_Instance *)(p + sizeof(SceneHeader));
            pkg->scene.instance_count = sh->instance_count;
            pkg->scene.clear_r = sh->clear_r;
            pkg->scene.clear_g = sh->clear_g;
            pkg->scene.clear_b = sh->clear_b;
        }
        /* Unknown chunk types are skipped on purpose, so a newer package with
         * extra sections still loads on an older runtime. */
    }

    if (pkg->mesh_count == 0) {
        printf("nc_pkg: package contains no meshes\n");
        return 0;
    }

    printf("nc_pkg: %d mesh(es), %d instance(s)\n",
           pkg->mesh_count, pkg->scene.instance_count);
    return 1;
}


void nc_pkg_draw(const NC_Package *pkg, int frame)
{
    SVECTOR rot;
    VECTOR pos;
    int i;

    for (i = 0; i < pkg->scene.instance_count; i++) {
        const NC_Instance *in = &pkg->scene.instances[i];

        if (in->mesh_id >= pkg->mesh_count)
            continue;                       /* package referenced a missing mesh */

        /* Rotation wraps naturally in 16 bits, which is exactly what RotMatrix
         * wants -- 4096 is a full turn, so overflow is harmless. */
        rot.vx = (short)(in->rx + in->sx * frame);
        rot.vy = (short)(in->ry + in->sy * frame);
        rot.vz = (short)(in->rz + in->sz * frame);
        rot.pad = 0;

        pos.vx = in->px;
        pos.vy = in->py;
        pos.vz = in->pz;

        nc_mesh_draw(&pkg->meshes[in->mesh_id], &rot, &pos);
    }
}
