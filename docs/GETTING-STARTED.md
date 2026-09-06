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
./ncc doctor           # toolchain status
```

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
