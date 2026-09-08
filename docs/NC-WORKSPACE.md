# Editing inside NC Studio

Restart Studio after updating. The top workspace contains ROOM, EVENTS,
GAME FLOW and VIEWPORT; the bottom dock contains supporting editors and assets.

## GAME FLOW: overall structure

Each example/template now has a game-structure.json reference map. Room names
come from its scene/VN data where present. Stages labeled planned are suggestions,
not existing gameplay. Drag nodes, connect stages and double-click to edit labels.
This file is a design map; EVENTS remains the executable action system.
INSERT KIT appends another project learning map without replacing existing work.

## VIEWPORT: first native editing path

Select PS2 Fixed Camera Room. The view is a top-down authoring canvas, not a PS2
render preview. Drag player, key or door; SAVE LAYOUT then BUILD. The compiler
turns room-layout.json into positions used for rendering, reset and interactions.
CAMERA ANGLES edits the three exported yaw presets in radians.

The door is restricted to a smaller area so its exit remains reachable. Objects
can overlap; collision-aware placement is not implemented. Move to event nodes
still hold explicit coordinates: moving the key does not retarget those nodes.
Update the movement destination when changing key placement.

Unsaved layouts remain in memory while switching projects. Build and app close
save pending viewport drafts, stopping on external-file conflicts. RELOAD discards the current viewport draft. Saving refuses to overwrite
a file changed outside the viewport. There are no new assets, meshes, animation
imports or arbitrary object creation tools in this initial viewport.

PS1 and VN room editing stays in ROOM. Their Godot files and existing editing
paths remain available. Viewport editing currently applies only to the fixed-room
PS2 adapter and does not import its data into other targets.

## ASSETS

The inventory uses dark rows, readable text and contrasting selection colors.
It lists project files, filters by path, opens them externally, and previews
PNG/JPEG images with dimensions. WAV inspection shows duration, sample rate and
channel count. Reference-safe renaming and replacement are still pending.

Viewport controls: mouse wheel zooms, FIT restores framing, POSITION edits exact
coordinates, and UNDO restores up to 40 snapshots in the current project session.

## Structure drill-down and event editing

Double-click an Initialize stage to inspect startup chains, or the first Play
stage to inspect existing gameplay chains. Other stages start empty unless you
add nodes to their editing group. ALL EVENTS restores the complete graph;
GAME FLOW returns to the structure map. EDIT changes the stage label.

Groups organize editing only: the compiler still executes the project's enabled
root events globally. A Menu group is not a menu-active condition. No runtime
scene scope is inferred from the structure diagram.

DUPLICATE copies a selected node without connections; UNDO restores up to 40
snapshots within the current project session. Adding/editing/connecting nodes
returns executable graphs to Draft so changes must be enabled again.
PROJECT WALKTHROUGH opens the selected example's guide inside Studio. New
projects inherit their template guide and authoring/reference files.
