/* Drawing an imported model on the console.
 *
 * The boxes in nc_world3d.h project eight corners and draw six faces. A model
 * has thousands of both, and the difference that matters is not the count --
 * it is that a corner is shared. Cloud has 2754 vertices and 3341 triangles,
 * which is 10023 triangle corners; transforming per corner rather than per
 * vertex is three times the arithmetic on a processor with none spare.
 *
 * So this is two passes. Every vertex is transformed, projected and lit once
 * into a scratch array, and then the index list is walked and triangles are
 * emitted from numbers that are already computed. The second pass touches no
 * trigonometry at all.
 *
 * Included after nc_world3d.h, whose camera, lighting and depth values it
 * shares -- a model and a box lit by different code would disagree about the
 * same light.
 */
#pragma once

/* Enough for a character. An environment is a different problem and wants
 * culling before it wants a bigger buffer. */
#define NC_MESH_MAX_VERTS 4096

/* One record a vertex, sixteen bytes, four to a cache line.
 *
 * This was five parallel arrays, and it cost about what five parallel arrays
 * cost. The emit reads a vertex by index, and an index list is scattered, so
 * every corner missed the cache once per array: measured at 572 ticks a
 * triangle, of which five misses times 31 ticks times three corners is 468.
 * Interleaved, a corner touches one line instead of five.
 *
 * The projected depth is not kept at all. Only 1/depth is ever read again --
 * by the texture coordinate and by the depth value -- so keeping both was a
 * fifth of a cache line spent on a number nothing wanted. */
typedef struct {
    float x, y, w;
    unsigned short shade, visible;
} NCScreenVertex;

static NCScreenVertex nc_mv[NC_MESH_MAX_VERTS];

static int nc_stat_mesh_tris, nc_stat_mesh_culled, nc_stat_mesh_dropped;

/* Where the mesh frame actually goes. Two guesses about this have now been
 * wrong -- a cache theory that predicted fusing the passes would help, and it
 * bought nothing measurable -- so the split is measured on the console rather
 * than reasoned about from a listing. */
static unsigned int nc_stat_tk_vertex, nc_stat_tk_emit, nc_mesh_emit_mark;

/* Where a model stands. Kept separate from NCObject because a mesh has no
 * scale per axis and no six faces -- pretending it is a box would mean the
 * box code growing a branch for something that is not one. */
typedef struct {
    const NCMeshData *data;
    float pos[3];
    float yaw;              /* degrees */
    float scale;
    int tint[3];
    int active;
    /* The rig posing this mesh, if one is. Null means the mesh stands in its
     * bind pose and the compiled arrays are read straight.
     *
     * The skinned vertices are deliberately *not* stored anywhere. Writing
     * them to an array and reading them back in the next pass costs 11 KB of
     * traffic through an 8 KB data cache, so the skin happens inside the
     * transform loop and the result never leaves a register. */
    const unsigned char *vbone;
    int posed;
} NCModel;

static void nc_model_init(NCModel *model, const NCMeshData *data)
{
    int i;
    model->data = data;
    for (i = 0; i < 3; i++) { model->pos[i] = 0.f; model->tint[i] = 128; }
    model->yaw = 0.f;
    model->scale = 1.f;
    model->active = 1;
    model->vbone = 0;
    model->posed = 0;
}

/* Pass one: every vertex, once. */
static void nc_mesh_transform(const NCModel *model, float yaw, float pitch,
                              float focal)
{
    const NCMeshData *data = model->data;
    float my = model->yaw * NC_DEG;
    float mc = cosf(my), ms = sinf(my), scale = model->scale;
    int count = data->vertices > NC_MESH_MAX_VERTS ? NC_MESH_MAX_VERTS : data->vertices;
    float cy = cosf(yaw), sy = sinf(yaw), cp = cosf(pitch), sp = sinf(pitch);
    int i;

    for (i = 0; i < count; i++) {
        const float *p = &data->pos[i * 3];
        const float *n = &data->nrm[i * 3];
        float sx, sy, sz, nx0, ny0, nz0;
        float vx, vy, vz, tx, tz, rx, rz, ry, depth, lit, w;
        int l, shade;

        if (model->posed) {
            /* Skinned here rather than in a pass of its own. */
            const float *m = nc_bone_skin[model->vbone[i]];
            sx = m[0] * p[0] + m[1] * p[1] + m[2] * p[2] + m[3];
            sy = m[4] * p[0] + m[5] * p[1] + m[6] * p[2] + m[7];
            sz = m[8] * p[0] + m[9] * p[1] + m[10] * p[2] + m[11];
            nx0 = m[0] * n[0] + m[1] * n[1] + m[2] * n[2];
            ny0 = m[4] * n[0] + m[5] * n[1] + m[6] * n[2];
            nz0 = m[8] * n[0] + m[9] * n[1] + m[10] * n[2];
        } else {
            sx = p[0]; sy = p[1]; sz = p[2];
            nx0 = n[0]; ny0 = n[1]; nz0 = n[2];
        }

        /* Model yaw, then scale, then into the world. */
        tx = sx * mc + sz * ms;
        tz = -sx * ms + sz * mc;
        vx = tx * scale + model->pos[0] - nc_cam_pos[0];
        vy = sy * scale + model->pos[1] - nc_cam_pos[1];
        vz = tz * scale + model->pos[2] - nc_cam_pos[2];

        rx = vx * cy + vz * sy;
        rz = -vx * sy + vz * cy;
        ry = vy * cp - rz * sp;
        depth = vy * sp + rz * cp;

        nc_mv[i].visible = (unsigned short)(depth >= 0.3f);
        if (nc_mv[i].visible) {
            w = 1.f / depth;                 /* the frame's only divide here */
            nc_mv[i].w = w;
            nc_mv[i].x = rx * focal * NC_PIXEL_ASPECT * w;
            nc_mv[i].y = -ry * focal * w;
        } else {
            nc_mv[i].w = 0.f;
        }

        /* Lit per vertex, which is what the Gouraud path can carry. A model
         * shaded per face reads as faceted no matter how many triangles it
         * has. */
        lit = NC_WORLD_AMBIENT;
        if (nc_opt_lighting) {
            float nx = nx0 * mc + nz0 * ms;
            float ny = ny0;
            float nz = -nx0 * ms + nz0 * mc;
            for (l = 0; l < NC_WORLD_LIGHT_COUNT; l++) {
                float d = nx * nc_world_light_dir[l][0]
                        + ny * nc_world_light_dir[l][1]
                        + nz * nc_world_light_dir[l][2];
                if (d > 0) lit += d * nc_world_light_power[l];
            }
        } else {
            lit = 1.f;
        }
        shade = (int)(lit * 128.f);
        if (nc_opt_boost) shade *= 2;
        if (shade > 255) shade = 255;
        if (shade < 0) shade = 0;
        nc_mv[i].shade = (unsigned short)shade;
    }
    for (i = count; i < data->vertices && i < NC_MESH_MAX_VERTS; i++)
        nc_mv[i].visible = 0;
}

/* Triangles are buffered and emitted together, and the batch is always an
 * even number of them. This is not an optimisation.
 *
 * REGLIST mode packs each register as 64 bits, and draw_prim_end is handed a
 * qword_t pointer. One triangle carrying ST, RGBAQ and XYZ is 3 vertices x 3
 * registers = 9 quadwords' worth of halves -- 4.5 quadwords -- so emitting a
 * primitive per triangle hands draw_prim_end a pointer half a quadword out of
 * alignment. It writes a GIF tag with the wrong length, and everything after
 * it in the packet is read as the wrong kind of thing: textures arrive torn,
 * and the DMA eventually stops. Two triangles is 18 halves, which is 9 whole
 * quadwords, and every other primitive in this engine was already even by
 * accident of drawing quads.
 */
#define NC_MESH_BATCH 96                  /* even, and +1 for the pad */
static unsigned short nc_mesh_run[(NC_MESH_BATCH + 1) * 3];
static int nc_mesh_run_count;

static qword_t *nc_mesh_flush(qword_t *q, const NCMeshData *data,
                              const NCModel *model, float far_s, float far_t,
                              prim_t *prim, color_t *color, int ceiling)
{
    int corner, total;
    u64 *dw;

    if (!nc_mesh_run_count) return q;
    if (nc_mesh_run_count & 1) {
        /* Repeat the last triangle to make the count even. It draws over
         * itself at identical depth, which the GREATER test rejects, so it
         * costs a little fill and changes no pixel. */
        int last = (nc_mesh_run_count - 1) * 3;
        nc_mesh_run[last + 3] = nc_mesh_run[last];
        nc_mesh_run[last + 4] = nc_mesh_run[last + 1];
        nc_mesh_run[last + 5] = nc_mesh_run[last + 2];
        nc_mesh_run_count++;
    }
    total = nc_mesh_run_count * 3;
    if (q + (total * 2) + 16 >= packet_limit) { nc_mesh_run_count = 0; return q; }

    nc_mesh_emit_mark = cpu_ticks();
    dw = (u64 *)draw_prim_start(q, 0, prim, color);
    for (corner = 0; corner < total; corner++) {
        int v = nc_mesh_run[corner];
        const NCScreenVertex *sv = &nc_mv[v];   /* one line, not five */
        float w = sv->w;
        texel_t st; xyz_t xyz;
        int shade = sv->shade;
        st.s = data->uv[v * 2] * far_s * w;
        st.t = data->uv[v * 2 + 1] * far_t * w;
        color->r = (model->tint[0] * shade) >> 7;
        color->g = (model->tint[1] * shade) >> 7;
        color->b = (model->tint[2] * shade) >> 7;
        if (color->r > ceiling) color->r = ceiling;
        if (color->g > ceiling) color->g = ceiling;
        if (color->b > ceiling) color->b = ceiling;
        color->q = w;
        xyz.x = (u16)ftoi4(2048 + sv->x);
        xyz.y = (u16)ftoi4(2048 + sv->y);
        xyz.z = nc_depth_from_w(w);
        *dw++ = st.uv; *dw++ = color->rgbaq; *dw++ = xyz.xyz;
    }
    q = draw_prim_end((qword_t *)dw, 3, DRAW_STQ2_REGLIST);
    nc_stat_tk_emit += cpu_ticks() - nc_mesh_emit_mark;
    nc_stat_mesh_tris += nc_mesh_run_count;
    nc_mesh_run_count = 0;
    return q;
}

static qword_t *nc_mesh_draw(qword_t *q, const NCModel *model)
{
    const NCMeshData *data;
    prim_t prim = {0}; color_t color = {0}; clutbuffer_t clut = {0};
    float dx, dy, dz, yaw, pitch, focal;
    int part, ceiling = nc_opt_boost ? 0xFF : 0x80;

    nc_stat_mesh_tris = nc_stat_mesh_culled = nc_stat_mesh_dropped = 0;
    nc_mesh_run_count = 0;
    if (!model->active || !model->data) return q;
    data = model->data;
    if (data->vertices > NC_MESH_MAX_VERTS) return q;   /* refuse, do not clip */

    dx = nc_cam_target[0] - nc_cam_pos[0];
    dy = nc_cam_target[1] - nc_cam_pos[1];
    dz = nc_cam_target[2] - nc_cam_pos[2];
    yaw = -atan2f(dx, dz);
    pitch = atan2f(dy, sqrtf(dx * dx + dz * dz));
    focal = ((float)SCREEN_H * .5f) / tanf(nc_cam_fov * 0.00872664626f);
    {
        unsigned int mark = cpu_ticks();
        nc_mesh_transform(model, yaw, pitch, focal);
        nc_stat_tk_vertex = cpu_ticks() - mark;
    }
    nc_stat_tk_emit = 0;

    clut.storage_mode = CLUT_STORAGE_MODE1; clut.load_method = CLUT_NO_LOAD;
    /* PRIM bit 10, FIX, is fragment value control. Set, the GS stops
     * interpolating across the primitive and every pixel takes one
     * texture coordinate -- one texel stretched over the whole triangle,
     * which is a solid colour with the geometry still correct. That is
     * every "the texture is not showing" in this project, and PS2SDK's
     * own textured rectangle, which always worked, leaves it clear. */
    prim.type = PRIM_TRIANGLE; prim.mapping = DRAW_ENABLE;
    prim.colorfix = PRIM_UNFIXED; prim.shading = PRIM_SHADE_GOURAUD;
    prim.mapping_type = PRIM_MAP_ST;
    prim.blending = nc_opt_blend ? DRAW_ENABLE : DRAW_DISABLE;
    color.a = nc_opt_blend == 1 ? 0x40 : 0x80;
    color.q = 1.0f;

    for (part = 0; part < data->parts_count; part++) {
        const NCMeshPart *run = &data->parts[part];
        int material = run->material;
        int first = run->first, count = run->count, at;
        float far_s, far_t;

        if (material < 0 || material >= NC_MATERIAL_COUNT) continue;
        q = draw_texturebuffer(q, 0, &nc_world_tex[material], &clut);
        far_s = (float)nc_materials[material].used_width
              / (float)nc_materials[material].width;
        far_t = (float)nc_materials[material].used_height
              / (float)nc_materials[material].height;

        for (at = first; at + 2 < first + count; at += 3) {
            int a = data->index[at], b = data->index[at + 1], c = data->index[at + 2];
            float area;

            if (!nc_mv[a].visible || !nc_mv[b].visible || !nc_mv[c].visible) {
                nc_stat_mesh_dropped++;
                continue;
            }
            /* Same winding rule the boxes cull by, so a model and a box
             * disagree about nothing. */
            area = (nc_mv[b].x - nc_mv[a].x) * (nc_mv[c].y - nc_mv[a].y)
                 - (nc_mv[c].x - nc_mv[a].x) * (nc_mv[b].y - nc_mv[a].y);
            if (nc_opt_cull && area <= 0.f) { nc_stat_mesh_culled++; continue; }

            nc_mesh_run[nc_mesh_run_count * 3] = (unsigned short)a;
            nc_mesh_run[nc_mesh_run_count * 3 + 1] = (unsigned short)b;
            nc_mesh_run[nc_mesh_run_count * 3 + 2] = (unsigned short)c;
            nc_mesh_run_count++;
            if (nc_mesh_run_count >= NC_MESH_BATCH)
                q = nc_mesh_flush(q, data, model, far_s, far_t, &prim, &color, ceiling);
        }
        /* A part's triangles cannot spill into the next part's texture. */
        q = nc_mesh_flush(q, data, model, far_s, far_t, &prim, &color, ceiling);
    }
    return q;
}
