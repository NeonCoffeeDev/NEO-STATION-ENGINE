# NCScript

## Why this exists, and what it is not

**GDScript cannot run on a PlayStation 1.** Godot's runtime is tens of megabytes
of C++ with a garbage-collected VM; the console has 2 MB of RAM, a 33 MHz MIPS
R3000, and no floating-point unit. That is not a porting problem, it is an
order-of-magnitude problem.

But *translating* a restricted subset to C costs nothing at run time. NCScript is
a **transpiler**: `ncc build` reads `script.ncs`, emits C, and the same MIPS
compiler that builds the engine compiles it into native code. There is no
interpreter on the console. A `move()` call in your script is a direct function
call in the finished executable.

So you write something that looks like GDScript, and the console runs machine
code.

## The trade

What you get:

```gdscript
var speed = 24                     # variables
func _ready():                     # once, when a scene starts
func _update():                    # every frame
func my_own(a, b):                 # your own functions
if / elif / else, while, for i in range(n)
+ - * / %, == != < > <= >=, and / or / not
```

What it refuses, and why:

| Not supported | Reason |
|---------------|--------|
| `float` | No FPU. Use ints, or fixed point where `4096` means `1.0`. |
| arrays, dictionaries | Would need dynamic allocation. |
| classes, `extends` | No object model on the console. |
| strings beyond literals | No string handling in 2 MB. |

Every rejection is a compile error with a line number. A transpiler that quietly
dropped code you wrote would be worse than no transpiler.

## Structure

```gdscript
var score = 0                 # module-level state, persists across scenes

func _ready():                # called when a scene loads, and again on each
    print("hello")            # goto_scene()

func _update():               # called once per frame, 60 times a second
    if btn_pressed(BTN_START):
        goto_scene(1)
```

Objects are addressed by **index within the current scene**, counting from 0 in
the order they appear in `scene.json` (which is the order the groups export from
Godot). Object 0 in a level is conventionally the player.

## The API

### Output
| | |
|---|---|
| `print(text)` | Write a string to the PS1 TTY. Shows in NC Studio's **PS1 TTY** pane. |
| `print_num(n)` | Write a number. |
| `draw_text(x, y, "TEXT")` | Draw on the TV with the debug font. 0,0 top-left of 320x240. |
| `draw_num(x, y, n)` | Same, for a number -- scores, timers, debug values. |

### Input
| | |
|---|---|
| `btn_held(b)` | True every frame the button is down. |
| `btn_pressed(b)` | True only on the frame it goes down. Use this for menus and jumps. |

Buttons: `BTN_UP` `BTN_DOWN` `BTN_LEFT` `BTN_RIGHT` `BTN_CROSS` `BTN_CIRCLE`
`BTN_SQUARE` `BTN_TRIANGLE` `BTN_L1` `BTN_R1` `BTN_L2` `BTN_R2` `BTN_START`
`BTN_SELECT`.

### Objects
| | |
|---|---|
| `count()` | How many objects in this scene. |
| `get_x(id)` `get_y(id)` `get_z(id)` | Read a position. |
| `set_pos(id, x, y, z)` | Move it somewhere. |
| `move(id, dx, dy, dz)` | Move it by an offset. |
| `set_rot(id, x, y, z)` | Set rotation. `4096` is a full turn. |
| `spin(id, x, y, z)` | Rotation added per frame; `0, 12, 0` turns slowly. |
| `show(id)` / `hide(id)` | Visibility. |

### Sprites (2D)

Sprites are flat textured quads in **screen space** -- pixels on the 320x240
display, 0,0 top-left. No camera, no depth sorting, no GTE. They draw over the 3D
pass and under the text.

| | |
|---|---|
| `sprite_count()` | How many sprites in this scene. |
| `sprite_x(id)` `sprite_y(id)` | Read a position. |
| `sprite_set_pos(id, x, y)` | Place it. |
| `sprite_move(id, dx, dy)` | Nudge it. |
| `sprite_frame(id, u, v)` | Move the window into the texture -- this is animation. |
| `sprite_show(id)` / `sprite_hide(id)` | Visibility. |

Animation is one sheet plus a moving UV window. With four 32x32 frames side by
side:

```gdscript
sprite_frame(0, anim * 32, 0)
```

A game can be entirely 2D: a package with no meshes at all is fine.

### Camera
| | |
|---|---|
| `camera_set(x, y, z, rx, ry, rz)` | Place it outright. |
| `camera_move(dx, dy, dz)` | Nudge it. |
| `camera_turn(d)` | Add to the yaw. |
| `camera_x()` `camera_y()` `camera_z()` `camera_yaw()` | Read it back. |

### Scenes
| | |
|---|---|
| `goto_scene(n)` | Switch scene. Takes effect at the end of the frame, so it is safe mid-logic. `_ready()` runs again. |
| `scene()` | Which scene is running, from 0. |
| `scene_count()` | How many the package holds. |

### Numbers
| | |
|---|---|
| `abs(v)` `min(a,b)` `max(a,b)` `clamp(v,lo,hi)` | The usual. |
| `rand(n)` | 0 to n-1. |
| `sin(a)` `cos(a)` | Fixed point. Angle `0..4095` is a full turn; result `-4096..4096` means `-1.0..1.0`. |
| `frame()` | Frames since the scene started. |
| `set_clear(r,g,b)` | Background colour, 0-255. |

## Fixed point, briefly

There is no `float`. Where you would want fractions, use **fixed point**: the
number `4096` represents `1.0`. To use a fraction, multiply then divide:

```gdscript
var bob = sin(frame() * 16) / 24      # sin gives -4096..4096, so this is +/-170
set_pos(0, 0, bob, 900)
```

The same `4096` is one full turn for rotations, which is deliberate — it means
`sin()` and `set_rot()` speak the same units.

## A complete example

This is `script.ncs` from the `game` template: a menu and a level.

```gdscript
var player = 0
var speed = 24
var pulse = 0

func _ready():
    if scene() == 0:
        print("main menu -- press START")
    else:
        print("level 1 -- SELECT to go back")

func _update():
    if scene() == 0:
        update_menu()
    else:
        update_level()

func update_menu():
    pulse = pulse + 1
    var bob = sin(pulse * 16) / 24
    set_pos(0, 0, bob, 900)
    if btn_pressed(BTN_START):
        goto_scene(1)

func update_level():
    if btn_held(BTN_LEFT):
        move(player, -speed, 0, 0)
    if btn_held(BTN_RIGHT):
        move(player, speed, 0, 0)
    if btn_pressed(BTN_SELECT):
        goto_scene(0)
```

## Where it runs out

Honest limits of the current version:

- **One script per project.** Not one per object. Branch on `scene()` and object
  index instead. Per-object scripts need an object model that does not exist yet.
- **No collision.** You can compare positions yourself with `abs()`, but nothing
  is built in.
- **No sound.**
- **Integers only**, 32-bit.
- **The debug font only.** `draw_text()` works, but it is PSn00bSDK's built-in
  font -- fixed size, one colour. A custom font needs its own texture work.

## Seeing what it generated

The C is written to `src/nc_script_generated.c` in your project. Reading it is
the fastest way to understand what a line of NCScript actually costs, and it is
plain C — if you ever outgrow the script, that file is a starting point rather
than a wall.
