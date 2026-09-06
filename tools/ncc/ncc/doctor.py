"""Environment check.

NC is an integration project, so "is the environment correct" is the single question
that most often blocks work. This makes the answer cheap to get.

Tools are located in three places, in order: the project-local `toolchain/` directory,
then PATH, then a few well-known install locations. Reporting which one won matters --
"missing" almost always means "installed, but this shell has not sourced env.sh".
"""

import os
import shutil
import subprocess
import sys

# Well-known install dirs to check when a tool is not on PATH.
EXTRA_DIRS = [
    r"C:\Program Files\CMake\bin",
    r"C:\Program Files (x86)\CMake\bin",
]

# (label, exe, required, why it matters, how to get it)
CHECKS_COMMON = [
    ("git", "git", True, "Fetching and pinning the upstream SDKs.",
     "https://git-scm.com/download/win"),
    ("Godot 4.x", "godot", False, "Authoring frontend. Not needed until M3.",
     "https://godotengine.org/download (expose the binary on PATH as 'godot')"),
    ("Blender", "blender", False, "Mesh authoring/export.",
     "https://www.blender.org/download/"),
    ("ffmpeg", "ffmpeg", False, "Audio normalization before psxavenc.",
     "winget install Gyan.FFmpeg"),
]

CHECKS_PS1 = [
    ("CMake", "cmake", True, "PSn00bSDK's build system.",
     "winget install Kitware.CMake"),
    ("Ninja", "ninja", True, "PSn00bSDK's generator.",
     "Bundled in toolchain/psn00bsdk/bin, or: winget install Ninja-build.Ninja"),
    ("MIPS GCC", "mipsel-none-elf-gcc", True, "The PS1 cross compiler.",
     "Bundled in the PSn00bSDK release. See docs/ROADMAP.md M0."),
    ("mkpsxiso", "mkpsxiso", True, "Builds the .bin/.cue disc image.",
     "Bundled in the PSn00bSDK release."),
    ("elf2x", "elf2x", True, "Converts the linked ELF into a PS-EXE.",
     "Bundled in the PSn00bSDK release."),
    ("DuckStation", "duckstation-qt-x64-ReleaseLTCG", False,
     "Emulator, to run what you build.",
     "https://github.com/stenzek/duckstation/releases"),
]

CHECKS_PS2 = [
    ("Docker", "docker", False, "Simplest way to run ps2dev on Windows. Deferred to M6.",
     "https://docs.docker.com/desktop/install/windows-install/"),
    ("ee-gcc", "ee-gcc", False, "PS2 cross compiler, if installed natively. Deferred to M6.",
     "Use the ps2dev/ps2dev Docker image, or WSL2 + ps2dev."),
]


def project_root():
    """Repo root, from this file's location: tools/ncc/ncc/doctor.py -> up 3."""
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


def local_bin():
    return os.path.join(project_root(), "toolchain", "psn00bsdk", "bin")


def locate(exe):
    """Return (path, source) or (None, None)."""
    lb = local_bin()
    if os.path.isdir(lb):
        hit = shutil.which(exe, path=lb)
        if hit:
            return hit, "local"
    hit = shutil.which(exe)
    if hit:
        return hit, "PATH"
    for d in EXTRA_DIRS:
        if os.path.isdir(d):
            hit = shutil.which(exe, path=d)
            if hit:
                return hit, "installed"
    return None, None


def version_of(path):
    """Best-effort one-line version string. Never raises."""
    for flag in ("--version", "-version", "-V"):
        try:
            r = subprocess.run([path, flag], capture_output=True, text=True, timeout=10)
            out = (r.stdout or r.stderr).strip()
            if out:
                return out.splitlines()[0][:60]
        except Exception:
            continue
    return "(found)"


def section(title, checks, missing):
    print(f"\n  {title}")
    print("  " + "-" * len(title))
    for label, exe, required, why, how in checks:
        path, source = locate(exe)
        if path:
            tag = "" if source == "PATH" else f"  [{source}]"
            print(f"  [ok]      {label:<14} {version_of(path)}{tag}")
        else:
            mark = "MISSING" if required else "  --   "
            print(f"  [{mark}] {label:<14} {why}")
            print(f"            -> {how}")
            if required:
                missing.append(label)


def run(args):
    missing = []
    print("\nNeon Coffee - environment check")
    print(f"  python  {sys.version.split()[0]}  ({sys.platform})")
    print(f"  root    {project_root()}")

    section("Common", CHECKS_COMMON, missing)
    if args.target in ("ps1", "all"):
        section("PS1 target", CHECKS_PS1, missing)
    if args.target in ("ps2", "all"):
        section("PS2 target", CHECKS_PS2, missing)

    print("\n  Project")
    print("  -------")
    root = project_root()
    if " " in root:
        print("  [warn]  Project path contains a space.")
        print("          PSn00bSDK's stock CMake preset fails on this: the nested")
        print("          cmd /C post-link step mangles quoting and dies with a bare")
        print("          'Access is denied.'  Source dirs are fine; the BUILD dir")
        print("          must be space-free. ncc build handles this automatically.")
        print("          See docs/KNOWN-ISSUES.md.")
    else:
        print("  [ok]    Project path is space-free.")

    print("\n  Environment")
    print("  -----------")
    libs = os.environ.get("PSN00BSDK_LIBS")
    if libs:
        print(f"  [ok]    PSN00BSDK_LIBS   {libs}")
    else:
        print("  [--]    PSN00BSDK_LIBS   unset -- run:  . ./env.ps1   (or source ./env.sh)")

    print()
    if missing:
        print(f"  {len(missing)} required tool(s) missing: {', '.join(missing)}")
        return 1
    print("  PS1 toolchain is complete.")
    return 0
