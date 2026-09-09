# Box-owned game flow

Select a GAME FLOW box to see its entire event canvas beneath the map. The selected box owns every node added or kit inserted there. You stay in the map workspace; selection does not jump to one global event. Empty boxes display an empty canvas.

1. Select a box and add On start, input or timer events supported by the project target.
2. Connect actions. On start means enter this box; On exit means leave it.
3. Use Go to Flow Box with the destination box ID shown above the event canvas. It ends its chain. Map arrows remain planning annotations and do not implicitly execute transitions.
4. MAKE SELECTED BOX THE ENTRY chooses the first box. ENABLE validates the entire project's event graph. Editing logic makes the graph a draft until enabled again.
5. Build and test. The fixed-camera example demonstrates Initialize -> Play.

Only the active box's visual events execute. First transition request wins; later event roots are skipped. Exit handlers run at the end of that update. The destination enters on the next update, with no input/arrival/zone event replay. Exit handlers cannot transition. PS2 frame timers, Once and Cooldown reset on entry; named variables persist between boxes and reset on application startup. Reset game remains the adapter's room reset, not a graph reboot. PS1 first entry executes on the first update; scene ready callbacks do not restart the flow.

These rules scope visual events, not existing handwritten runtime code. Native player movement/rendering and authored NCScript still execute as before. A box named Menu or Pause does not automatically create a menu or suspend native gameplay. Loading, video, inventory and new objects require their corresponding runtime capability.

## Compatibility and collaboration

`event-flow.json` version 2 keeps nodes/edges plus `stages`, `entry` and mandatory `section_id` ownership on each node. IDs are stable positive integers. Cross-box event wires, missing destinations, cycles and transitions from exit handlers are rejected. Limits: 64 boxes / 128 event nodes. Console target must match the project and map.

Version 1 graphs remain supported by the compilers. Opening them inside a box prepares a draft migration: existing events all belong to the first Play box (or selected box if no Play exists). Earlier editing-only groups had no runtime meaning and are not used to guess execution states. Saving writes version 2; review and ENABLE explicitly. The standalone EVENTS overview becomes read-only for version 2 projects. Other projects and the user's VN files are not migrated by this change.

PS1 compiles through NCScript into C. PS2 currently requires `fixed_room_v1`; unsupported PS2 adapters refuse ENABLE and retain drafts. No PS2 camera or movement actions enter the PS1 palette.

## UI handoff

- `tools/ncstudio/structurepanel.py`: game map and selected-box event canvas.
- `tools/ncstudio/boxevents.py`: ownership, entry choice, merge/save and external edit protection.
- `tools/ncstudio/flowpanel.py`: shared node widgets and graph editing; standalone overview.
- `tools/ncc/ncc/flowstate.py`: shared schema validation.
- `tools/ncc/ncc/eventflow.py` and `ps2flow.py`: separate runtime generators.
- `tools/ncstudio/viewportpanel.py`: current top-down fixed-room editor.
- `tools/ncc/ncc/roomlayout.py`: viewport/runtime layout contract.

Keep IDs, ownership and target values intact when changing presentation. Event saves reject external changes instead of overwriting them; re-select the box to reload. Renaming a box label does not change its ID. Deleting an event-owned map box requires repairing ownership/destinations before building.

The viewport now offers object selection, optional 0.25-unit snap and camera yaw direction guides. These are authoring guides, not console-frustum previews. Player/key/door positions and the three camera yaw values compile into the fixed-room runtime. Save/Build persist layout edits with external-change checks. Reload asks before discarding edits. Arbitrary objects, sprite layers and a rendered 3D view remain separate work.
