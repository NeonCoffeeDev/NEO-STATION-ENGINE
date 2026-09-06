# Getting started

How to build and run a PlayStation 1 game on this machine. Everything below is
already installed and verified -- this documents it so it is reproducible.

## 0. What you have

| Piece            | Where                                        |
|------------------|----------------------------------------------|
| MIPS compiler    | `toolchain/psn00bsdk/bin/mipsel-none-elf-gcc` |
| PS1 libraries    | `toolchain/psn00bsdk/lib/libpsn00b`          |
| Disc builder     | `toolchain/psn00bsdk/bin/mkpsxiso`           |
| CMake / Ninja    | installed system-wide                        |
| Emulator         | DuckStation (winget)                         |
| BIOS             | OpenBIOS, in DuckStation's `bios/` folder    |
| Orchestrator     | `./ncc`                                      |

Check it any time:

```bash
./ncc doctor
```

On Windows use `ncc.cmd` instead of `./ncc` (both take the same arguments).

## 1. Make a project

```bash
./ncc new mygame
```

This writes a complete, buildable project:

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

## 2. Build and run it

```bash
./ncc run mygame
```

That compiles, links, converts the ELF to a PS-EXE, builds a `.bin`/`.cue` disc
image, and launches DuckStation on it. You should get a lit, spinning cube.

Controls: D-pad rotates, L1/R1 move it away/closer, X resets.

Other commands:

```bash
./ncc build mygame     # build only, no emulator
./ncc clean mygame     # delete the build directory
./ncc targets          # hardware profiles and budgets
```

## 3. The development loop

1. Edit `src/main.c`.
2. `./ncc run mygame`
3. Look at it.

Rebuilds are incremental, so step 2 takes a couple of seconds after the first run.

### Seeing printf output

`printf()` in your game goes to the PS1's TTY. DuckStation is configured to log it,
so it lands in:

```
%LOCALAPPDATA%\DuckStation\duckstation.log
```

as `I/TTY:` lines. This is the main debugging tool you have -- use it liberally.

## 4. Where the build output goes

Because this project lives in `C:\Users\bates\Desktop\NC HOMEBREW` and that path
contains a space, `ncc build` redirects the build directory to:

```
%LOCALAPPDATA%\NeonCoffee\build\<project>-<hash>\
```

The finished `game.bin` / `game.cue` are there. This is automatic; see
`docs/KNOWN-ISSUES.md` for why it is necessary. If you ever move the project to a
path without a space, `ncc` will build in-tree at `<project>/build/` instead.

## 5. Rebuilding OpenBIOS

Already done, but if you need to redo it:

```bash
./tools/build-openbios.sh
```

It clones PCSX-Redux sparsely (~10 MB), builds `openbios.bin` with the same MIPS
compiler your game uses, and installs it into DuckStation.

OpenBIOS is open source and freely redistributable, which is why NC uses it. A retail
BIOS dump would also work and is more faithful to real hardware, but it is
copyrighted -- if you want that, dump it from a console you own.

Two known OpenBIOS quirks:

- DuckStation's `-fastboot` does not work with it (`Cannot fast boot, BIOS is
  incompatible`). Harmless; `ncc run` does not use it.
- It is built for homebrew. Commercial games are not its target.

## 6. What to edit

`src/main.c` is yours. The interesting parts of the engine:

- `nc_mesh_draw()` in `nc_gfx.c` -- the whole render path: GTE transform, backface
  cull, depth sort, lighting. Read this one first; it is the PS1 in miniature.
- `nc_gfx_flip()` -- double buffering and the ordering table walk.
- `nc_input_poll()` -- BIOS controller reads.

Things worth trying, roughly in difficulty order:

1. Change the cube's colors, or the clear color (`nc_gfx_set_clear`).
2. Draw a second mesh at a different position.
3. Add a `printf` and watch it in the log.
4. Replace the cube's vertex data with your own model.
5. Add textures. This means learning the TIM format and VRAM allocation --
   PSn00bSDK's `graphics/gte` example, under
   `toolchain/psn00bsdk/share/psn00bsdk/examples/`, does exactly this.

Those bundled examples are the best PS1 reference you have locally. `nc_gfx.c` is
derived from `graphics/gte`.
