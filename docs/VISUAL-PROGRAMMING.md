> Updated: GAME FLOW now supports box-owned events and active-state execution. See [FLOW-BOXES.md](FLOW-BOXES.md); older reference-map descriptions below apply only to legacy graphs.

# Programming with events

Start in a PS2 Fixed Camera Room project. These variable/condition nodes require
that adapter; other PS2 projects and PS1 projects do not gain them automatically.

1. **Event:** when should something happen? `On button: TRIANGLE` fires once per
   press. Timers and zone entry are other supported events.
2. **State:** remember a number. `Set variable: presses, 0` assigns a value;
   `Add variable: presses, 1` increments it.
3. **Condition:** decide whether to continue. `If equal: presses, 3` passes only
   at three. `If at least` also passes at four, five, and above.
4. **Action:** perform behavior, such as `Set camera: 2`.

The Count three presses kit combines those ideas. Press TRIANGLE three times
in the fixed-room example to change cameras. A later camera-zone event can
change the camera again. The count remains three until another press.

## Tokens and flags

Insert Grant three tokens (SELECT -> Repeat 3 -> Add tokens 1) and Spend a token
(CIRCLE -> If tokens >= 1 -> Add tokens -1 -> Interact). These recipes share the
same graph variable by name. Spending happens before attempting interaction;
it is an educational counter, not a success-aware inventory transaction.
Use a variable valued 0 or 1 as a simple flag. An unset variable starts at zero.

Variables are case-sensitive and graph-local, not memory-card saves or the
room's built-in inventory. They reset on program startup. Reset game currently
resets room state only; add explicit Set variable nodes if a restart button
should clear your counters. Up to 16 names are supported, with values clamped
to -32767..32767 after addition.

## Sequencing and repetition

Connect actions in a chain to make their order obvious. Sibling connections
execute in connection order, not their visual positions. A false condition
stops only its downstream branch; there is no separate Else output yet.

Repeat executes its downstream chain 1..16 times in the same update. Use Every
frames for periodic behavior over time. Once gates and Cooldown gates can help
prevent repeated triggers. Very large expanded graphs are rejected to bound
generated code size. Cycles are not supported.

Move to starts motion and returns immediately. A following action does not wait
for arrival. Connect a separate On arrival event to actions that should wait.
Stop movement cancels motion without firing arrival. Do not use Repeat to emulate
waiting or animation. Named restartable timers, general comparisons and debugging
watches remain future work. ENABLE checks the graph before building; hardware behavior still
needs testing after edits.
