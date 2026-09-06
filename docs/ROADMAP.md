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

## M4 - Make it a game engine  (you are here)
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
