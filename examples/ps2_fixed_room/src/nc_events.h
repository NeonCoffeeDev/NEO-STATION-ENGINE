/* Generated PS2 fixed-room events. Do not edit. */
static void nc_events(int start, unsigned int pressed, int zone) {
    (void)start; (void)pressed; (void)zone;
    static unsigned int tick;
    if (start) tick = 0; else if (tick < 0xffffffffu) tick++;
    static unsigned int next_15;
    if (start) next_15 = 0;
    static int var_presses;
    if(start) var_presses=0;
    if (start) {
        nc_action(2, 0);
    }
    if (pressed & PAD_CROSS) {
        if (tick >= next_15) { next_15 = tick + 20;
        nc_action(1, 0);
        }
    }
    if (pressed & PAD_START) {
        nc_action(2, 0);
    }
    if (pressed & PAD_L1) {
        nc_action(0, 0);
    }
    if (pressed & PAD_R1) {
        nc_action(0, 2);
    }
    if (zone == 0) {
        nc_action(0, 0);
    }
    if (zone == 1) {
        nc_action(0, 1);
    }
    if (pressed & PAD_SQUARE) {
        nc_move_to(-2.00000000f, 1.50000000f, 90);
    }
    if (pressed & PAD_TRIANGLE) {
        var_presses += 1;
        if(var_presses>32767) var_presses=32767;
        if(var_presses< -32767) var_presses=-32767;
        if(var_presses == 3) {
        nc_action(0, 2);
        }
    }
    if (!start && nc_move_arrived) {
        nc_action(1, 0);
    }
    if (pressed & PAD_CIRCLE) {
        nc_action(3, 0);
    }
}
