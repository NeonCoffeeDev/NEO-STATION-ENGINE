"""The API NCScript can call, and the C function each name maps to.

This is the single source of truth. `ncscript.py` checks calls against it, and
`nc_script.c` in every project implements the C side. If they disagree the build
fails at link time rather than misbehaving on the console.

Keep it small. Every entry here is a promise the runtime has to keep on a 2 MB
machine, and a name the user has to learn.
"""

# name -> {"c": C function, "args": expected count or None for any}
FUNCTIONS = {
    # --- output ---
    "print":         {"c": "nc_s_print",        "args": 1},
    "print_num":     {"c": "nc_s_print_num",    "args": 1},

    # --- text on screen (built-in debug font) ---
    # Screen coordinates, 0,0 top-left, 320x240.
    "draw_text":     {"c": "nc_s_draw_text",    "args": 3},
    "draw_num":      {"c": "nc_s_draw_num",     "args": 3},

    # --- sound ---
    # Samples live in the SPU's own RAM, so playing one costs almost nothing.
    "play_sound":    {"c": "nc_s_play_sound",   "args": 1},
    "sound_count":   {"c": "nc_s_sound_count",  "args": 0},
    # Music is a CD track, streamed by the drive. Track 1 is the game data, so
    # the first song is track 2.
    "play_music":    {"c": "nc_s_play_music",   "args": 1},
    "stop_music":    {"c": "nc_s_stop_music",   "args": 0},

    # --- saving to a memory card ---
    # Values live in RAM; save_write()/save_read() move them to and from the
    # card. Both return 1 on success, 0 if there is no card or no save.
    "save_get":      {"c": "nc_s_save_get",     "args": 1},
    "save_set":      {"c": "nc_s_save_set",     "args": 2},
    "save_write":    {"c": "nc_s_save_write",   "args": 0},
    "save_read":     {"c": "nc_s_save_read",    "args": 0},
    "save_erase":    {"c": "nc_s_save_erase",   "args": 0},

    # --- feel ---
    "shake":         {"c": "nc_s_shake",        "args": 1},

    # --- input ---
    # held() is true every frame the button is down; pressed() only on the frame
    # it goes down, which is what you want for menus and jumps.
    "btn_held":      {"c": "nc_s_btn_held",     "args": 1},
    "btn_pressed":   {"c": "nc_s_btn_pressed",  "args": 1},

    # --- objects, addressed by their index in the scene ---
    "count":         {"c": "nc_s_count",        "args": 0},
    "get_x":         {"c": "nc_s_get_x",        "args": 1},
    "get_y":         {"c": "nc_s_get_y",        "args": 1},
    "get_z":         {"c": "nc_s_get_z",        "args": 1},
    "set_pos":       {"c": "nc_s_set_pos",      "args": 4},
    "move":          {"c": "nc_s_move",         "args": 4},
    "set_rot":       {"c": "nc_s_set_rot",      "args": 4},
    "spin":          {"c": "nc_s_spin",         "args": 4},
    "show":          {"c": "nc_s_show",         "args": 1},
    "hide":          {"c": "nc_s_hide",         "args": 1},

    # --- sprites: flat 2D quads in screen space, drawn over the 3D pass ---
    "sprite_count":   {"c": "nc_s_sprite_count",   "args": 0},
    "sprite_x":       {"c": "nc_s_sprite_x",       "args": 1},
    "sprite_y":       {"c": "nc_s_sprite_y",       "args": 1},
    "sprite_set_pos": {"c": "nc_s_sprite_set_pos", "args": 3},
    "sprite_move":    {"c": "nc_s_sprite_move",    "args": 3},
    "sprite_frame":   {"c": "nc_s_sprite_frame",   "args": 3},
    "sprite_show":    {"c": "nc_s_sprite_show",    "args": 1},
    "sprite_hide":    {"c": "nc_s_sprite_hide",    "args": 1},

    # --- 2D physics ---
    # Velocity is 20.12 fixed point: 4096 is one pixel per frame. Positions stay
    # whole pixels and the sprite carries the remainder, so half a pixel per
    # frame moves you one pixel every other frame rather than never.
    "sprite_set_solid": {"c": "nc_s_sprite_set_solid", "args": 2},
    "sprite_set_vel":   {"c": "nc_s_sprite_set_vel",   "args": 3},
    "sprite_vx":        {"c": "nc_s_sprite_vx",        "args": 1},
    "sprite_vy":        {"c": "nc_s_sprite_vy",        "args": 1},
    "move_and_slide":   {"c": "nc_s_move_and_slide",   "args": 3},
    "physics_step":     {"c": "nc_s_physics_step",     "args": 1},
    "on_floor":         {"c": "nc_s_on_floor",         "args": 1},
    "on_ceiling":       {"c": "nc_s_on_ceiling",       "args": 1},
    "on_wall":          {"c": "nc_s_on_wall",          "args": 1},
    "set_gravity":      {"c": "nc_s_set_gravity",      "args": 1},
    "set_terminal":     {"c": "nc_s_set_terminal",     "args": 1},
    "touching":         {"c": "nc_s_touching",         "args": 2},

    # --- the 2D view ---
    # Sprites are screen-space, so a level bigger than the screen is an offset
    # subtracted at draw time rather than a camera. Positions stay in world
    # coordinates and collision never has to know the view moved.
    "scroll_set":       {"c": "nc_s_scroll_set",       "args": 2},
    "scroll_by":        {"c": "nc_s_scroll_by",        "args": 2},
    "scroll_x":         {"c": "nc_s_scroll_x",         "args": 0},
    "scroll_y":         {"c": "nc_s_scroll_y",         "args": 0},
    "scroll_follow":    {"c": "nc_s_scroll_follow",    "args": 3},
    "sprite_set_flip":  {"c": "nc_s_sprite_set_flip",  "args": 2},

    # --- prototyping helpers ---
    "draw_text_center": {"c": "nc_s_draw_text_center", "args": 2},
    "sign":             {"c": "nc_s_sign",             "args": 1},
    "approach":         {"c": "nc_s_approach",         "args": 3},
    "lerp":             {"c": "nc_s_lerp",             "args": 3},
    "rand_range":       {"c": "nc_s_rand_range",       "args": 2},
    "dist":             {"c": "nc_s_dist",             "args": 4},
    "every":            {"c": "nc_s_every",            "args": 1},

    # --- camera ---
    "camera_set":    {"c": "nc_s_camera_set",   "args": 6},
    "camera_move":   {"c": "nc_s_camera_move",  "args": 3},
    "camera_turn":   {"c": "nc_s_camera_turn",  "args": 1},
    "camera_x":      {"c": "nc_s_camera_x",     "args": 0},
    "camera_y":      {"c": "nc_s_camera_y",     "args": 0},
    "camera_z":      {"c": "nc_s_camera_z",     "args": 0},
    "camera_yaw":    {"c": "nc_s_camera_yaw",   "args": 0},

    # --- scenes ---
    # goto_scene() takes effect at the end of the frame, so it is safe to call
    # in the middle of update logic.
    "goto_scene":    {"c": "nc_s_goto_scene",   "args": 1},
    "scene":         {"c": "nc_s_scene",        "args": 0},
    "scene_count":   {"c": "nc_s_scene_count",  "args": 0},

    # --- misc ---
    "frame":         {"c": "nc_s_frame",        "args": 0},
    "set_clear":     {"c": "nc_s_set_clear",    "args": 3},
    "abs":           {"c": "nc_s_abs",          "args": 1},
    "min":           {"c": "nc_s_min",          "args": 2},
    "max":           {"c": "nc_s_max",          "args": 2},
    "clamp":         {"c": "nc_s_clamp",        "args": 3},
    "rand":          {"c": "nc_s_rand",         "args": 1},

    # Fixed-point trig: the angle is 0..4095 for a full turn, and the result is
    # -4096..4096 meaning -1.0..1.0. Multiply and then divide by 4096 (or shift
    # right 12) to use it.
    "sin":           {"c": "nc_s_sin",          "args": 1},
    "cos":           {"c": "nc_s_cos",          "args": 1},
}

# Bare names that become C constants.
CONSTANTS = {
    "BTN_UP":        "PAD_UP",
    "BTN_DOWN":      "PAD_DOWN",
    "BTN_LEFT":      "PAD_LEFT",
    "BTN_RIGHT":     "PAD_RIGHT",
    "BTN_CROSS":     "PAD_CROSS",
    "BTN_CIRCLE":    "PAD_CIRCLE",
    "BTN_SQUARE":    "PAD_SQUARE",
    "BTN_TRIANGLE":  "PAD_TRIANGLE",
    "BTN_START":     "PAD_START",
    "BTN_SELECT":    "PAD_SELECT",
    "BTN_L1":        "PAD_L1",
    "BTN_R1":        "PAD_R1",
    "BTN_L2":        "PAD_L2",
    "BTN_R2":        "PAD_R2",

    # 4096 is 1.0 in the fixed-point format the hardware uses, and also one
    # full turn for rotations.
    "ONE":           "4096",
    "TURN":          "4096",
}
