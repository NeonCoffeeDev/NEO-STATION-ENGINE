/* Posing a skeleton and moving a mesh with it, on the console.
 *
 * Rigid binding: one bone per vertex. That is what the models of this era did
 * and it is why this is affordable -- a vertex is one matrix pick and one
 * multiply, not a weighted sum of four.
 *
 * The arithmetic that matters is the inverse bind. The vertices are stored in
 * model space at the pose the mesh was built in, not in bone space, so moving
 * a bone means undoing the bind first:
 *
 *     skinned = BoneWorld(posed) * BoneWorld(bind)^-1 * vertex
 *
 * The right hand side of that is constant, so it is compiled in rather than
 * inverted here. What is left per frame is one 3x4 multiply per bone and one
 * per vertex.
 *
 * Matrices are 3x4, row major: nine for rotation and three for translation.
 * The fourth row of a 4x4 is always 0,0,0,1 and multiplying by it is three
 * wasted multiplies per vertex on a processor that has none to waste.
 */
#pragma once

#define NC_SKIN_MAX_BONES 64

static float nc_bone_local[NC_SKIN_MAX_BONES][12];
static float nc_bone_world[NC_SKIN_MAX_BONES][12];
static float nc_bone_skin[NC_SKIN_MAX_BONES][12];
static float nc_skin_pos[NC_MESH_MAX_VERTS * 3];
static float nc_skin_nrm[NC_MESH_MAX_VERTS * 3];

/* out = a * b, both 3x4 with an implied 0,0,0,1 bottom row. */
static void nc_mat34_mul(float *out, const float *a, const float *b)
{
    int row, col;
    for (row = 0; row < 3; row++) {
        for (col = 0; col < 3; col++)
            out[row * 4 + col] = a[row * 4 + 0] * b[0 * 4 + col]
                               + a[row * 4 + 1] * b[1 * 4 + col]
                               + a[row * 4 + 2] * b[2 * 4 + col];
        out[row * 4 + 3] = a[row * 4 + 0] * b[0 * 4 + 3]
                         + a[row * 4 + 1] * b[1 * 4 + 3]
                         + a[row * 4 + 2] * b[2 * 4 + 3]
                         + a[row * 4 + 3];
    }
}

/* XYZ Euler, the same order the importer and the clip authoring use. */
static void nc_mat34_euler(float *out, float x, float y, float z)
{
    float cx = cosf(x), sx = sinf(x);
    float cy = cosf(y), sy = sinf(y);
    float cz = cosf(z), sz = sinf(z);
    out[0] = cz * cy;
    out[1] = cz * sy * sx - sz * cx;
    out[2] = cz * sy * cx + sz * sx;
    out[3] = 0.f;
    out[4] = sz * cy;
    out[5] = sz * sy * sx + cz * cx;
    out[6] = sz * sy * cx - cz * sx;
    out[7] = 0.f;
    out[8] = -sy;
    out[9] = cy * sx;
    out[10] = cy * cx;
    out[11] = 0.f;
}

/* Sample a clip into nc_bone_skin. `blend` fades the clip in over the bind
 * pose, which is how walking starts and stops without a jump. */
static void nc_skin_pose(const NCSkeletonData *rig, const NCClipData *clip,
                         float time, float blend)
{
    int bone, slot, count = rig->count > NC_SKIN_MAX_BONES
                          ? NC_SKIN_MAX_BONES : rig->count;
    int first, second, i;
    float position, mix;

    for (bone = 0; bone < count; bone++)
        for (i = 0; i < 12; i++)
            nc_bone_local[bone][i] = rig->bind[bone * 12 + i];

    if (clip && clip->frames > 0 && blend > 0.001f) {
        position = time * clip->fps;
        first = (int)position;
        mix = position - (float)first;
        first %= clip->frames;
        if (first < 0) first += clip->frames;
        second = (first + 1) % clip->frames;

        for (slot = 0; slot < clip->joint_count; slot++) {
            int target = clip->joints[slot];
            const float *a = &clip->rot[(first * clip->joint_count + slot) * 3];
            const float *b = &clip->rot[(second * clip->joint_count + slot) * 3];
            float turn[12], combined[12];
            if (target < 0 || target >= count) continue;
            /* Euler angles are interpolated directly. Over one frame of a
             * walk the angles differ by a few degrees, where the difference
             * between this and a proper slerp is far below what a 640x448
             * picture can show. */
            nc_mat34_euler(turn,
                           (a[0] + (b[0] - a[0]) * mix) * blend,
                           (a[1] + (b[1] - a[1]) * mix) * blend,
                           (a[2] + (b[2] - a[2]) * mix) * blend);
            nc_mat34_mul(combined, nc_bone_local[target], turn);
            for (i = 0; i < 12; i++) nc_bone_local[target][i] = combined[i];
        }
        if (clip->root) {
            const float *a = &clip->root[first * 3];
            const float *b = &clip->root[second * 3];
            for (bone = 0; bone < count; bone++) {
                if (rig->parent[bone] >= 0) continue;
                nc_bone_local[bone][3] += (a[0] + (b[0] - a[0]) * mix) * blend;
                nc_bone_local[bone][7] += (a[1] + (b[1] - a[1]) * mix) * blend;
                nc_bone_local[bone][11] += (a[2] + (b[2] - a[2]) * mix) * blend;
            }
        }
    }

    /* Parents before children. The compiler emits them in that order, which
     * is what makes this one pass rather than a search. */
    for (bone = 0; bone < count; bone++) {
        int parent = rig->parent[bone];
        if (parent < 0 || parent >= count)
            for (i = 0; i < 12; i++) nc_bone_world[bone][i] = nc_bone_local[bone][i];
        else
            nc_mat34_mul(nc_bone_world[bone], nc_bone_world[parent],
                         nc_bone_local[bone]);
        nc_mat34_mul(nc_bone_skin[bone], nc_bone_world[bone],
                     &rig->inverse[bone * 12]);
    }
}

/* Move the mesh. One matrix pick and one multiply per vertex. */
static void nc_skin_mesh(const NCMeshData *mesh, const unsigned char *vbone)
{
    int i, count = mesh->vertices > NC_MESH_MAX_VERTS
                 ? NC_MESH_MAX_VERTS : mesh->vertices;
    for (i = 0; i < count; i++) {
        const float *m = nc_bone_skin[vbone[i]];
        const float *p = &mesh->pos[i * 3];
        const float *n = &mesh->nrm[i * 3];
        float *op = &nc_skin_pos[i * 3];
        float *on = &nc_skin_nrm[i * 3];
        op[0] = m[0] * p[0] + m[1] * p[1] + m[2] * p[2] + m[3];
        op[1] = m[4] * p[0] + m[5] * p[1] + m[6] * p[2] + m[7];
        op[2] = m[8] * p[0] + m[9] * p[1] + m[10] * p[2] + m[11];
        /* Rotation only. A normal is a direction, and translating one points
         * every surface at the origin. */
        on[0] = m[0] * n[0] + m[1] * n[1] + m[2] * n[2];
        on[1] = m[4] * n[0] + m[5] * n[1] + m[6] * n[2];
        on[2] = m[8] * n[0] + m[9] * n[1] + m[10] * n[2];
    }
}
