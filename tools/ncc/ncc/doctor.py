"""Environment check.

NC is an integration project, so 'is the environment correct' is the single question
that most often blocks work. This makes the answer cheap to get.
"""

import os
import shutil
import subprocess
import sys

# (label, probe, why it matters, how to get it)
CHECKS_COMMON = [
    ("git", "git", "Fetching and pinning the upstream SDKs.",
     "https://git-scm.com/download/win"),
    ("Godot 4.x", "godot", "Authoring frontend. Optional until milestone M3.",
     "https://godotengine.org/download  (or add the binary to PATH as 'godot')"),
    ("Blender", "blender", "Mesh authoring/export. Optional.",
     "https://www.blender.org/download/"),
    ("ffmpeg", "ffmpeg", "Audio normalization before psxavenc. Optional.",
     "winget install Gyan.FFmpeg"),
]

CHECKS_PS1 = [
    ("CMake", "cmake", "PSn00bSDK's build system.",
     "winget install Kitware.CMake"),
    ("Ninja", "ninja", "PSn00bSDK's generator.",
     "winget install Ninja-build.Ninja"),
    ("MIPS GCC", "mipsel-none-elf-gcc", "The PS1 cross compiler.",
     "Installed by the PSn00bSDK toolchain build. Run: ncc setup --target ps1"),
    ("mkpsxiso", "mkpsxiso", "Builds the .bin/.cue disc image.",
     "Ships with PSn00bSDK releases."),
    ("DuckStation", "duckstation-qt-x64-ReleaseLTCG", "Emulator, to run what you build.",
     "https://github.com/stenzek/duckstation/releases"),
]

CHECKS_PS2 = [
    ("Docker", "docker", "Simplest way to run the ps2dev toolchain on Windows.",
     "https://docs.docker.com/desktop/install/windows-install/"),
    ("ee-gcc", "ee-gcc", "PS2 cross compiler, if installed natively instead of Docker.",
     "Use Docker image ps2dev/ps2dev, or WSL2 + ps2dev."),
]

ENV_VARS = [
    ("PSN00BSDK_LIBS", "Where PSn00bSDK's libraries live. PSn00bSDK's CMake needs it."),
    ("PS2SDK", "Where PS2SDK lives. Unset is fine if you use the Docker image."),
]


def _version(exe):
    """Best-effort one-line version string. Never raises."""
    for flag in ("--version", "-version", "-v"):
        try:
            r = subprocess.run([exe, flag], capture_output=True, text=True, timeout=10)
            out = (r.stdout or r.stderr).strip()
            if out:
                return out.splitlines()[0][:70]
        except Exception:
            continue
    return "(found)"


def _section(title, checks, missing):
    print(f"\n  {title}")
    print("  " + "-" * len(title))
    for label, exe, why, how in checks:
        path = shutil.which(exe)
        if path:
            print(f"  [ok]      {label:<14} {_version(exe)}")
        else:
            print(f"  [MISSING] {label:<14} {why}")
            print(f"            -> {how}")
            missing.append(label)


def run(args):
    missing = []
    print("\nNeon Coffee - environment check")
    print(f"  python  {sys.version.split()[0]}  ({sys.platform})")

    _section("Common", CHECKS_COMMON, missing)
    if args.target in ("ps1", "all"):
        _section("PS1 target", CHECKS_PS1, missing)
    if args.target in ("ps2", "all"):
        _section("PS2 target", CHECKS_PS2, missing)

    print("\n  Environment")
    print("  -----------")
    for var, why in ENV_VARS:
        val = os.environ.get(var)
        print(f"  [{'ok' if val else '--'}]  {var:<16} {val or why}")

    print()
    if missing:
        print(f"  {len(missing)} missing: {', '.join(missing)}")
        print("  Optional entries above can be ignored for now; see docs/ROADMAP.md M0.")
        return 1
    print("  Environment looks complete.")
    return 0
