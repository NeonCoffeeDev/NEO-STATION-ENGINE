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

Unsaved layouts remain in memory while switching projects; save before closing
Studio. RELOAD discards the current viewport draft. Saving refuses to overwrite
a file changed outside the viewport. There are no new assets, meshes, animation
imports or arbitrary object creation tools in this initial viewport.

PS1 and VN room editing stays in ROOM. Their Godot files and existing editing
paths remain available. Viewport editing currently applies only to the fixed-room
PS2 adapter and does not import its data into other targets.

## ASSETS

The inventory uses dark rows, readable text and contrasting selection colors.
It lists project files and can open them externally. Reference-safe renaming,
replacement and thumbnail previews are still pending.
