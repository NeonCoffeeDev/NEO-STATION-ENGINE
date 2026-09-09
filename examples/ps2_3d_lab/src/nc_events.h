/* Generated PS2 fixed-room events. Do not edit. */
static void nc_events(int start, unsigned int pressed, int zone) {
    (void)start; (void)pressed; (void)zone;
    static int active, pending, initialized;
    static unsigned int tick;
    int entering = 0;
    if (start || !initialized) { active = 4; pending = 0; initialized = 1; entering = 1; }
    else if (pending) { active = pending; pending = 0; entering = 1; }
    if (entering) { tick = 0; pressed = 0; zone = -1; } else if (tick < 0xffffffffu) tick++;
    static int inside_1;
    int hit_1 = (1 && nc_object_pos[0][0] >= 1.00000000f && nc_object_pos[0][0] < 4.00000000f && nc_object_pos[0][1] >= -2.00000000f && nc_object_pos[0][1] < 2.00000000f && nc_object_pos[0][2] >= -2.00000000f && nc_object_pos[0][2] < 2.00000000f);
    int enter_1 = !start && hit_1 && !inside_1;
    int leave_1 = !start && !hit_1 && inside_1;
    inside_1 = hit_1;
    if (active == 4 && !pending && (!entering && (enter_1))) {
        nc_action(5, 2);
    }
    if (active == 4 && !pending && (!entering && (pressed & PAD_SELECT))) {
        nc_object_pos[0][0] = 2.00000000f;
        nc_object_pos[0][1] = 0.00000000f;
        nc_object_pos[0][2] = 0.00000000f;
    }
}
