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
