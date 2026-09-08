/* Generated PS2 fixed-room events. Do not edit. */
static void nc_events(int start, unsigned int pressed, int zone) {
    (void)start; (void)pressed; (void)zone;
    if (start) {
        nc_action(2, 0);
    }
    if (pressed & PAD_CROSS) {
        nc_action(1, 0);
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
}
