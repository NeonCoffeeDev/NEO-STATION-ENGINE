# ps2_pad: reference workflow

1. Select this project and check its target in the workspace header.
2. Open GAME FLOW to inspect/edit its design map. Planned nodes do not create
   executable screens.
3. Inspect existing files in ASSETS. Use ROOM if this project has scene data.
4. Build the original example before adding logic. EVENTS only enables nodes
   implemented by its console and adapter; unsupported projects remain drafts.
5. For native PS2 layout editing and executable camera/movement kits, create a
   PS2 Fixed Camera Room project rather than copying PS1 logic into this one.

## Workspace map

- GAME FLOW is the overall design/reference map, not runtime routing.
- EVENTS contains the executable subset supported by this project's adapter.
- ROOM edits existing PS1/VN layouts. VIEWPORT edits the PS2 fixed-room adapter.
- ASSETS filters and previews project files. It does not safely rename references yet.
- The lower dock keeps logs, authoring and inspection beside your main editor.

Build after changes and check the console. Keep graph files in their own target;
PS2 actions and assets are not automatically converted for PS1.
