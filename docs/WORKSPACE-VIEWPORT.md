# Main 2D/3D workspace

This is the world/scene workspace. It places instances in the loaded project. It does not edit the internal contents of a reusable GameObject; that is the next editor subsystem.

## PS2 3D workflow

The PS2 3D template is the primary workspace test. Its `room-layout.json` stores object positions, rotations, scales, the game camera, collision previews, and attachment previews. The compiler emits native arrays in `src/nc_objects.h`; the PS2 runtime uses the same position, rotation, scale, camera position, camera target, and field of view.

- `PERSPECTIVE` is the free editor camera. Right-drag orbits, middle-drag pans, and the wheel dollies. These movements never alter the game camera.
- `GAME CAMERA` shows a desktop approximation of the serialized PS2 camera framing.
- `XY`, `XZ`, and `YZ` are manipulation views. Left-drag moves the selected object on those two axes. Snap uses 0.25 PS2 world units.
- `POSITION` edits all position coordinates numerically.
- `SIZE / ROTATION` edits PS2 3D rotation in degrees and scale per axis. Scale is restricted to 0.05..20.
- `CAMERA ANGLES` edits game-camera position, target, and FOV. FOV is restricted to 20..100 degrees.
- `DUPLICATE OBJECT` creates another bounded PS2 3D primitive instance. The current lab supports at most 16.
- Purple wire boxes are editable world trigger volumes. Red boxes are collision components and green markers are attachment points. Collision and attachment data is displayed in world space but remains read-only here because it belongs to a GameObject definition.

The PS2 3D example includes a cube, collision volume, top attachment, game camera, and a trigger. `SELECT` moves the cube into the trigger through its visual event example. Builds regenerate native transform data.

## Scaffolded adapters

PS1 scene projects expose sprites, meshes, cameras, draw order, orthographic transforms, mesh wireframes, trigger volumes, and image previews. PS2 fixed-room exposes player/key/door placement, camera directions, and movable trigger volumes. PS2 pad exposes its 2D box. The VN exposes backgrounds, portrait slots, dialogue bounds, and images without replacing the focused Rooms/GameObject work.

These adapters preserve each console's units and limits. PS1 trigger positions must be integer coordinates. Target mismatches, missing trigger subjects, invalid bounds, external file edits, and project switches are checked before saving or building. Drafts are keyed by absolute project path, so one project's objects cannot appear in another project's workspace.

## Renderer decision

Raylib 6.0 remains the first candidate for the later standalone Game/Camera Preview renderer. It provides models, cameras, render textures, and a small API, but it owns its desktop window/context and does not provide a clean supported path for rendering into an existing Tk widget. Reparenting its native Win32 window would make the editor Windows-specific and fragile.

For this milestone the embedded editor uses a deterministic Canvas wireframe renderer, which keeps scene editing inside NC Studio with no new dependency. The renderer boundary is explicit: the workspace owns authoring and overlays; a later raylib preview process can consume the same validated project data without changing PS1/PS2 runtime code.

## Current limits

The PS2 3D lab still renders simple wireframe box geometry on console. The editor can position multiple instances and visualize transforms, but importing arbitrary PS2 models/materials, textured preview parity, gizmo handles, local GameObject hierarchy editing, and executable collision response belong to later milestones. Triggers have native event predicates; collision components are visualization/serialization groundwork until the component runtime is added.
