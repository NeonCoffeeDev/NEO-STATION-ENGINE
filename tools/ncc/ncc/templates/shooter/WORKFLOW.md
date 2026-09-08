# Shooter: room, HUD and event tutorial

1. Open ASSETS; select the sprite sheet or panels to inspect their dimensions.
   Select WAV effects to inspect audio metadata. These are PS1 assets.
2. Open ROOM and select the menu/game room. Move an existing visual element and
   save. Script-driven objects can override starting coordinates during play.
3. Study script.ncs alongside GAME FLOW: menu -> gameplay -> results/restart.
4. EVENTS offers PS1 room, sound and pooled-sprite recipes. Start with a button
   and Play effect, choosing an existing sound index. Avoid binding a button
   already used by the authored game. ENABLE, build, and test.
5. Showing a pooled sprite only changes visibility; it does not reset bullet or
   enemy state. Do not reorder indexed objects without checking script references.

The dedicated PS2 viewport is not a PS1 renderer or importer.

## Workspace map

- GAME FLOW is the overall design/reference map, not runtime routing.
- EVENTS contains the executable subset supported by this project's adapter.
- ROOM edits existing PS1/VN layouts. VIEWPORT edits the PS2 fixed-room adapter.
- ASSETS filters and previews project files. It does not safely rename references yet.
- The lower dock keeps logs, authoring and inspection beside your main editor.

Build after changes and check the console. Keep graph files in their own target;
PS2 actions and assets are not automatically converted for PS1.
