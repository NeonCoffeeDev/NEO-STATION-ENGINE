PS2 coordinate/DMA repair — 2026-09-07

Copy these ELF files to your USB and launch with uLaunchELF.
Test NCPAD.ELF first: a centred 96x96 cyan square on a dark background.
D-pad moves; X changes colour; L1/R1 resize; START restores 96x96.
NCPULSE.ELF: cycling background and centred 200x200 white square.
NCTEX.ELF: texture diagnostic panels. NCVN.ELF: title/menu prototype.

All four were rebuilt from clean sources. Hardware rendering is not yet verified.
No separate assets are required: textures/fonts are embedded in these ELFs.
Fixes: centred libdraw coordinates, explicit GIF initialization and fast waits,
Windows POSIX build shell, and PS2 object cleanup.

The previous missing-marker/stale-binary diagnosis was not valid.
libdraw adds its own 2048 origin; XYOFFSET retains the hardware origin while
rectangles and clears now use screen coordinates minus half the screen size.
