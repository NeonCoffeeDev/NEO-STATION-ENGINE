# Visual room editing

Restart Studio to load the new ROOM tab. Select ps2_vn or a PS1 sprite project.
The room canvas displays the existing artwork; click and drag objects to move.
Use the object list to select elements hidden behind another. Toggle 8px snapping,
edit X/Y/Width/Height, APPLY, UNDO, SAVE ROOM. F7 saves room edits before building.
NEW ROOM creates a PS1 scene or PS2 VN named location. ADD SPRITE / CHARACTER
adds a PS1 sprite using an existing texture or a VN character with a PNG picker.
REPLACE IMAGE copies PNGs into the project; it does not overwrite the source.
The actor dropdown chooses which VN portrait you are editing/previewing.
VN layout positions are shared across scenes and characters in this first pass.

EDIT CONVERSATION edits text and scene/speaker/next/item IDs. The Choices tab
edits two alternatives and their required/reward items. ADD DIALOGUE ENTRY adds
a new page. Blank next ends the conversation. Build/check reports invalid IDs,
text overflow, texture limits and unsupported rectangle sizes.

Godot: reopen vn_authoring.tscn. It is now a Node2D scene with visible Background,
Portrait and Dialogue children. Click the children and move/resize them in 2D.
The outline marks an approximate safe area. NC export reads these rectangles;
CHECK / BUILD now correctly find PS2 nc.json projects. Rotations/flips are rejected.

When switching from Studio edits to Godot, choose Tools > Neon Coffee: reload VN
from Studio, then save the scene. When switching back, use ROOM > RELOAD. Studio
refuses to overwrite externally changed room data. Save before switching projects.

Scope: the same Studio canvas edits PS1 sprite scenes and PS2 VN layouts; it does
not make the PS2 conversation runtime exportable to PS1. Existing PS1 NCScript
still controls gameplay, and script-written positions can override editor values.
This is a room editor foundation, not a complete GameMaker replacement or a graph
editor. Existing Godot tools and native runtimes are retained.

Font repair: the 256x16 font was allocated without reserving the full 32-row GS
page height. New texture allocations could overlap the atlas, consistent with
missing letters in its right half. Font reservation now rounds to 32 rows; kit
textures reserve whole pages with at least a 64-pixel pitch, and budgets include
this padding. Upstream allocator reference:
https://github.com/ps2dev/ps2sdk/blob/master/ee/graph/src/graph_vram.c
The footer is also moved inward. This fix compiles but needs hardware verification.

Verified: Studio PS1/PS2 canvas load/save/undo; Godot 2D layout export/reload and
PS2 project detection; fresh VN project build; existing compiler validation tests.
