#!/bin/sh
# Build OpenBIOS (PCSX-Redux) and install it into DuckStation.
#
# OpenBIOS is an open-source, freely redistributable replacement for the PS1 BIOS.
# DuckStation cannot boot anything without a BIOS image, and retail BIOS dumps are
# copyrighted -- this is the legally clean route, and it is built for homebrew.
#
# Requires: git, make, and the PSn00bSDK MIPS toolchain (mipsel-none-elf-gcc).
# Run `ncc doctor` first.
#
# NOTE: this builds in a space-free directory on purpose. GNU Make silently mangles
# include paths containing spaces -- the same class of bug as docs/KNOWN-ISSUES.md,
# but in make rather than cmake. Building under "NC HOMEBREW" produces
# `-IC:/Users/.../Desktop/ HOMEBREW/...` and fails with confusing missing-header
# errors.

set -e

NC_ROOT=$(cd "$(dirname "$0")/.." && pwd)
WORK="${LOCALAPPDATA:-$HOME}/NeonCoffee/src"
REPO="$WORK/pcsx-redux"
SDK_BIN="$NC_ROOT/toolchain/psn00bsdk/bin"

case "$WORK" in
    *" "*) echo "error: work dir '$WORK' contains a space; make will fail." >&2; exit 1 ;;
esac

export PATH="$SDK_BIN:$PATH"
command -v mipsel-none-elf-gcc >/dev/null || {
    echo "error: mipsel-none-elf-gcc not found. Run 'ncc doctor'." >&2; exit 1; }

MAKE=$(command -v make || true)
[ -n "$MAKE" ] || MAKE=$(find "$LOCALAPPDATA/Microsoft/WinGet/Packages" -iname make.exe 2>/dev/null | head -1)
[ -n "$MAKE" ] || { echo "error: GNU make not found. winget install ezwinports.make" >&2; exit 1; }

mkdir -p "$WORK"

if [ ! -d "$REPO/.git" ]; then
    echo "Cloning pcsx-redux (sparse, ~10 MB)..."
    git clone --depth 1 --filter=blob:none --no-checkout \
        https://github.com/grumpycoders/pcsx-redux.git "$REPO"
    cd "$REPO"
    git sparse-checkout init --cone
    git sparse-checkout set src/mips third_party/uC-sdk
    git checkout
else
    echo "Reusing existing clone at $REPO"
    cd "$REPO"
fi

# OpenBIOS links against uC-sdk's libc.
git submodule update --init --depth 1 third_party/uC-sdk

echo "Building OpenBIOS..."
cd "$REPO/src/mips/openbios"
"$MAKE" -j4

[ -f openbios.bin ] || { echo "error: openbios.bin was not produced." >&2; exit 1; }

# Install into whichever data dir DuckStation actually created.
for d in "$LOCALAPPDATA/DuckStation" "$HOME/Documents/DuckStation"; do
    if [ -d "$d" ]; then
        mkdir -p "$d/bios"
        cp openbios.bin "$d/bios/openbios.bin"
        echo "Installed -> $d/bios/openbios.bin"
        installed=1
    fi
done

[ -n "$installed" ] || echo "warning: no DuckStation data dir found; run DuckStation once first."
echo "Done. openbios.bin is $(wc -c < openbios.bin) bytes."
