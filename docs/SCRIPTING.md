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

### Sound
| | |
|---|---|
| `play_sound(id)` | Play a sample. `id` is its index in `scene.json`'s `sounds`. |
| `sound_count()` | How many are loaded. |
| `play_music(2)` | Start a looping CD audio track. Track 1 is the game, so music starts at 2. |
| `stop_music()` | Stop it. |

Music is a CD-DA track on the disc, not an SPU sample -- a song is far larger
than the SPU's 512 KB. The drive streams it straight into the mixer, so it costs
no RAM and no CPU. List the files under `"music"` in `scene.json` and `ncc build`
adds them to the disc layout.

### Feel
| | |
|---|---|
| `shake(n)` | Screen shake, decaying. 3 is a hit, 9 is taking damage, 16 is the cap. |

Sprites marked `"fixed": true` in `scene.json` ignore the shake -- that is how
side panels and the HUD stay still while the playfield jolts.

### Arrays

Fixed size, declared at the top of the file. There is no allocator, so the size
is part of the declaration:

```gdscript
var bullets: array[16]

func _update():
    bullets[0] = bullets[0] + 1
```

An out-of-range index reads as `0` and writes nowhere rather than crashing --
there is no MMU here, so a stray write would corrupt memory silently.

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

Sprite order is also **draw order, back to front reversed**: sprite 0 ends up on
top. Put panels and overlays first, background last.

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

### Saving
| | |
|---|---|
| `save_set(slot, value)` | Put an int in one of **16** slots. RAM only. |
| `save_get(slot)` | Read one back. Out-of-range slots read as `0`. |
| `save_write()` | Write all 16 slots to the memory card. `1` on success. |
| `save_read()` | Load them back. `0` if there is no card and no save yet. |
| `save_erase()` | Delete the file. |

Sixteen ints is the whole format, and that is on purpose: a high score, a level
number, some flags. There is no allocator and nothing to serialise strings with.
The file takes one 8 KB block — the smallest a PlayStation save can be.

`save_read()` returning `0` is the normal state on a first run. Treat it as "no
save", not as an error, and never block the player on it:

```
func _ready():
    if save_read() == 1:
        hiscore = save_get(0)
```

The save shows up in the console's own memory card screen with your project's
name and a small icon. Everything about it — the file name, the title — comes
from the project name, so two Neon Coffee games never collide.

Writing takes a few frames and blocks while it happens. Save at a natural pause
(game over, a checkpoint), never every frame.

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
- **Nothing can be created at run time.** Every sprite and object exists from the
  start; you show, hide and move them. Allocate a pool up front -- the `shooter`
  template does this for its bullets.
- **No collision.** You can compare positions yourself with `abs()`, but nothing
  is built in.
- **Integers only**, 32-bit.
- **The debug font only.** `draw_text()` works, but it is PSn00bSDK's built-in
  font -- fixed size, one colour. A custom font needs its own texture work.

## Seeing what it generated

The C is written to `src/nc_script_generated.c` in your project. Reading it is
the fastest way to understand what a line of NCScript actually costs, and it is
plain C — if you ever outgrow the script, that file is a starting point rather
than a wall.
