# Learning with event kits

Select a project, open EVENTS, choose a kit and click INSERT KIT. New nodes and
connections are appended below existing work. Insertion switches the graph to
Draft. Edit parameters, remove duplicate event handlers, then click ENABLE and
build. Flow examples also ship in the templates' flow-examples directories.
These files are references; only the project's event-flow.json is executed.

## PS2 fixed-camera adapter

- Interaction with cooldown: CROSS -> Cooldown 20 -> Interact. Limits accepted
  interactions to one per 20 updates. It does not queue ignored button presses.
- One-time camera reveal: zone 1 -> Once -> camera 1. The gate is shared by every
  incoming connection to that node, and resets at program start.
- Delayed establishing shot: after 180 updates -> camera 2. Runs once from boot.
- Timed camera demonstration: every 300 updates -> camera 0. Repeats from boot.
- Restart button: START -> Reset game. Resets the room's gameplay state, not the
  event clock or Once gates. Reboot to restart the whole event session.

Timers count game updates, not wall-clock seconds. At 60 updates/sec, 180 frames
is about three seconds; slower rendering takes longer. Timers accept 1..36000.
No blocking sleeps are generated. These nodes currently belong exclusively to
the PS2 fixed_room_v1 adapter. They are unavailable to PS1 and other PS2 adapters.

## PS1 recipes

Button-to-room, reveal/hide pooled sprite, and UI sound recipes use existing
indices in scene.json. Set those indices before enabling. Showing a pooled
sprite does not allocate an object, position it, or reset its gameplay state.
Check sound availability before using the UI sound recipe.

## Connections and execution

Events trigger connected actions in connection order. Once/Cooldown guard all
their downstream actions. A shared action executes once for each path that
reaches it; avoid diamond-shaped connections unless that is intentional.
Cycles and disconnected actions are rejected. PS2 source generation checks the
project adapter and target; copying a PS2 kit into a PS1 graph does not grant
PS1 support for its nodes.

Runtime object spawning, general inventory layouts, animation graphs, branching
conditions, reusable subgraph execution and reference-safe asset edits are not
implemented by these kits. They are examples of the current executable subset.

## Move to (PS2 fixed room)

SQUARE -> Move to (-2, 1.5, 90) is included in the fixed-room example.
Double-click Move to for separate X, Z and duration fields. The player moves
linearly over that many updates; manual movement is suspended until arrival.
A new Move to replaces the previous destination from the current position.
Reset game cancels movement. Bounds are X -3..3 and Z -2..2.

This is not teleportation, pathfinding or collision avoidance. Following actions
run immediately after starting movement, not upon arrival. Use it only in the
updated fixed-room runtime; the compiler rejects older adapters missing the
movement function. PS1 does not inherit this node.

Select a node to read its help. CONNECT prompts for source then destination.
UNLINK removes all connections touching the selected node and returns the graph
to Draft. It does not delete the node. Reconnect and ENABLE before building.
