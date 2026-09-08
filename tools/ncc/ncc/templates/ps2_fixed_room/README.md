# PS2 Fixed Camera Room

D-pad moves the green character. Approach the rotating amber key and press X.
Approach the door at the right and press X again. Walk through after it opens;
the background turns green. START resets. L1/R1 selects camera views.
Crossing the room centre switches cameras via On zone nodes.

Open EVENTS in Studio: this graph is enabled and compiled into the PS2 build.
Set camera accepts 0..2; Interact and Reset game take 0.
The adapter implements proximity checks, one inventory flag, key rotation,
walk bob and door rotation. It is not a general inventory or skeletal animator.
Wireframes have no occlusion or texture support. Hardware verification pending.

SQUARE starts a 90-update walk to the key via the Move to event node.

On arrival now attempts interaction automatically. Circle cancels Move to.
Cancelling does not fire On arrival.
