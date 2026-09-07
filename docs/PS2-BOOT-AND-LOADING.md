# PS2 boot and resource loading

## Current test build

The VN resets the IOP before loading pad or audio modules. This avoids depending
on modules left resident by the ELF launcher. Audio still shows its startup stage;
this change needs a real-console test. It is not evidence that sound now works.

All current VN art and compressed audio are embedded in the ELF. Music is decoded
incrementally, but is NOT read incrementally from USB. Main RAM, IOP RAM, VRAM
and SPU2 RAM are separate budgets. The bank size limit is a conservative content
allowance, not a measurement of free SPU2 memory with the software mixer.

## Install a menu entry without a second ELF

1. Copy the supplied GAME.ELF to USB at NC/PS2/VN/GAME.ELF.
2. Open Free McBoot Configurator. Load your existing configuration first.
3. In Configure OSDSYS options, choose an unused Configure Item slot.
4. Name it NC Visual Novel and set Path1 to mass:/NC/PS2/VN/GAME.ELF.
5. Return and Save CNF to the memory card containing your FMCB configuration.
6. Test this menu entry before enabling automatic launch.

For automatic launch, set AUTO under Configure E1 launch keys to that same ELF.
Keep an accessible launch-key shortcut for the Configurator or wLaunchELF, and
keep OSDSYS as a fallback where your version supports additional AUTO paths.
Save the configuration again. Menu wording varies by FMCB version.

Do not replace the entire FREEMCB.CNF with a generated file: it contains your
existing menu entries and recovery shortcuts. The game remains on USB; the
memory card stores only the launch configuration.

Reference configuration:
https://github.com/israpps/FreeMcBoot-Installer/blob/master/MASS/FREEMCB.CNF

## Optional future NC launcher

A small memory-card ELF could select games from a USB manifest, display missing
media errors and chainload the selected game. It must initialize its own storage
drivers and use a loader that handles overlapping ELF memory safely. A plain
SifLoadElf into the launcher's own address range is not sufficient. This is not
implemented or needed for the single-game FMCB entry above.

## Resource architecture to implement after audio startup is verified

- Explicit init, splash, intro, menu, room-load, play and room-unload states.
- Persistent UI assets plus room-scoped banks with dependency tracking.
- A storage abstraction with explicit game-root paths, not inherited CWD.
- Reload USB drivers after IOP reset before attempting external file reads.
- Bounded music buffers, prefill before playback, short-read/underrun reporting.
- Separate video support with decoder and bandwidth budgets; not yet supported.
- Account for peak transition memory (old room plus incoming room), not just
  individual scene size. Reject an over-budget transition before loading it.

A loading animation alone does not change memory ownership or make blocking
driver RPC calls safe. Keep hardware startup testing separate from changing
the entire storage format so failures remain attributable.
