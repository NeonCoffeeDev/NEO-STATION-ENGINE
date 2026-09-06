# The open-source stack NC merges

NC writes as little as possible. Almost every box below already exists and is
maintained by someone else; NC's job is to make them work as one environment.

## PS1

| Need                  | Tool                | Notes                                        |
|-----------------------|---------------------|----------------------------------------------|
| Compiler / SDK        | **PSn00bSDK**       | MIT. GCC MIPS toolchain, libpsn00b, CMake.   |
| CD image              | **mkpsxiso**        | Ships with PSn00bSDK. XML-driven .bin/.cue.  |
| Audio                 | **psxavenc**        | WAV/audio -> SPU-ADPCM, XA, .vag.            |
| Emulator (running)    | **DuckStation**     | Accurate, fast, good enough to iterate in.   |
| Emulator (debugging)  | **PCSX-Redux**      | GDB stub, VRAM viewer, GPU debugger.         |

## PS2

| Need                  | Tool                | Notes                                        |
|-----------------------|---------------------|----------------------------------------------|
| Compiler / SDK        | **ps2dev / PS2SDK** | Official-ish community toolchain.            |
| Graphics              | **gsKit**           | Low-level Graphics Synthesizer wrapper.      |
| Graphics (higher)     | **ps2gl**           | GL-ish layer, if gsKit is too raw.           |
| Prior art             | **Tyra**            | An existing open-source PS2 engine. Read it. |
| Emulator              | **PCSX2**           |                                              |

## Shared / asset side

| Need                  | Tool                | Notes                                        |
|-----------------------|---------------------|----------------------------------------------|
| Authoring             | **Godot 4.x**       | Stock install + NC addon. Not forked.        |
| Modeling              | **Blender**         | Export via its Python API.                   |
| Texture conversion    | **Pillow**          | Quantize to 4/8-bit CLUT.                    |
| Audio conversion      | **ffmpeg**          | Normalize before psxavenc.                   |
| Orchestration         | **ncc** (ours)      | The glue. Python.                            |

## What NC actually writes

1. `ncc` — the orchestrator and asset compiler.
2. A thin runtime per target, on top of libpsn00b / gsKit, that loads `.ncpkg` and
   draws it. Small, but it is the piece nobody else has written for us.
3. The Godot addon.
4. The `.ncpkg` format that ties the three together.

That's it. Everything else is somebody else's maintained project, pinned to a version.

## The one hard integration problem

These toolchains disagree about the host OS. PSn00bSDK builds natively on Windows via
CMake/Ninja. ps2dev is realistically Linux — the sane path on Windows is the
`ps2dev/ps2dev` Docker image or WSL2. So NC must tolerate a per-target "how do I
invoke this" abstraction (native vs container) rather than assuming one shell.
Designing for that on day one is much cheaper than retrofitting it.
