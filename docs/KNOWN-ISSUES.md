# Known issues

## Spaces in the build directory break the PS1 link step

**Symptom.** Compile and link succeed, then the build dies with a bare
`Access is denied.` from `ninja`, pointing at the combined link + `elf2x` + `nm`
command. No output `.exe`/`.bin` is produced.

**Cause.** PSn00bSDK's CMake rules chain the post-link steps into a single nested
`cmd /C "... && cmd /C "..." ..."` invocation. When the paths inside contain a space,
cmd's quote parsing mangles the final redirect and the command fails. Running the same
`elf2x.exe` by hand succeeds, which is what makes this misleading to diagnose.

**Scope — verified 2026-09-05 on this machine:**

| Path                          | Spaces OK? |
|-------------------------------|------------|
| CMake **source** dir          | yes        |
| CMake **binary/build** dir    | **no**     |
| `PSN00BSDK_LIBS` (SDK itself) | yes        |

Only the build directory matters. This is why `C:\Users\bates\Desktop\NC HOMEBREW`
works as a project root but its in-tree `build/` subdirectory does not.

**Workaround.** Configure with an explicit space-free binary dir instead of the
bundled `default` preset:

```bash
cmake -G Ninja -S . -B /c/ncbuild/<project> \
      -DCMAKE_TOOLCHAIN_FILE="$PSN00BSDK_LIBS/cmake/sdk.cmake" \
      -DPSN00BSDK_TARGET=mipsel-none-elf -DCMAKE_BUILD_TYPE=Debug
cmake --build /c/ncbuild/<project>
```

`ncc build` must do this automatically and must never hand CMake a binary dir
containing a space. `ncc doctor` warns when the project root has one, because the
default preset will then fail.

**Not fixed by** renaming the project folder, unless you also stop using the in-tree
`build/` directory — though renaming does make the stock preset work again.

## Spaces also break GNU Make (OpenBIOS build)

**Symptom.** Building OpenBIOS from a path containing a space fails with a flood of
missing-header errors (`openbios/patches/patches.h: No such file or directory`).

**Cause.** Same class of bug as above, different tool. `common.mk` computes its root
with `$(dir $(abspath $(lastword $(MAKEFILE_LIST))))`; make does not quote the result,
so a space splits the `-I` flag. Building under `NC HOMEBREW` emits:

```
-IC:/Users/bates/Desktop/ HOMEBREW/toolchain/src/pcsx-redux/src/mips/
```

Note the `NC` has vanished and the path is now two arguments.

**Workaround.** `tools/build-openbios.sh` builds in `%LOCALAPPDATA%\NeonCoffee\src`
and refuses to run if that path contains a space.

## RESOLVED: the project folder was renamed

CMake and GNU Make were both bitten by the space in `NC HOMEBREW`, each with a
different and misleading error. On 2026-09-05 the folder was renamed to
`NC-HOMEBREW`, which removes the whole class of problem: projects now build
in-tree and neither workaround is exercised.

The workarounds above stay in place, because they still apply if a project is
created somewhere else with a space in its path. `ncc doctor` still warns, and
`ncc build` still redirects the build directory when it has to.

One footnote from the rename itself: the folder could not be renamed while
DuckStation was running, because `ncc run` spawned it without setting `cwd` and
the emulator inherited the project directory, holding a lock on it. Fixed -- it
now launches with the build directory as its working directory.
