# Neon Coffee Engine

A PlayStation 1 / PlayStation 2 homebrew game engine that uses **Godot as its editor**
and compiles to **native console runtimes** written in C.

NC is an **integration project**, not a from-scratch engine. Nearly every piece
already exists as open source - PSn00bSDK, mkpsxiso, ps2dev, gsKit, Godot, Blender -
and NC's job is to pin them to known versions and make them behave as one environment.
See `docs/TOOLS.md` for the full inventory and the short list of what NC actually
writes itself.

It is also not a converter. You do not take a finished Godot game and turn it into a
PS1 game - the PS1 has no hardware for most of what modern Godot does. You author
against a restricted, hardware-aware node set from the start.

```
  NC Godot Project  ->  .ncpkg  ->  NC Runtime (C)  ->  PS-EXE / ELF  ->  disc image
     (authoring)       (data)        (per target)
```

## Layout

| Path                        | What it is                                              |
|-----------------------------|---------------------------------------------------------|
| `runtime/ps1/`              | PS1 runtime, C, built on PSn00bSDK                       |
| `runtime/ps2/`              | PS2 runtime, C, built on PS2SDK + gsKit                  |
| `runtime/common/`           | Target-independent headers (`.ncpkg` structs, math)      |
| `tools/ncc/`                | `ncc` — the Python asset compiler + build orchestrator   |
| `godot/addons/neoncoffee/`  | Godot editor plugin (NC nodes, budgets, export)          |
| `examples/hello_cube/`      | Smallest end-to-end project                              |
| `docs/`                     | Architecture, `.ncpkg` format spec, roadmap              |

## Start here

```bash
python tools/ncc/ncc doctor
```

`doctor` reports which parts of the toolchain are installed and what is missing.
Nothing else will work until it is clean for at least one target.

## Scope honesty

Supported by design: low-poly meshes, CLUT textures, vertex color / Gouraud, rigid and
skeletal animation, ADPCM audio, simple collision, fixed-function-style materials.

Not supported, and not planned: arbitrary GDScript at runtime, modern shaders, GPU
particles, dynamic shadow mapping, physically-based rendering, runtime scene
instancing without a budget, and anything that assumes floating point on PS1.
