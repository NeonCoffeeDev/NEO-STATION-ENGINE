# NC Bench

One boot, the whole cost model.

Every question about what this console can afford was being answered by
shipping a build, photographing a television, and reasoning from one number.
That is a slow way to be wrong, and it spends someone else's time doing it.
This runs every measurement that matters back to back and prints them as a
table, so a scene can be costed on paper afterwards instead of by another
round trip.

## Running it

Copy `bench.elf` to a USB stick and launch it from uLaunchELF or OPL. It takes
a second to measure, then draws the table and sits there. Photograph it.

## Reading it

Every row is the total ticks for the run, how many operations that was, and
the ticks per operation. A tick is the EE's cycle counter, which runs at half
the 294.912 MHz core -- so **one tick is two CPU cycles**, and one 59.94 Hz
field is **2,460,060 ticks**.

| Row | What it isolates |
|---|---|
| `LOOP OVERHEAD` | The measurement floor. Subtract mentally from small rows. |
| `PROJECT` | Camera transform and perspective divide, per vertex. |
| `PROJECT + LIGHT` | The same plus one directional light. |
| `PROJECT+LIGHT+SKIN` | The same plus rigid skinning: the full engine vertex. |
| `EMIT TRIANGLE` | Writing registers into the packet. No arithmetic. |
| `FLOAT DIVIDE` | One divide, to price the perspective divide honestly. |
| `COSF` | A trig call, to price anything done per frame rather than per vertex. |
| `READ SEQUENTIAL` | Memory that is in cache. |
| `READ STRIDED 64B` | One cache line per access, so every read misses. |

The gap between the last two rows is what a cache miss costs on this machine.
The gaps between the three `PROJECT` rows are what lighting and skinning cost
on top of the transform. Together those say whether a vertex is expensive
because of arithmetic, because of memory, or because of something else --
which is the question three separate guesses failed to settle.

The two lines under the table do the division for you: how many projected
vertices and emitted triangles fit in one field.

## Building it

Not an ncc project on purpose. It needs no VN, no audio, no materials and no
asset pipeline, and staying plain means it builds and boots even when the
engine around it does not.

    PS2SDK=<sdk> PS2DEV=<dev> PATH=$PS2DEV/ee/bin:$PATH make
