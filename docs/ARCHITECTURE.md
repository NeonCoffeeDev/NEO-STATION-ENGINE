# Architecture

## The three pieces

**1. Authoring (Godot, unmodified).** A stock Godot 4.x install plus the
`addons/neoncoffee` editor plugin. The plugin supplies NC nodes, a target selector,
live budget meters, per-asset compatibility warnings, and a Build button. It does not
require a custom Godot binary.

**2. Data (`ncc`, Python).** Reads the `.tscn`/asset tree, validates it against the
selected hardware profile, converts textures/meshes/animation/audio into native
formats, packs a `.ncpkg`, invokes the target C toolchain, and produces a disc image.

**3. Runtime (C, per target).** `runtime/ps1` and `runtime/ps2` are separate programs
that consume a `.ncpkg`. They share the on-disk format and a small math header, and
almost nothing else — the renderers have no meaningful common code.

## Why Godot is not forked

A fork costs multi-hour builds, permanent upstream rebasing, and three platforms of
editor binaries to ship. It buys nothing the plugin API doesn't already give us:

| Desired feature              | Plugin mechanism                              |
|------------------------------|-----------------------------------------------|
| `NCCharacter`, `NCStaticMesh`| `class_name` scripts, or GDExtension for speed |
| Target selector              | `ProjectSettings` + a dock                     |
| VRAM / poly / RAM budgets    | Dock panel driven by a `ncc analyze --json`    |
| Per-texture warnings         | `_get_configuration_warnings()` on the node    |
| Build button                 | `EditorPlugin` tool menu -> `ncc build`        |
| PS1 look in the viewport     | Shader + subviewport, not an engine change     |

Reconsider the fork only against a named blocker. "It would feel more like our engine"
is not one; the plugin can rename the window and skin the theme.

## Why the runtime comes first

The tooling is low-risk: Python that converts a PNG and shells out to a compiler is
well-understood work. The runtime is where the unknowns are — GTE fixed-point
pipelines, DMA/ordering tables, VRAM allocation, CD streaming latency, VU1 microcode.
Answer the hard question first: get a textured, animated object onto real hardware at
an acceptable framerate. Every downstream decision (what the format holds, what the
budgets are, what the nodes expose) is informed by what that runtime actually needs.

Building the compiler first means guessing at those requirements and rewriting the
format later.

## PS1 vs PS2 are not one backend

Shared: the `.ncpkg` container, asset semantics, the node-level API a game author sees.

Not shared: PS1 is fixed-point 20.12 with a GTE coprocessor, 2 MB RAM, 1 MB VRAM,
affine texture mapping, no depth buffer (ordering tables instead), and 4/8/16-bit CLUT
textures. PS2 has an FPU, 32 MB RAM, 4 MB VRAM, perspective-correct texturing, a real
depth buffer, and programmable vector units. Treating these as one renderer with flags
produces a renderer that is bad at both. They are two implementations behind one API.
