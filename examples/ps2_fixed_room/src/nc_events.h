/* Generated PS2 fixed-room events. Do not edit. */
#include "nc_code_generated.h"
static void nc_events(int start, unsigned int pressed, int zone) {
    static int active, pending, initialized;
    static unsigned int tick;
    int entering = 0;
    if (start || !initialized) { active = 1; pending = 0; initialized = 1; entering = 1; }
    else if (pending) { active = pending; pending = 0; entering = 1; }
    if (entering) { tick = 0; pressed = 0; zone = -1; } else if (tick < 0xffffffffu) tick++;
    static unsigned int next_15;
    if (entering) next_15 = 0;
    static int var_presses;
    if(start) var_presses=0;
    static int inside_101;
    int hit_101 = (1 && player_x >= -3.00000000f && player_x < 0.00000000f && 0.0f >= -1.00000000f && 0.0f < 2.00000000f && player_z >= -2.00000000f && player_z < 2.10000000f);
    int enter_101 = !start && hit_101 && !inside_101;
    int leave_101 = !start && !hit_101 && inside_101;
    inside_101 = hit_101;
    static int inside_102;
    int hit_102 = (1 && player_x >= 0.00000000f && player_x < 3.10000000f && 0.0f >= -1.00000000f && 0.0f < 2.00000000f && player_z >= -2.00000000f && player_z < 2.10000000f);
    int enter_102 = !start && hit_102 && !inside_102;
    int leave_102 = !start && !hit_102 && inside_102;
    inside_102 = hit_102;
    if (active == 1 && !pending && (entering)) {
        nc_action(2, 0);
        if (!pending) pending = 4;
    }
    if (active == 4 && !pending && (!entering && (pressed & PAD_CROSS))) {
        if (tick >= next_15) { next_15 = tick + 20;
        nc_action(1, 0);
        }
    }
    if (active == 4 && !pending && (!entering && (pressed & PAD_START))) {
        nc_action(2, 0);
    }
    if (active == 4 && !pending && (!entering && (pressed & PAD_L1))) {
        nc_action(0, 0);
    }
    if (active == 4 && !pending && (!entering && (pressed & PAD_R1))) {
        nc_action(0, 2);
    }
    if (active == 4 && !pending && (!entering && (enter_101))) {
        nc_action(0, 0);
    }
    if (active == 4 && !pending && (!entering && (enter_102))) {
        nc_action(0, 1);
    }
    if (active == 4 && !pending && (!entering && (pressed & PAD_SQUARE))) {
        nc_move_to(-2.00000000f, 1.50000000f, 90);
    }
    if (active == 4 && !pending && (!entering && (pressed & PAD_TRIANGLE))) {
        var_presses += 1;
        if(var_presses>32767) var_presses=32767;
        if(var_presses< -32767) var_presses=-32767;
        if(var_presses == 3) {
        nc_action(0, 2);
        }
    }
    if (active == 4 && !pending && (!entering && (!start && nc_move_arrived))) {
        nc_action(1, 0);
    }
    if (active == 4 && !pending && (!entering && (pressed & PAD_CIRCLE))) {
        nc_action(3, 0);
    }
    if (active == 4 && !pending && (entering)) {
        nc_action(0, 0);
    }
}
