# Fixed-camera room: native NC editing tutorial

1. Select this project and open VIEWPORT. Select the door, choose POSITION,
   and set X=1.5, Z=0.5. Use Undo to restore it, then drag it to a new spot.
2. Save Layout. Build also saves pending layouts. Camera Angles changes the
   exported presets; mouse-wheel zoom and Fit only change the editor view.
3. Build and test: the rendered door and its interaction location both follow
   the edited position. X opens it after the key is collected.
4. Open EVENTS. Follow SQUARE -> Move to, then On arrival -> Interact.
   If you move the key in VIEWPORT, update Move to's destination too; it stores
   coordinates, not an object reference. CIRCLE cancels movement.
5. Press TRIANGLE three times to demonstrate a variable and condition switching
   camera 2. START resets room state; it does not reset event counters/timers.
6. INSERT KIT adds editable nodes and returns the graph to Draft. Edit parameters
   and remove duplicate handlers before enabling. Try Initialize a score, then
   add to the same variable from a button event.
7. In ASSETS, filter room-layout to inspect authoring data, or WORKFLOW to find
   this guide. This example uses procedural wireframe objects, not imported art.

Expected controls: D-pad move; X interact; Square walk to key; Circle cancel;
Triangle counter; L1/R1 camera; START reset. No textures, occlusion, skeletal
animation or collision-aware movement is claimed by this prototype.

## Workspace map

- GAME FLOW is the overall design/reference map, not runtime routing.
- EVENTS contains the executable subset supported by this project's adapter.
- ROOM edits existing PS1/VN layouts. VIEWPORT edits the PS2 fixed-room adapter.
- ASSETS filters and previews project files. It does not safely rename references yet.
- The lower dock keeps logs, authoring and inspection beside your main editor.

Build after changes and check the console. Keep graph files in their own target;
PS2 actions and assets are not automatically converted for PS1.

## Executable flow boxes

Select Initialize in GAME FLOW: On start resets the room, then Go to Flow Box 4 enters Play on the next update. Select Play to edit its complete input, movement and camera graph beneath the map. On start selects camera 0 on entry. Other planned boxes remain empty until you author their events. ENABLE validates all boxes together.
