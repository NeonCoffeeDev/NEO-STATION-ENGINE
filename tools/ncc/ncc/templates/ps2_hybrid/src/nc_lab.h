/* The hardware lab: everything that can only be answered by a television.
 *
 * Most of what is uncertain about this engine cannot be settled from a desk.
 * Whether perspective-correct texturing works, what a frame costs with twenty
 * objects on it, whether backface culling pays for itself, whether bilinear is
 * worth its bandwidth, whether a sprite sorts correctly against the pillar it
 * is standing behind -- each of those is a trip to the console, and answering
 * them one build at a time is how a week disappears.
 *
 * So they are all switches instead, and the readout carries the numbers worth
 * reporting back. One boot, one pass, every answer.
 *
 * Included after the drawing helpers in main.c, because it draws.
 */
#pragma once

/* Data that outlives a scene. Walking from the world into the conversation and
 * back is the smallest version of what a real game does constantly, and it is
 * worth having something concrete on screen that proves the trip did not
 * quietly reset it. */
typedef struct {
    int spawned;            /* total ever spawned, across levels */
    int visits;             /* how many times a level has been entered */
    int level;
    float player[3];
    int carried;            /* mirrored from the conversation's inventory */
} NCPersist;

static NCPersist nc_persist;

enum { NC_LEVEL_AUTHORED, NC_LEVEL_ARENA, NC_LEVEL_COUNT };
static const char *const NC_LEVEL_NAMES[NC_LEVEL_COUNT] = {"AUTHORED", "ARENA"};

/* ---- levels ---------------------------------------------------------- */

static void nc_lab_load_level(int level)
{
    int i;
    if (level < 0) level = NC_LEVEL_COUNT - 1;
    if (level >= NC_LEVEL_COUNT) level = 0;

    /* Where the character was standing survives the switch; the geometry does
     * not. That is the split every streaming game makes. */
    if (nc_player >= 0 && nc_player < nc_object_count)
        for (i = 0; i < 3; i++) nc_persist.player[i] = nc_objects[nc_player].pos[i];

    nc_persist.level = level;
    nc_persist.visits++;
    nc_world_reset();
    nc_sprite_count = 0;

    if (level == NC_LEVEL_ARENA) {
        NCObject block;
        nc_object_count = 0;
        nc_object_init(&block);
        block.scale[0] = 7.f; block.scale[1] = 0.2f; block.scale[2] = 7.f;
        block.pos[1] = -1.2f;
        nc_world_spawn(&block);
        for (i = 0; i < 8; i++) {
            float angle = (float)i * 0.7853981634f;
            nc_object_init(&block);
            block.pos[0] = sinf(angle) * 5.f;
            block.pos[2] = cosf(angle) * 5.f;
            block.pos[1] = 0.4f;
            block.scale[0] = 0.5f; block.scale[1] = 1.6f; block.scale[2] = 0.5f;
            block.rot[1] = (float)i * 45.f;
            nc_world_spawn(&block);
        }
    }

    /* Two billboards among the boxes. They are here so that walking behind a
     * pillar and watching the sprite disappear behind it is a thing you can
     * do, rather than a claim about the sort order. */
    nc_sprite_spawn(-2.5f, -1.f, 1.5f, 1.4f, 1.8f);
    nc_sprite_spawn(2.5f, -1.f, -1.5f, 1.4f, 1.8f);

    /* The character is a box until there is a mesh loader to make it anything
     * else. What is being tested is the control, the camera and the collision,
     * and none of those care what shape it is. */
    {
        NCObject actor;
        nc_object_init(&actor);
        actor.scale[0] = 0.4f; actor.scale[1] = 0.8f; actor.scale[2] = 0.4f;
        actor.tint[0] = 128; actor.tint[1] = 64; actor.tint[2] = 40;
        for (i = 0; i < 3; i++) actor.pos[i] = nc_persist.player[i];
        actor.pos[1] = 0.f;
        nc_player = nc_world_spawn(&actor);
    }
}

/* ---- frame cost ------------------------------------------------------ */

/* The EE's cycle counter. Whether it runs at half the core clock is stated
 * rather than assumed: the raw count is on screen beside the derived figure,
 * so one look at a console that is plainly running at 60 confirms or refutes
 * the constant without another build. */
#define NC_TICKS_ASSUMED 147456000

static unsigned int nc_frame_ticks, nc_draw_ticks;
static unsigned int nc_tick_mark, nc_frame_mark;
static int nc_fps_x10;

static void nc_lab_frame_begin(void)
{
    unsigned int now = cpu_ticks();
    if (nc_frame_mark) {
        unsigned int elapsed = now - nc_frame_mark;
        /* A gentle average; a number that flickers every field is unreadable,
         * and an unreadable number cannot be reported back. */
        nc_frame_ticks = nc_frame_ticks ? (nc_frame_ticks * 7 + elapsed) / 8 : elapsed;
        nc_fps_x10 = nc_frame_ticks ? (int)((NC_TICKS_ASSUMED * 10ULL) / nc_frame_ticks) : 0;
    }
    nc_frame_mark = now;
    nc_tick_mark = now;
}

static void nc_lab_draw_end(void)
{
    unsigned int elapsed = cpu_ticks() - nc_tick_mark;
    nc_draw_ticks = nc_draw_ticks ? (nc_draw_ticks * 7 + elapsed) / 8 : elapsed;
}

/* ---- the 2D layer ---------------------------------------------------- */

static int nc_opt_backdrop;
static int nc_backdrop_scroll;

/* A multiple of both tile sizes, so the counter wrapping is itself seamless.
 * Wrapping at 1024 put a jump in the scroll every few seconds because 1024 is
 * not a whole number of tiles. */
#define NC_BACKDROP_PERIOD 480

/* Two layers of the same tile at different speeds and sizes. Parallax is the
 * oldest trick in 2D and it is still the fastest way to find out whether a
 * console can afford a full screen of overdraw before anything else is drawn
 * -- which is the question a 2D game asks first. */
static qword_t *nc_lab_backdrop(qword_t *q)
{
    int layer, x, y;
    if (!nc_opt_backdrop || NC_MATERIAL_COUNT <= 0)
        return q;
    nc_backdrop_scroll = (nc_backdrop_scroll + 1) % NC_BACKDROP_PERIOD;
    q = bind_texture(q, &nc_world_tex[0]);
    for (layer = 0; layer < 2; layer++) {
        int size = layer ? 96 : 160;
        int speed = layer ? 2 : 1;
        /* Both axes have to step by a whole tile to come back to where they
         * started. Scrolling y by half of x looked right until the horizontal
         * shift wrapped and the vertical one did not. */
        int shift = (nc_backdrop_scroll * speed) % size;
        int bright = layer ? 0x30 : 0x1c;
        for (y = -size; y < SCREEN_H + size; y += size)
            for (x = -size; x < SCREEN_W + size; x += size)
                q = sprite(q, x + shift, y + shift, size, size, 0, 0,
                           nc_materials[0].used_width,
                           nc_materials[0].used_height, bright);
    }
    return q;
}

/* ---- the menu -------------------------------------------------------- */

enum { LAB_SPIN, LAB_TEXTURE, LAB_FILTER, LAB_LIGHT, LAB_CULL, LAB_WIRE,
       LAB_BLEND, LAB_BRIGHT, LAB_MATERIAL, LAB_TINT, LAB_FOV, LAB_SPAWN,
       LAB_SPRITE, LAB_COLLIDE, LAB_BACKDROP, LAB_CAMERA, LAB_LEVEL, LAB_ROWS };

static const char *const LAB_NAMES[LAB_ROWS] = {
    "SPIN", "TEXTURE", "FILTER", "LIGHTING", "CULLING", "WIREFRAME",
    "BLEND", "BRIGHTNESS", "MATERIAL", "TINT", "FOV", "BOXES",
    "SPRITES", "COLLISION", "BACKDROP", "CAMERA", "LEVEL"};

/* Open on arrival. This is a test build; the menu is the reason to be here,
 * and it was being missed entirely on the first visit. */
static int nc_lab_open = 1;
static int nc_lab_row, nc_lab_spin, nc_lab_tint;

static const char *const LAB_SPIN_NAMES[3] = {"STILL", "SLOW", "FAST"};
static const char *const LAB_BLEND_NAMES[3] = {"OPAQUE", "ALPHA", "ADDITIVE"};
static const char *const LAB_TINT_NAMES[5] = {"WHITE", "RED", "GREEN", "BLUE", "AMBER"};
static const int LAB_TINTS[5][3] = {{128,128,128},{128,40,40},{40,128,60},
                                    {50,70,128},{128,100,40}};

static void nc_lab_apply_spin(void)
{
    static const float rate[3] = {0.f, 0.6f, 3.f};
    int i;
    for (i = 0; i < nc_object_count; i++) {
        if (i == nc_player) continue;
        nc_objects[i].spin[1] = rate[nc_lab_spin];
    }
}

static void nc_lab_apply_tint(void)
{
    int i, axis;
    for (i = 0; i < nc_object_count; i++) {
        if (i == nc_player) continue;          /* the character keeps its own */
        for (axis = 0; axis < 3; axis++)
            nc_objects[i].tint[axis] = LAB_TINTS[nc_lab_tint][axis];
    }
    for (i = 0; i < nc_sprite_count; i++)
        for (axis = 0; axis < 3; axis++)
            nc_sprites[i].tint[axis] = LAB_TINTS[nc_lab_tint][axis];
}

static void nc_lab_value(int row, char *out)
{
    switch (row) {
    case LAB_SPIN:     strcpy(out, LAB_SPIN_NAMES[nc_lab_spin]); break;
    case LAB_TEXTURE:  strcpy(out, nc_opt_perspective ? "PERSPECT" : "AFFINE"); break;
    case LAB_FILTER:   strcpy(out, nc_opt_filter ? "BILINEAR" : "NEAREST"); break;
    case LAB_LIGHT:    strcpy(out, nc_opt_lighting ? "ON" : "OFF"); break;
    case LAB_CULL:     strcpy(out, nc_opt_cull ? "ON" : "OFF"); break;
    case LAB_WIRE:     strcpy(out, nc_opt_wireframe ? "ON" : "OFF"); break;
    case LAB_BLEND:    strcpy(out, LAB_BLEND_NAMES[nc_opt_blend]); break;
    case LAB_BRIGHT:   strcpy(out, nc_opt_boost ? "BOOSTED" : "NORMAL"); break;
    case LAB_MATERIAL: sprintf(out, "%d OF %d", nc_objects[0].material + 1,
                               NC_MATERIAL_COUNT); break;
    case LAB_TINT:     strcpy(out, LAB_TINT_NAMES[nc_lab_tint]); break;
    case LAB_FOV:      sprintf(out, "%d DEG", (int)nc_cam_fov); break;
    case LAB_SPAWN:    sprintf(out, "%d OF %d", nc_object_count, NC_WORLD_MAX); break;
    case LAB_SPRITE:   sprintf(out, "%d OF %d", nc_sprite_count, NC_SPRITE_MAX); break;
    case LAB_COLLIDE:  strcpy(out, nc_opt_collide ? "ON" : "OFF"); break;
    case LAB_BACKDROP: strcpy(out, nc_opt_backdrop ? "PARALLAX" : "OFF"); break;
    case LAB_CAMERA:   strcpy(out, NC_CAM_NAMES[nc_cam_mode]); break;
    case LAB_LEVEL:    strcpy(out, NC_LEVEL_NAMES[nc_persist.level]); break;
    default:           out[0] = 0; break;
    }
}

static void nc_lab_adjust(int row, int step)
{
    int i;
    switch (row) {
    case LAB_SPIN:
        nc_lab_spin = (nc_lab_spin + 3 + step) % 3;
        nc_lab_apply_spin();
        break;
    case LAB_TEXTURE:  nc_opt_perspective = !nc_opt_perspective; break;
    case LAB_FILTER:   nc_opt_filter = !nc_opt_filter; break;
    case LAB_LIGHT:    nc_opt_lighting = !nc_opt_lighting; break;
    case LAB_CULL:     nc_opt_cull = !nc_opt_cull; break;
    case LAB_WIRE:     nc_opt_wireframe = !nc_opt_wireframe; break;
    case LAB_BLEND:    nc_opt_blend = (nc_opt_blend + 3 + step) % 3; break;
    case LAB_BRIGHT:   nc_opt_boost = !nc_opt_boost; break;
    case LAB_MATERIAL:
        if (NC_MATERIAL_COUNT > 0) {
            for (i = 0; i < nc_object_count; i++)
                nc_objects[i].material = (nc_objects[i].material + NC_MATERIAL_COUNT + step)
                                         % NC_MATERIAL_COUNT;
            for (i = 0; i < nc_sprite_count; i++)
                nc_sprites[i].material = (nc_sprites[i].material + NC_MATERIAL_COUNT + step)
                                         % NC_MATERIAL_COUNT;
        }
        break;
    case LAB_TINT:
        nc_lab_tint = (nc_lab_tint + 5 + step) % 5;
        nc_lab_apply_tint();
        break;
    case LAB_FOV:
        nc_cam_fov += (float)step * 5.f;
        if (nc_cam_fov < 25.f) nc_cam_fov = 25.f;
        if (nc_cam_fov > 100.f) nc_cam_fov = 100.f;
        break;
    case LAB_SPAWN:
        if (step > 0) {
            NCObject block;
            /* Spread new boxes around a ring so a stress test stays readable
             * rather than becoming one box in twenty places. */
            float angle = (float)nc_object_count * 0.9f;
            nc_object_init(&block);
            block.pos[0] = sinf(angle) * (3.f + (float)(nc_object_count % 3));
            block.pos[2] = cosf(angle) * (3.f + (float)(nc_object_count % 3));
            block.pos[1] = 0.4f;
            block.scale[0] = block.scale[1] = block.scale[2] = 0.5f;
            for (i = 0; i < 3; i++) block.tint[i] = LAB_TINTS[nc_lab_tint][i];
            if (nc_world_spawn(&block) >= 0) nc_persist.spawned++;
            nc_lab_apply_spin();
        } else if (nc_object_count > 1) {
            nc_object_count--;
            if (nc_player >= nc_object_count) nc_player = -1;
        }
        break;
    case LAB_SPRITE:
        if (step > 0) {
            float angle = (float)nc_sprite_count * 1.3f;
            int made = nc_sprite_spawn(sinf(angle) * 4.f, -1.f, cosf(angle) * 4.f,
                                       1.4f, 1.8f);
            if (made >= 0)
                for (i = 0; i < 3; i++) nc_sprites[made].tint[i] = LAB_TINTS[nc_lab_tint][i];
        } else if (nc_sprite_count > 0) {
            nc_sprite_count--;
        }
        break;
    case LAB_COLLIDE:  nc_opt_collide = !nc_opt_collide; break;
    case LAB_BACKDROP: nc_opt_backdrop = !nc_opt_backdrop; break;
    case LAB_CAMERA:
        nc_cam_mode = (nc_cam_mode + NC_CAM_MODES + step) % NC_CAM_MODES;
        break;
    case LAB_LEVEL:
        nc_lab_load_level(nc_persist.level + step);
        nc_lab_apply_spin();
        nc_lab_apply_tint();
        break;
    }
}

/* Returns 0 when the lab wants to hand the button back to the scene. */
static int nc_lab_update(unsigned int pressed, unsigned int held)
{
    if (pressed & PAD_SELECT) {
        nc_lab_open = !nc_lab_open;
        nc_sfx_family(nc_role_shift);
        return 1;
    }
    if (nc_lab_open) {
        if (pressed & PAD_UP)   { nc_lab_row = (nc_lab_row + LAB_ROWS - 1) % LAB_ROWS; nc_sfx_family(nc_role_move); }
        if (pressed & PAD_DOWN) { nc_lab_row = (nc_lab_row + 1) % LAB_ROWS; nc_sfx_family(nc_role_move); }
        if (pressed & PAD_LEFT)  { nc_lab_adjust(nc_lab_row, -1); nc_sfx_family(nc_role_confirm); }
        if (pressed & (PAD_RIGHT | PAD_CROSS)) { nc_lab_adjust(nc_lab_row, 1); nc_sfx_family(nc_role_confirm); }
        return 1;
    }

    /* The right stick drives the camera. That is not a period detail to be
     * respectful about -- it is how anyone picking up a pad today expects to
     * look around, and getting it wrong makes everything built on top feel
     * wrong. L2/R2 stay as a fallback for a pad with no sticks. */
    nc_cam_angle += (float)stick_rx * 0.00055f;
    nc_cam_height -= (float)stick_ry * 0.004f;
    if (held & PAD_L2) nc_cam_angle -= 0.03f;
    if (held & PAD_R2) nc_cam_angle += 0.03f;
    if (nc_cam_height < 1.f)  nc_cam_height = 1.f;
    if (nc_cam_height > 16.f) nc_cam_height = 16.f;

    if (nc_player >= 0 && nc_player < nc_object_count) {
        NCObject *actor = &nc_objects[nc_player];
        float speed = 0.12f;
        /* Which way the camera is actually looking, flattened onto the ground.
         * Taking this from the orbit angle instead was wrong the moment the
         * camera was the authored one, because an authored camera has a yaw
         * of its own that the orbit angle knows nothing about -- so "forward"
         * meant a different direction depending on the mode. */
        float look_x = nc_cam_target[0] - nc_cam_pos[0];
        float look_z = nc_cam_target[2] - nc_cam_pos[2];
        float length = sqrtf(look_x * look_x + look_z * look_z);
        float fx, fz, move_x = 0.f, move_z = 0.f;
        if (length < 0.001f) { fx = 0.f; fz = 1.f; }
        else { fx = look_x / length; fz = look_z / length; }

        if (held & PAD_UP)    { move_x += fx; move_z += fz; }
        if (held & PAD_DOWN)  { move_x -= fx; move_z -= fz; }
        /* Screen-left is the camera's left: rotate forward by a quarter turn. */
        if (held & PAD_LEFT)  { move_x -= fz; move_z += fx; }
        if (held & PAD_RIGHT) { move_x += fz; move_z -= fx; }
        /* The left stick does the same thing, proportionally. */
        move_x += (fx * (float)stick_ly * -1.f + fz * (float)stick_lx) / 128.f;
        move_z += (fz * (float)stick_ly * -1.f - fx * (float)stick_lx) / 128.f;

        if (move_x != 0.f || move_z != 0.f) {
            float scale = sqrtf(move_x * move_x + move_z * move_z);
            /* Diagonals must not be faster than straight lines. */
            if (scale > 1.f) { move_x /= scale; move_z /= scale; }
            actor->pos[0] += move_x * speed;
            actor->pos[2] += move_z * speed;
            /* Face where it is going, not where the camera is pointing. */
            actor->rot[1] = atan2f(move_x, move_z) * 57.2957795f;
        }
        nc_world_collide(nc_player);
    }
    return 0;
}

/* ---- the readout ----------------------------------------------------- */

static qword_t *nc_lab_draw(qword_t *q)
{
    char line[64];
    int i, y;

    /* Always on, menu or not. The numbers are the reason this screen exists,
     * and hiding them behind the menu would mean never seeing what the menu
     * just changed. */
    q = panel(q, 16, 14, 316, 104, 0x0a, 0x0c, 0x12);
    /* Culling reported as a share of what it was offered. "CULLED 74" alone
     * cannot be checked against anything; "74 OF 144" can. */
    sprintf(line, "DRAWN %2d  TRI %4d  CULL %3d/%3d  SPR %d",
            nc_stat_objects, nc_stat_tris, nc_stat_culled, nc_stat_faces,
            nc_stat_sprites);
    q = text(q, 26, 22, line, 0x70);
    sprintf(line, "FRAME %7u TK  DRAW %7u TK", nc_frame_ticks, nc_draw_ticks);
    q = text(q, 26, 40, line, 0x70);
    sprintf(line, "%d.%d FPS IF TICK IS %d HZ", nc_fps_x10 / 10, nc_fps_x10 % 10,
            NC_TICKS_ASSUMED);
    q = text(q, 26, 58, line, 0x50);
    sprintf(line, "CAM %s %d,%d,%d FOV %d", NC_CAM_NAMES[nc_cam_mode],
            (int)nc_cam_pos[0], (int)nc_cam_pos[1], (int)nc_cam_pos[2],
            (int)nc_cam_fov);
    q = text(q, 26, 76, line, 0x70);
    sprintf(line, "%s %s %s TOUCH %d",
            nc_opt_perspective ? "PERSP" : "AFFIN",
            nc_opt_cull ? "CULL" : "NOCULL",
            LAB_BLEND_NAMES[nc_opt_blend], nc_stat_touching);
    q = text(q, 26, 94, line, 0x70);

    /* Persistence, stated plainly. A number that survives a trip through the
     * conversation and back is the only proof that it survived. */
    sprintf(line, "LEVEL %s  VISITS %d  SPAWNED %d  CARRIED %d",
            NC_LEVEL_NAMES[nc_persist.level], nc_persist.visits,
            nc_persist.spawned, nc_persist.carried);
    q = text(q, 26, SCREEN_H - 60, line, 0x50);
    q = text(q, 26, SCREEN_H - 40,
             nc_lab_open ? "D-PAD MOVE/ADJUST   SELECT CLOSE"
                         : "L-STICK WALK  R-STICK LOOK  SELECT LAB", 0x48);
    q = text(q, 26, SCREEN_H - 22, "SQUARE BAG   TRIANGLE MENU", 0x40);

    /* The same material, drawn through the 2D path that the logo, the font and
     * the visual novel all use and that is known to work. If the tile shows
     * artwork and the boxes do not, the upload is fine and the fault is in how
     * the world pass samples it. If the tile is flat too, it is the upload.
     * One look, no rebuild. */
    if (NC_MATERIAL_COUNT > 0 && !nc_lab_open) {
        q = text(q, 26, SCREEN_H - 196, "MATERIAL VIA 2D PATH", 0x48);
        q = bind_texture(q, &nc_world_tex[0]);
        q = sprite(q, 26, SCREEN_H - 180, 96, 96, 0, 0,
                   nc_materials[0].used_width, nc_materials[0].used_height, 0x80);
        if (NC_MATERIAL_COUNT > 1) {
            q = bind_texture(q, &nc_world_tex[1]);
            q = sprite(q, 130, SCREEN_H - 180, 96, 96, 0, 0,
                       nc_materials[1].used_width, nc_materials[1].used_height, 0x80);
        }
    }

    if (!nc_lab_open)
        return q;

    q = panel(q, 348, 8, 280, 16 + LAB_ROWS * 18, 0x0a, 0x0c, 0x12);
    q = panel(q, 348, 8, 280, 2, 0x5f, 0xd4, 0xd0);
    for (i = 0; i < LAB_ROWS; i++) {
        int bright = i == nc_lab_row ? 0x80 : 0x44;
        y = 18 + i * 18;
        q = text(q, 354, y, i == nc_lab_row ? ">" : " ", bright);
        q = text(q, 370, y, LAB_NAMES[i], bright);
        nc_lab_value(i, line);
        q = text(q, 504, y, line, bright);
    }
    return q;
}

static void nc_lab_init(void)
{
    nc_persist.level = NC_LEVEL_AUTHORED;
    nc_lab_load_level(NC_LEVEL_AUTHORED);
    nc_lab_apply_spin();
}
