# Activate the Neon Coffee PS1 toolchain for this shell only.
#   source ./env.sh
# Nothing is written to your global PATH or user environment.

NC_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SDK="$NC_ROOT/toolchain/psn00bsdk"

if [ ! -d "$SDK" ]; then
    echo "PSn00bSDK not found at $SDK. See docs/ROADMAP.md M0." >&2
    return 1
fi

export PSN00BSDK_LIBS="$SDK/lib/libpsn00b"
export NC_ROOT
case ":$PATH:" in
    *":$SDK/bin:"*) ;;
    *) export PATH="$SDK/bin:$PATH" ;;
esac

echo "Neon Coffee PS1 toolchain active."
echo "  PSN00BSDK_LIBS = $PSN00BSDK_LIBS"
