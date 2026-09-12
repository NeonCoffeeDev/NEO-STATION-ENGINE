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

static float nc_mv_x[NC_MESH_MAX_VERTS];
static float nc_mv_y[NC_MESH_MAX_VERTS];
static float nc_mv_depth[NC_MESH_MAX_VERTS];
static unsigned char nc_mv_visible[NC_MESH_MAX_VERTS];
static unsigned char nc_mv_shade[NC_MESH_MAX_VERTS];

static int nc_stat_mesh_tris, nc_stat_mesh_culled, nc_stat_mesh_dropped;

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
    /* Where the vertices are this frame, if something is posing them. Null
     * means the mesh stands in its bind pose and the renderer reads the
     * compiled arrays straight. */
    const float *skin_pos, *skin_nrm;
} NCModel;

static void nc_model_init(NCModel *model, const NCMeshData *data)
{
    int i;
    model->data = data;
    for (i = 0; i < 3; i++) { model->pos[i] = 0.f; model->tint[i] = 128; }
    model->yaw = 0.f;
    model->scale = 1.f;
    model->active = 1;
    model->skin_pos = 0;
    model->skin_nrm = 0;
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
        const float *p = model->skin_pos ? &model->skin_pos[i * 3] : &data->pos[i * 3];
        const float *n = model->skin_nrm ? &model->skin_nrm[i * 3] : &data->nrm[i * 3];
        float vx, vy, vz, tx, tz, rx, rz, ry, depth, lit;
        int l, shade;

        /* Model yaw, then scale, then into the world. */
        tx = p[0] * mc + p[2] * ms;
        tz = -p[0] * ms + p[2] * mc;
        vx = tx * scale + model->pos[0] - nc_cam_pos[0];
        vy = p[1] * scale + model->pos[1] - nc_cam_pos[1];
        vz = tz * scale + model->pos[2] - nc_cam_pos[2];

        rx = vx * cy + vz * sy;
        rz = -vx * sy + vz * cy;
        ry = vy * cp - rz * sp;
        depth = vy * sp + rz * cp;

        nc_mv_depth[i] = depth;
        nc_mv_visible[i] = depth >= 0.3f;
        if (nc_mv_visible[i]) {
            nc_mv_x[i] = rx * focal * NC_PIXEL_ASPECT / depth;
            nc_mv_y[i] = -ry * focal / depth;
        }

        /* Lit per vertex, which is what the Gouraud path can carry. A model
         * shaded per face reads as faceted no matter how many triangles it
         * has. */
        lit = NC_WORLD_AMBIENT;
        if (nc_opt_lighting) {
            float nx = n[0] * mc + n[2] * ms;
            float ny = n[1];
            float nz = -n[0] * ms + n[2] * mc;
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
        nc_mv_shade[i] = (unsigned char)shade;
    }
    for (i = count; i < data->vertices && i < NC_MESH_MAX_VERTS; i++)
        nc_mv_visible[i] = 0;
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

    dw = (u64 *)draw_prim_start(q, 0, prim, color);
    for (corner = 0; corner < total; corner++) {
        int v = nc_mesh_run[corner];
        float w = 1.f / nc_mv_depth[v];
        texel_t st; xyz_t xyz;
        int shade = nc_mv_shade[v];
        st.s = data->uv[v * 2] * far_s * w;
        st.t = data->uv[v * 2 + 1] * far_t * w;
        color->r = (model->tint[0] * shade) >> 7;
        color->g = (model->tint[1] * shade) >> 7;
        color->b = (model->tint[2] * shade) >> 7;
        if (color->r > ceiling) color->r = ceiling;
        if (color->g > ceiling) color->g = ceiling;
        if (color->b > ceiling) color->b = ceiling;
        color->q = w;
        xyz.x = (u16)ftoi4(2048 + nc_mv_x[v]);
        xyz.y = (u16)ftoi4(2048 + nc_mv_y[v]);
        xyz.z = nc_depth_value(nc_mv_depth[v]);
        *dw++ = st.uv; *dw++ = color->rgbaq; *dw++ = xyz.xyz;
    }
    q = draw_prim_end((qword_t *)dw, 3, DRAW_STQ2_REGLIST);
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
    nc_mesh_transform(model, yaw, pitch, focal);

    clut.storage_mode = CLUT_STORAGE_MODE1; clut.load_method = CLUT_NO_LOAD;
    prim.type = PRIM_TRIANGLE; prim.mapping = DRAW_ENABLE;
    prim.colorfix = PRIM_FIXED; prim.shading = PRIM_SHADE_GOURAUD;
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

            if (!nc_mv_visible[a] || !nc_mv_visible[b] || !nc_mv_visible[c]) {
                nc_stat_mesh_dropped++;
                continue;
            }
            /* Same winding rule the boxes cull by, so a model and a box
             * disagree about nothing. */
            area = (nc_mv_x[b] - nc_mv_x[a]) * (nc_mv_y[c] - nc_mv_y[a])
                 - (nc_mv_x[c] - nc_mv_x[a]) * (nc_mv_y[b] - nc_mv_y[a]);
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
