# Getting started

How to build and run a PlayStation 1 game on this machine. Everything below is
installed and verified -- this documents it so it is reproducible.

## 0. What you have

| Piece            | Where                                         |
|------------------|-----------------------------------------------|
| MIPS compiler    | `toolchain/psn00bsdk/bin/mipsel-none-elf-gcc` |
| PS1 libraries    | `toolchain/psn00bsdk/lib/libpsn00b`           |
| Disc builder     | `toolchain/psn00bsdk/bin/mkpsxiso`            |
| CMake / Ninja    | installed system-wide                         |
| Emulator         | DuckStation (winget)                          |
| BIOS             | OpenBIOS, in DuckStation's `bios/` folder     |
| CLI              | `./ncc` (or `ncc.cmd`)                        |
| GUI              | `./ncc studio` (or `studio.cmd`)              |

Check it any time:

```bash
./ncc doctor
```

## 1. The GUI

```bash
./ncc studio
```

NC Studio wraps everything below. Left column: project list, target, actions,
open-buttons, and the hardware budgets for the selected target. Right: two panes.

- **CONSOLE** -- `ncc` output, colorized, streamed live while a build runs.
- **PS1 TTY** -- your game's own `printf()` output, tailed from DuckStation's log.
  With no debugger attached to the console, this is your main instrument.

Shortcuts: `F5` build+run, `F7` build, `Shift+F7` clean, `F9` doctor,
`Ctrl+N` new project, `Ctrl+L` clear the active pane, `Esc` stop a running build.
Double-clicking a project builds and runs it.

Window size, selected project, target and the autoscroll toggle persist in
`%LOCALAPPDATA%\NeonCoffee\studio.json`.

## 2. The CLI

```bash
./ncc new mygame
```

```bash
./ncc run mygame
```

`run` compiles, links, converts the ELF to a PS-EXE, builds a `.bin`/`.cue` disc
image, and launches DuckStation on it. Rebuilds are incremental, so after the
first run the loop is a couple of seconds.

```bash
./ncc build mygame     # build only, no emulator
./ncc clean mygame     # delete the build directory
./ncc templates        # list project templates
./ncc targets          # hardware profiles and budgets
./ncc check mygame     # what fits, what does not, and why
./ncc sync mygame      # bring the project's engine files up to date
./ncc font my.png      # dump the built-in font sheet to edit
./ncc doctor           # toolchain status
```

`ncc sync` is worth knowing about. A project keeps its own copy of the runtime
under `src/`, which is what makes it readable and yours to change -- but it also
means a fix made to the engine after your project was created does not reach it.
The symptom is usually a package that refuses to load with a version mismatch.
`ncc sync` copies the engine files back over, and touches nothing else.

On Windows `ncc.cmd` takes the same arguments as `./ncc`.

## 3. Templates

```bash
./ncc new mygame -t scene
```

| Template | What it is                                                        |
|----------|-------------------------------------------------------------------|
| `blank`  | Empty game loop. Graphics and input set up, nothing drawn.        |
| `cube`   | One lit, Gouraud-shaded cube on the D-pad. **Default.**            |
| `scene`  | Four objects, swinging camera, fixed-point circular motion.        |
| `game`   | **Menu + level, Godot scenes, and a script. No C.** Start here.     |
| `sprite2d` | **A 2D game.** Sprite sheet, animation, screen-space movement.     |
| `shooter` | **A whole game.** Vertical shmup with arcade side panels, CD music and screen shake. |

Every template gets the same engine files; only `src/main.c` differs. They live in
`tools/ncc/ncc/templates/`, with the shared engine in `_common/`. To add one, drop
a folder in beside them containing `main.c` and a `template.json` -- both the CLI
and the Studio new-project dialog pick it up automatically.

A generated project looks like:

```
mygame/
  CMakeLists.txt      build config
  system.cnf          PS1 boot config -- points at GAME.EXE
  iso.xml             disc layout, read by mkpsxiso
  include/nc.h        engine API
  src/main.c          YOUR GAME -- edit this
  src/nc_gfx.c        engine: double buffer, GTE transforms, ordering table
  src/nc_input.c      engine: controller
```

## 3a. The Godot + script flow (no C at all)

This is the one to use if you would rather not write C.

```bash
./ncc new mygame -t game
```

You get three files that matter, and none of them is C:

| | |
|---|---|
| `godot/` | A Godot 4 project. **What exists** -- meshes, objects, cameras, scenes. |
| `script.ncs` | **What happens** -- your game logic. See `docs/SCRIPTING.md`. |
| `scene.json` | Written by the Godot exporter, read by the build. |

The script is not interpreted on the console: `ncc build` transpiles it to C and
compiles it natively. GDScript itself cannot run on a PS1, but a GDScript-shaped
language can be translated to something that does.

The Godot project holds **both** scenes at once. Any direct child of the root
named `Scene...` (or carrying metadata `nc_scene`) becomes its own game scene,
with its own camera. Each is exported relative to itself, so moving a group
around to keep them from overlapping in the viewport does not affect the game. In NC Studio, select the project and
press **EDIT SCENE IN GODOT**, or open `mygame/godot/project.godot` by hand.

1. Arrange `MeshInstance3D` nodes with **BoxMesh** in the 3D viewport. Move,
   rotate and scale them normally.
2. Frame the scene through the `Camera3D`. Positions are exported *relative to
   the camera*, so roughly what you see is what the console shows.
3. Optional: give a node metadata named `nc_spin` (a `Vector3`) in the inspector
   to make it turn on its own. The units are PS1 angle-per-frame, where 4096 is a
   full turn -- so `12` is a slow spin.
4. Press **Export to NC** in the toolbar. It writes `../scene.json`.
5. Edit `script.ncs` for the logic (Studio's **script** button opens it).
6. Back in NC Studio, press **F5**.

`ncc build` compiles `scene.json` into `scene.ncpkg`, embeds it in the executable,
and the runtime draws whatever it finds. `src/main.c` never changes.

### What survives the trip, and what does not

**Boxes are the good path.** A `BoxMesh` becomes six quads with correct winding
and outward normals, which is exactly what the hardware wants.

Anything else -- a sphere, an imported model -- is exported as triangles padded
into degenerate quads. It draws, but it wastes GPU time and gets flat per-face
lighting. Real triangle support is a known gap; see `docs/ROADMAP.md`.

Also not yet supported, and worth knowing before you build something around them:

- **No textures.** Everything is flat-lit Gouraud.
- **No runtime camera.** The viewpoint is baked at export time and cannot move.
- **Compound rotations are approximate.** Godot and the PS1's `RotMatrix` use
  different Euler orders. A rotation about one axis is exact; combining two drifts.
- **Watch the budget.** The exporter warns past ~256 vertices per mesh or ~900
  quads total. Those are where it stops being plausible on real hardware, not
  hard limits.

## 3b. Textures and text

### Textures

Drop a PNG in your project and name it in `scene.json`:

```json
{
  "textures": [
    { "name": "checker", "file": "textures/checker.png" }
  ],
  "meshes": [
    { "name": "block", "texture": "checker", "verts": [...], "quads": [...] }
  ]
}
```

`ncc build` quantises it to a 256-colour palette, converts to the PS1's BGR555,
and places it in VRAM. Faces get the whole texture unless the mesh supplies its
own `uvs`.

Or skip the JSON: give a Godot material an **albedo texture** and the exporter
writes the PNG to `textures/` and wires it up for you.

**Transparency** is one reserved colour, not an alpha channel -- the GPU skips
any texel whose value is exactly `0x0000`. Give a PNG an alpha channel and the
packer reserves palette entry 0 for it automatically, quantising the rest to 255
colours. (Which is also why opaque pure black gets nudged: black *is* `0x0000`,
and would otherwise punch holes in your texture.)

The limits are the hardware's, not arbitrary:

| | |
|---|---|
| **8 textures** | Each needs its own VRAM slot. |
| **256 x 240 max** | Bigger will not fit a texture page. |
| **Even width** | Two 8-bit texels share one 16-bit VRAM cell. |
| **256 colours** | 8-bit CLUT. Quantisation is automatic. |

VRAM is 1024x512 and the framebuffers already occupy a third of it. The full map
is documented at the top of `tools/ncc/ncc/textures.py`.

### Text

`print()` goes to the TTY log. To put words on the TV, use the built-in debug
font:

```gdscript
draw_text(96, 40, "MY GAME")
draw_num(24, 20, score)
```

Screen coordinates, 0,0 top-left, 320x240. It is drawn over everything else.

### Sprites (2D)

2D is the cheap path on this hardware: a sprite is a textured quad drawn straight
in screen space, skipping the GTE entirely. Add them per scene:

```json
"sprites": [
  { "texture": "sheet", "x": 144, "y": 100, "w": 32, "h": 32, "u": 0, "v": 0 }
]
```

`u`/`v` pick which part of the texture to show, so one sheet holds every frame
and animation is just moving that window. A package with no meshes at all is
valid -- see the `sprite2d` template.

```bash
./ncc new mygame -t sprite2d
```

That template ships a **Godot 2D project** too. Its viewport is 320x240 to match
the console exactly, and Godot's 2D origin is the top-left with +Y down -- the
same as the PS1 screen -- so positions map across with no conversion. Lay out
`Sprite2D` nodes, use **region** to pick a frame from the sheet, and press
Export to NC.

### Debug and release

```bash
./ncc run mygame --release
```

Debug (the default) is `-Og` and keeps every function separate, which is what you
want while iterating. Release is `-O2` and inlines your script's functions away
entirely. NC Studio has a DEBUG/RELEASE toggle; the two use separate build
directories so switching costs nothing.

## 3c. Knowing what fits

```bash
./ncc check mygame
```

or **F8** in NC Studio. It runs the same converters the build does and reports
every budget -- textures, VRAM, sound, SPU RAM, meshes, sprites, package size --
plus anything that will stop the build, with the reason and the fix.

A failed build runs it automatically, so a too-large texture tells you so instead
of surfacing as a linker error.

`docs/LIMITS.md` is the full set of rules and why each one exists.

## 3d. Sound

```json
"sounds": [ { "name": "shoot", "file": "sounds/shoot.wav" } ]
```

```gdscript
play_sound(0)
```

Mono PCM WAV in, SPU-ADPCM out (about 3.5:1). Samples live in the SPU's own
512 KB, so playing one costs the CPU almost nothing. 22050 Hz is the sweet spot;
keep effects short.

**Music** is different -- a song will not fit in 512 KB, so it goes on the disc as
a CD audio track and the drive streams it:

```json
"music": [ "music/theme.wav" ]
```

```gdscript
play_music(2)      # track 1 is the game data, so the first song is track 2
```

44100 Hz 16-bit stereo WAV. `ncc build` adds it to the disc layout for you.

## 4. The development loop

1. Edit `src/main.c` (the Studio's `main.c` button opens it).
2. `F5`, or `./ncc run mygame`.
3. Look at it. Check the PS1 TTY pane for your `printf` output.

## 5. Where the build output goes

`<project>/build/`, with the disc image as `game.bin` / `game.cue`.

If the project ever sits in a path containing a space, `ncc` transparently
redirects the build to `%LOCALAPPDATA%\NeonCoffee\build\<project>-<hash>\` instead,
because PSn00bSDK's post-link step cannot survive spaces. See
`docs/KNOWN-ISSUES.md`. This repo was renamed from `NC HOMEBREW` to `NC-HOMEBREW`
precisely to avoid that, so builds are in-tree.

## 6. Rebuilding OpenBIOS

Already done, but if you need to redo it:

```bash
./tools/build-openbios.sh
```

It clones PCSX-Redux sparsely (~10 MB), builds `openbios.bin` with the same MIPS
compiler your game uses, and installs it into DuckStation.

OpenBIOS is open source and freely redistributable, which is why NC uses it. A
retail BIOS dump would also work and is more faithful to real hardware, but it is
copyrighted -- if you want that, dump it from a console you own.

Two known quirks:

- DuckStation's `-fastboot` does not work with it (`Cannot fast boot, BIOS is
  incompatible`). Harmless; `ncc run` does not use it.
- It targets homebrew. Commercial games are not its concern.

## 7. What to read first

- `nc_mesh_draw()` in `src/nc_gfx.c` -- the whole render path in about 60 lines:
  GTE transform, backface cull, depth sort, lighting. The PS1 in miniature.
- `nc_gfx_flip()` -- double buffering and the ordering table walk.
- `nc_input_poll()` -- BIOS controller reads.

Things worth trying, roughly in difficulty order:

1. Change the cube's colors, or the clear color (`nc_gfx_set_clear`).
2. Draw a second mesh at a different position -- or start from the `scene` template.
3. Add a `printf` and watch it land in the PS1 TTY pane.
4. Replace the cube's vertex data with your own model.
5. Add textures. This means the TIM format and VRAM allocation -- PSn00bSDK's
   `graphics/gte` example under `toolchain/psn00bsdk/share/psn00bsdk/examples/`
   does exactly that.

Those bundled examples are the best PS1 reference you have locally; `nc_gfx.c` is
derived from `graphics/gte`.
