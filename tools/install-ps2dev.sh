#!/bin/sh
# Install the PS2 toolchain (ps2dev) into toolchain/ps2dev.
#
# ps2dev is the open-source PlayStation 2 SDK: the EE and IOP cross compilers,
# PS2SDK, gsKit and friends. The project publishes prebuilt archives per
# platform, which is the whole reason this is a download rather than the
# multi-hour source build ps2dev has historically needed on Windows.
#
# It lands beside psn00bsdk under toolchain/, which .gitignore excludes -- a
# 900 MB toolchain does not belong in the repository.
#
# Two things about the Windows archive are not obvious and cost an afternoon:
#
#   1. It contains symlinks under ps2sdk/ports/bin. Windows refuses to create
#      them without developer mode, and tar then aborts the whole extraction.
#      They are only convenience aliases for bzip2, so they are skipped.
#
#   2. The binaries are 32-bit and dynamically linked against the MinGW
#      runtime, which is not shipped with them. Without those DLLs the driver
#      starts, spawns cc1, and cc1 dies silently -- make reports "Error 1" with
#      no diagnostic at all, which is a miserable thing to debug. So this
#      fetches the i686 runtime from the MSYS2 repository and puts a copy beside
#      every executable in the toolchain. Beside, rather than on PATH, so
#      nothing depends on the machine having MinGW installed.
#
# Requires: curl, tar, python3 (3.14+, for zstd). Then: ncc doctor --target ps2

set -e

VERSION="${PS2DEV_VERSION:-v2.0.0}"
ASSET="ps2dev-windows-latest.tar.gz"
case "$(uname -s)" in
    Linux*)  ASSET="ps2dev-ubuntu-latest.tar.gz" ;;
    Darwin*) ASSET="ps2dev-macos-latest.tar.gz" ;;
esac

NC_ROOT=$(cd "$(dirname "$0")/.." && pwd)
DEST="$NC_ROOT/toolchain/ps2dev"
CACHE="$NC_ROOT/toolchain/_dl"
URL="https://github.com/ps2dev/ps2dev/releases/download/$VERSION/$ASSET"
CC="$DEST/ps2dev/ee/bin/mips64r5900el-ps2-elf-gcc"

if "$CC" --version >/dev/null 2>&1 || "$CC.exe" --version >/dev/null 2>&1; then
    echo "ps2dev is already installed and working at $DEST"
    exit 0
fi

mkdir -p "$CACHE" "$DEST"

if [ ! -s "$CACHE/$ASSET" ]; then
    echo "Downloading $ASSET (about 260 MB)..."
    curl -L --fail -o "$CACHE/$ASSET" "$URL"
fi

echo "Extracting..."
tar -xzf "$CACHE/$ASSET" -C "$DEST" --exclude='ps2dev/ps2sdk/ports/bin/*'

case "$(uname -s)" in
    MINGW*|MSYS*|CYGWIN*)
        echo "Fetching the 32-bit MinGW runtime the binaries need..."
        python "$NC_ROOT/tools/ps2dev_runtime.py" "$DEST/ps2dev"
        ;;
esac

if ! "$CC" --version >/dev/null 2>&1 && ! "$CC.exe" --version >/dev/null 2>&1; then
    echo "error: the compiler still will not run. Look at $DEST" >&2
    exit 1
fi

echo
echo "Installed. Check it with:  ./ncc doctor --target ps2"
