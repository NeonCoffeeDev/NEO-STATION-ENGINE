# Roadmap

Ordered by risk, highest first. Each milestone must produce something that runs.

## M0 - Environment  [DONE]
`ncc doctor` is clean for PS1. PSn00bSDK builds its own examples on this machine.
Nothing NC-specific yet; this is just proving the ground is solid.

## M1 - Triangle on hardware  [DONE]
A hand-written C program using PSn00bSDK draws a spinning textured cube, packed into a
`.bin`/`.cue` that boots in DuckStation. **No Godot, no ncc, no .ncpkg.** This exists
to find out what the runtime actually needs before anything is designed around it.

## M2 - Data-driven runtime  [DONE]
Same cube, but the geometry now comes from a `.ncpkg` on the disc instead of a C array.
Locks down MESH/TEX0/CLUT. `ncc` gains a `pack` command that builds one by hand.

## M3 - Godot -> ncpkg  [DONE, boxes only]
The addon exists. A `.tscn` with `NCStaticMesh` nodes compiles through `ncc build
--target ps1` to the same booting cube. This is the first end-to-end vertical slice.

## M4 - Make it a game engine  (in progress)
Controller input, a camera you can move, multiple meshes, a scene graph, audio,
collision. Roughly in that order, each one hardware-verified.

## M5 - Editor feedback
Budget meters, per-asset compatibility warnings, PS1 preview shader. Deferred to here
on purpose — the budgets are only truthful once the runtime knows its real costs.

## M6 - PS2 backend
Repeat M1-M4 against PS2SDK + gsKit. Expect the renderer to share nothing with PS1.

## M7 - A real game
The engine is not validated until something is shipped with it.


---

## Status, 2026-09-05

M0-M3 are done and verified on the emulator with OpenBIOS.

The loop that exists today: arrange boxes in Godot -> "Export to NC" writes
scene.json -> `ncc build` compiles it to a .ncpkg and embeds it -> the runtime
draws it. No C is edited at any point.

What M3 does **not** yet cover, and should before M4 is called finished:

- **Only boxes are first-class.** Any other mesh is exported as triangles padded
  into degenerate quads. It draws, but it wastes GPU time and the normals are
  per-face rather than smooth. Triangles (`POLY_G3`) belong in the format.
- **No textures.** Everything is flat-lit Gouraud. This is the single biggest
  visual gap versus a real PS1 game, and it needs the TIM format plus VRAM
  allocation in the packer.
- **No camera in the runtime.** Positions are baked relative to the Godot camera
  at export time, so the viewpoint cannot move at runtime. A real camera
  transform is a prerequisite for anything playable.
- **Compound rotations are approximate.** Euler order differs between Godot and
  the PS1's RotMatrix. Single-axis rotations are exact; combined ones drift.
- **No collision, no gameplay, no audio.** That is M4.


## Update, 2026-09-06

Added since the last note:

- **A runtime camera.** The viewpoint moves; it is no longer baked at export.
- **Multiple scenes** in one package, with `goto_scene()`. Menu and level 1 both
  exist in the `game` template.
- **NCScript**, a GDScript-shaped language transpiled to C at build time. This is
  the answer to "how do I program it without writing C" -- see docs/SCRIPTING.md.
- **A live scene layer**, so scripts can move objects. The package stays
  read-only; a mutable copy is made per scene.

Still missing, in the order they hurt most:

1. ~~**Textures.**~~ **Done.** 8-bit CLUT, 8 slots, PNG in / VRAM out. Meshes
   name a texture and get POLY_FT4 with lighting still applied.
2. **2D.** Sprites and tilemaps in screen space. Cheap on this hardware once
   textures exist -- and arguably the faster route to a finished-looking game.
3. **Collision.** Scripts can compare positions by hand; nothing is built in.
4. ~~**Text on screen.**~~ **Done**, via the SDK debug font. A custom font is
   still open.
5. **Audio.**
6. **Per-object scripts.** One script per project today; branch on `scene()`.


## Update, 2026-09-06 (later)

- **Textures.** PNG -> 8-bit CLUT -> VRAM, 8 slots of up to 256x240. Textured
  faces use POLY_FT4 and are still lit, so the texture is modulated rather than
  replacing the shading. VRAM layout is documented in one place, in
  tools/ncc/ncc/textures.py, and shipped to the console rather than recomputed
  there.
- **Text on the TV**, via the SDK debug font: draw_text() and draw_num().

That clears the prerequisite for 2D. Sprites are textured quads in screen space
and skip the GTE entirely, so the remaining work is a screen-space primitive path
plus a Godot 2D exporter -- not another VRAM problem.

Still open, in order:

1. **2D.** Sprites and tilemaps. The texture work above is the hard part; this is
   mostly a second draw path.
2. **Godot texture export.** Textures are referenced from scene.json by hand
   today; the exporter should pull them from material albedo.
3. **Collision.**
4. **Audio.**
5. **Per-object scripts**, and 4-bit textures for twice the VRAM budget.


## Update, 2026-09-06 (2D)

- **Sprites.** Screen-space textured quads, drawn after the 3D pass and under the
  text. No GTE, no depth sort -- which is why 2D is comfortable here. Scripts get
  sprite_move / sprite_frame / sprite_show, and animation is a moving UV window
  over one sheet.
- **2D-only packages.** A game with no meshes is valid; the `sprite2d` template
  is one.
- **Release builds.** `--release` is -O2 and inlines the script wrappers.

Still open:

1. **Godot texture and 2D export.** Textures and sprites are declared in
   scene.json by hand. The exporter should pull textures from material albedo,
   and Sprite2D nodes from a Godot 2D scene.
2. **Collision.** Scripts compare positions by hand today.
3. **Audio.** Nothing at all yet -- probably the biggest remaining hole.
4. **Transparency.** Sprites are opaque; no alpha or semi-transparency blending.
5. **4-bit textures** for twice the VRAM budget, and LTO so the nc_s_* wrappers
   inline too.


## Update, 2026-09-06 (transparency and Godot export)

- **Transparency.** Images with alpha reserve palette entry 0 as the hardware's
  one transparent value (0x0000) and quantise the rest to 255 colours. Sprites
  are no longer opaque rectangles.
- **Godot texture export.** A material's albedo texture is written to textures/
  as a PNG and referenced automatically. No more declaring them by hand.
- **Godot 2D export.** Sprite2D nodes become sprites; region_rect picks the
  frame. The sprite2d template ships a 320x240 Godot 2D project, so the editor
  viewport matches the console pixel for pixel.
- **One shared editor plugin** in templates/_godot_addon, copied into any
  template that has a godot/ folder -- two copies of a 475-line exporter would
  have drifted within a week.

Still open:

1. **Audio.** Nothing at all. The biggest remaining hole.
2. **Collision.** Scripts compare positions by hand.
3. **Semi-transparent blending.** Alpha-keyed holes work; 50%% blending does not.
4. **Per-object scripts**, 4-bit textures, LTO.


## Update, 2026-09-06 (audio, arrays, a real game, and diagnostics)

- **Sound.** WAV to SPU-ADPCM, encoded here rather than shelling out to psxavenc.
  Exhaustive filter/shift search per block: 54.6 dB SNR on a test chirp at 3.5:1.
  Samples upload to the SPU's own 512 KB; play_sound() costs the CPU nothing.
- **Arrays in NCScript.** Fixed size, top level, bounds-checked -- an out-of-range
  write on a machine with no MMU is a lock-up, not an exception.
- **The `shooter` template.** A complete side-scrolling shmup: parallax
  starfield, bullet pool, respawning enemies, box collision, lives, score, sound
  and a game over. 250 lines of generated C.
- **`ncc check`.** Runs the real converters and reports every budget plus what
  will stop the build, with the reason and the fix. Studio runs it automatically
  when a build fails.
- **docs/LIMITS.md.** Every rule and where it comes from.

Still open:

1. **Music.** Sound effects work; streamed music does not, and would need CD
   streaming rather than SPU RAM.
2. **Semi-transparent blending.** Alpha-keyed holes work; 50%% blending does not.
3. **Per-object scripts**, 4-bit textures, LTO.
4. **PS2.** Untouched -- see M6.


## Update, 2026-09-06 (music, and the shooter goes vertical)

- **Music via CD audio.** Red Book tracks on the disc, streamed by the drive
  into the SPU mixer: no main RAM, no SPU RAM, no CPU. `ncc build` keeps the
  marked region of iso.xml in step with the "music" list in scene.json, because
  forgetting that produces a game that silently has no music. Verified on the
  emulator by the drive reporting CDDA sectors from track 2.
- **Screen shake.** A decaying random offset, strongest-wins rather than
  additive so several explosions do not compound into a screen that never
  settles. Sprites marked `"fixed"` ignore it, which is what lets the panels and
  HUD stay still while the playfield jolts.
- **The shooter is now vertical**, Galaga-style, with a narrow playfield framed
  by PC-98/Konami-style side panels. That framing is not decoration: 320x240 is
  far wider than a vertical shmup wants, and arcade boards solved it the same way.
  Adds explosions on a ring buffer, enemies that bounce off the panel edges,
  drifting descent, and a HUD that sits inside the panel windows.

Still open:

1. **Semi-transparent blending.** Alpha-keyed holes work; 50%% blending does not.
2. **CD streaming for data**, which would let levels exceed RAM -- and would have
   to share the drive with music.
3. **Per-object scripts**, 4-bit textures, LTO.
4. **PS2.** Untouched -- see M6.


## Update, 2026-09-06 (saves, a menu, and a collision fix)

- **Memory card saves.** 16 int slots, one 8 KB block, with a real BIOS header
  so the save appears in the console's own memory card screen under the
  project's name rather than as corrupted data. The failure that hid this for a
  while is written up in KNOWN-ISSUES.md: `_bu_init()` called before the card
  driver has exchanged a byte silently zeroes the card's directory, and every
  later save then fails as "card full" on an empty card.
- **A menu scene in the shooter.** High score read on entry, START to play,
  SELECT to clear, written back on game over. This is the shape a template
  should have: two scenes, one script, branching on `scene()`.
- **A collision fix.** A hit moved the player to the respawn point and the rest
  of the same loop then tested the remaining enemies against the new position,
  so one collision could cost several lives and paint explosions at both the
  impact and the respawn. Verified on the emulator: one collision, one life, one
  pair of explosions at the impact.

Still open:

1. **A real font.** Text is the SDK's debug font, which does not belong next to
   the panel art. A bitmap font sheet is the single most visible gap left.
2. **Semi-transparent blending.** Alpha-keyed holes work; 50%% blending does not.
3. **Per-object scripts**, 4-bit textures, LTO.
4. **PS2.** Untouched -- see M6.


## Update, 2026-09-06 (a real font, and keeping projects in step)

- **A bitmap font.** Text was the SDK's debug font, which does not belong next
  to the panel art. Every package now carries a `FNT0` chunk -- an 8x8 sheet,
  ASCII 32..95, uppercase only -- and `draw_text` emits one textured quad per
  character from it. The sheet is 256x16 for a reason: that is the shape of the
  VRAM strip between the framebuffers and the texture slots, so the font costs
  no texture slot at all. The glyphs live in tools/ncc/ncc/fontgen.py as
  editable pixel art rather than as a committed PNG; `ncc font out.png` dumps
  them, and a project can point `"font"` in scene.json at its own sheet.
- **`ncc sync`.** A project keeps its own copy of the runtime, which is what
  makes it readable and modifiable -- and also means an engine fix never reaches
  projects made before it. `ncc sync` copies the engine files back over,
  re-applying the project's own name and save id, and touches nothing else.
  There is a SYNC button in Studio.
- **Two small build traps closed.** `file(GLOB)` without `CONFIGURE_DEPENDS` is
  evaluated once, so a source file added later became an undefined reference at
  link time. And a running emulator holds game.bin open, which failed the build
  after a clean compile with a message about an output image -- `ncc run` now
  closes it first, and the error explains itself if it happens anyway.

Still open:

1. **Semi-transparent blending.** Alpha-keyed holes work; 50%% blending does not.
2. **Per-object scripts**, 4-bit textures, LTO.
3. **PS2.** Untouched -- see M6.


## Update, 2026-09-06 (collision and gravity)

The 2D template had no collision at all: the character walked through the
scenery, because the scenery was scenery. That is now a real feature rather
than a helper each game rewrites.

- **Solid sprites.** `"solid": true` in scene.json is the whole of what makes a
  sprite ground, a platform or a wall. Nothing else declares the level.
- **`physics_step(s)`** does gravity, velocity and collision in one call;
  `move_and_slide(s, dx, dy)` is the same collision without gravity, for
  top-down games. `on_floor` / `on_ceiling` / `on_wall` report what was hit.
- **Velocity is 20.12 fixed point**, the same convention as the 3D side: 4096 is
  one pixel per frame. Positions stay whole pixels and the sprite carries the
  remainder, so a speed under a pixel a frame accumulates instead of rounding to
  standing still.
- **Collision boxes are separate from the art.** A 16-pixel character in a
  32-pixel cell would otherwise stop seven pixels short of every wall, which
  reads as broken collision rather than as padding. `"box": [x, y, w, h]`, and
  in Godot a RectangleShape2D under the sprite exports as one.
- **The floor is probed, not inferred from collisions.** Standing still, gravity
  adds a fraction of a pixel, the sprite does not move, nothing is hit -- and a
  floor flag set only by collisions would flicker off, so jumps would fail every
  other frame. A one-pixel downward probe is what makes `on_floor` trustworthy.
- **The `sprite2d` template is a platformer**: a floor with a gap, two
  staircases, coyote time, and a respawn if you fall in the pit. The level is
  laid out against the jump arc -- apex is `v*v/(2g)`, about 39 pixels with the
  defaults -- because a platform the player cannot reach reads as a broken jump.

What this is not: no sub-stepping, so a sprite moving faster than a wall is
thick passes through it in one frame. No slopes, no rotation. Both are choices
about where the frame budget goes on a 33 MHz machine, and both are written
down in LIMITS.md rather than left to be discovered.

Package version 8 -- the sprite record grew a collision box. `ncc sync`.

Still open:

1. **Semi-transparent blending.** Alpha-keyed holes work; 50%% blending does not.
2. **Per-object scripts**, 4-bit textures, LTO.
3. **PS2.** Untouched -- see M6.


## Update, 2026-09-06 (the Godot side)

Godot is still not forked. All of this is a plain editor plugin.

- **A dock.** Export, export+build, export+build+run, and check budgets, with
  `ncc` output in the dock. The loop no longer leaves the editor, and a texture
  that is too big is something you find out about while looking at the editor
  rather than in a terminal you were not watching.
- **Buttons for the sprite flags.** MARK SOLID and MARK FIXED set the metadata
  the physics and the shake read, on whatever sprites are selected. Metadata
  rather than a custom node type, so any Sprite2D works -- including ones from a
  scene you already had.
- **Collision boxes are dragged, not typed.** An Area2D with a RectangleShape2D
  under a sprite exports as its `"box"`. Verified by round trip: the Godot
  export of the platformer level is byte-for-byte the same scene as the
  hand-written scene.json, `solid` flags and hitbox included.
- **Textures keep their names.** They exported as tex0, tex1; they now carry the
  name of the file they came from, because "tex0" tells you nothing when you
  open scene.json a week later.
- **An editor theme that matches NC Studio.** Project > Tools > apply. It writes
  Godot's own editor settings -- the same knobs the Editor Settings dialog
  writes -- so nothing is patched and nothing breaks on upgrade. Those settings
  are per user rather than per project, which is Godot's design and not a choice
  made here, so the previous values are saved and there is a restore that puts
  them back exactly.

One detail that cost time and is worth recording: Godot renamed several theme
settings across 4.x -- `interface/theme/preset` split into `color_preset` and
`spacing_preset`, and the font settings moved under `fonts/`. A plugin that
hard-codes one spelling silently does nothing on the versions using the other,
so each setting is a list of candidate names and the first one this Godot
actually has is used.

Still open:

1. **Semi-transparent blending.** Alpha-keyed holes work; 50%% blending does not.
2. **Per-object scripts**, 4-bit textures, LTO.
3. **PS2.** Untouched -- see M6.


## Update, 2026-09-06 (prototyping kit, and the manager follows the project)

- **A 2D view.** `scroll_set/by/follow` and `scroll_x/y`. Sprites are
  screen-space, so a level larger than the screen is an offset subtracted at
  draw time rather than a camera: positions stay in world coordinates and
  collision never has to know the view moved. Fixed sprites are exempt, which is
  what keeps a HUD still while the world slides. `scroll_follow` uses a dead
  zone, because a view that tracks exactly is nauseating to play.
- **Sprite mirroring.** `sprite_set_flip` swaps which end of the texture each
  corner samples. Facing both ways costs no extra art and no extra VRAM.
- **Prototyping helpers**: `draw_text_center`, `approach`, `sign`, `lerp`,
  `rand_range`, `dist`, `every`. Nothing clever -- these are where the sign
  errors come from when every game writes them again.

- **Projects declare their target.** `nc.json` records name, template and
  target. NC Studio reads it on selection and reconfigures around it: the target
  buttons, the hardware profile, and whether building is possible at all. A
  BUILD button that always fails is worse than one that is visibly unavailable,
  because the first looks like a bug in your project.
- **`ncc build` refuses a non-PS1 project by name**, naming what does exist for
  that target, rather than failing three layers down inside cmake with a missing
  compiler.
- **A `ps2_hello` template** that declares target ps2 and does not pretend to
  build. It exists so the PS2 path is a real, selectable thing with a hardware
  profile and a toolchain check rather than a promise.

Still open:

1. **The PS2 renderer** -- M6, and it is a second renderer rather than a port.
   No ordering table, a depth buffer, a real FPU, two vector units.
2. **Semi-transparent blending.** Alpha-keyed holes work; 50%% blending does not.
3. **Per-object scripts**, 4-bit textures, LTO.


## Update, 2026-09-06 (the PS2 toolchain actually builds)

M6 is no longer a promise: `ncc build` on a PS2 project produces a real .elf.

- **ps2dev installed** into toolchain/ps2dev by tools/install-ps2dev.sh --
  the EE and IOP compilers (GCC 15.2.0), PS2SDK and gsKit. Prebuilt, because
  building ps2dev from source on Windows is an afternoon.
- **`ncc build` builds PS2 projects** with PS2SDK Makefiles. The PS1 side uses
  CMake because PSn00bSDK does; forcing one build system across both would mean
  reimplementing PS2SDK link rules, which is the part most likely to be subtly
  wrong.
- **`ncc doctor --target ps2`** reports the real toolchain rather than a
  deferred placeholder.
- **The ps2_hello template builds and runs**: it sets up the GS, clears a
  640x448 framebuffer and prints to TTY. Not the NC runtime -- the smallest
  thing that proves the path works.

Two Windows-specific traps, both recorded in install-ps2dev.sh because both
cost real time:

1. The archive contains symlinks under ps2sdk/ports/bin. Windows refuses to
   create them and tar then aborts the whole extraction.
2. The binaries are 32-bit and linked against a MinGW runtime they do not
   ship. Without it the gcc driver starts, spawns cc1, and cc1 dies before
   printing anything -- make reports "Error 1" with no diagnostic, and the same
   command works by hand. tools/ps2dev_runtime.py reads what the binaries
   import, fetches those DLLs from MSYS2 and puts a copy beside every
   executable, so nothing depends on the machine having MinGW.

What is still M6: **the NC runtime itself**. The PS2 has a depth buffer, a real
FPU, 32 MB of RAM and two vector units, so the ordering table, the fixed-point
arithmetic and the GTE path -- most of the PS1 renderer -- have no counterpart.
That is a second renderer, not a port.

On hardware: PS2 output is an .elf, so a FreeMcBoot console runs it straight
from a USB stick via uLaunchELF or OPL. PCSX2 additionally needs a PS2 BIOS
dumped from your own console; unlike the PS1, there is no open replacement.


## Update, 2026-09-06 (running on real hardware)

**The PS2 build ran on a real console.** examples/ps2_pad, launched from
uLaunchELF off a USB stick on a FreeMcBoot PS2: a box that moves with the
D-pad and changes colour with X. Toolchain, build, GS display, controller and
frame loop, all verified on hardware rather than on my word.

That is the first Neon Coffee output to run on a real machine at all -- the PS1
side has only ever been verified in DuckStation, because a PS1 disc image needs
an ODE or a modchip and a FreeMcBoot PS2 will not boot one. OPL does not list
loose ELFs either; uLaunchELF is the launcher for this.

Also in this pass:

- **`ncc add texture|sound|music`**, and the same three buttons in Studio. It
  copies the file in and registers it in scene.json, and refuses up front --
  an oversized PNG is rejected when you add it, with the limit and the reason,
  rather than in a build log later.
- **PS2 is a first-class target in the manager**: Studio builds and runs it,
  the project list tags each row with its machine, `ncc check` reports what can
  honestly be said about a PS2 project, and `ncc run` explains the PCSX2 BIOS
  situation instead of failing at it.

Still M6: the NC runtime on PS2. What runs today is a hand-written main.c.


## Update, 2026-09-06 (the logo, and a visual novel on PS2)

- **The Neon Coffee mark is an asset now**, generated by tools/make_logo.py at
  whatever size is needed. Generated rather than stored as one PNG because it
  has to exist at several sizes for several machines, and rescaling a bitmap
  logo turns the black edging grey and furry.
- **tools/png2ps2.py** turns a PNG into a C array the GS can upload. The PS1
  side loads art from a .ncpkg because it has a runtime that does that; the PS2
  side does not yet, so this does what PS2SDK own samples do and links the
  pixels in.
- **The ps2_vn template**: logo title screen, a pad-driven menu, and a scene of
  text advanced a line at a time. A visual novel is a deliberate first game for
  this machine -- no physics, no scrolling, no per-frame budget to blow. Menu
  navigation has the same shape as the PS1 shooter: title, menu, scenes.

Two PS2 details worth writing down, because both cost time to learn:

1. **0x80 is fully opaque**, not 0xFF. 0xFF is over-bright and used for
   additive work. Every colour and every texel in this template uses 0x80.
2. **The alpha test, not blending**, does the cut-outs. Texels at alpha 0 never
   reach the framebuffer. It is cheaper than blending and, for hard-edged
   pixel art, indistinguishable from it.

Textures must be power-of-two on both axes -- the hardware addresses them by
shift rather than by multiply -- so png2ps2.py refuses anything else instead of
letting the console sample garbage.
