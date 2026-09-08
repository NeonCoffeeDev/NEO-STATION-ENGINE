# VN: room and asset authoring tutorial

1. Open ASSETS and filter .png. Select a portrait/background to inspect its
   thumbnail, dimensions and file path. Filter .wav to inspect available sound
   durations/rates/channels. OPEN SELECTED uses the system's file viewer.
2. Open ROOM. Select a named room, drag a portrait slot, and save. DESIGN owns
   conversations, character references and choices. Godot editing remains available.
3. Build and compare the resulting room on the console. Hardware audio has been
   confirmed with FreeSD; timing/flicker still require separate validation.
4. Use GAME FLOW to map title, conversation rooms, choices and ending plans.
   This map does not add menu screens or change game execution automatically.
5. This VN has no fixed_room_v1 event adapter: do not enable fixed-room movement
   or inventory kits here. The project uses its VN runtime and authored dialogue.

## Workspace map

- GAME FLOW is the overall design/reference map, not runtime routing.
- EVENTS contains the executable subset supported by this project's adapter.
- ROOM edits existing PS1/VN layouts. VIEWPORT edits the PS2 fixed-room adapter.
- ASSETS filters and previews project files. It does not safely rename references yet.
- The lower dock keeps logs, authoring and inspection beside your main editor.

Build after changes and check the console. Keep graph files in their own target;
PS2 actions and assets are not automatically converted for PS1.
