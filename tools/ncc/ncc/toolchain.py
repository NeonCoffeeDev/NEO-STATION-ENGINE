"""Locating and invoking the PS1 toolchain.

Everything that knows *where things are* lives here, so `doctor`, `build` and `run`
cannot disagree about it.
"""

import hashlib
import os
import shutil

# Well-known install dirs to search when a tool is not on PATH.
EXTRA_DIRS = [
    r"C:\Program Files\CMake\bin",
    r"C:\Program Files (x86)\CMake\bin",
]

DUCKSTATION_DIRS = [
    os.path.expandvars(
        r"%LOCALAPPDATA%\Microsoft\WinGet\Packages"
        r"\Stenzek.DuckStation_Microsoft.Winget.Source_8wekyb3d8bbwe"
    ),
    r"C:\Program Files\DuckStation",
]
DUCKSTATION_EXES = ["duckstation-qt-x64-ReleaseLTCG.exe", "duckstation-qt.exe",
                    "duckstation.exe"]


def project_root():
    """Repo root, from tools/ncc/ncc/toolchain.py -> up 3."""
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


def sdk_root():
    return os.path.join(project_root(), "toolchain", "psn00bsdk")


def sdk_bin():
    return os.path.join(sdk_root(), "bin")


def sdk_libs():
    return os.path.join(sdk_root(), "lib", "libpsn00b")


def locate(exe):
    """Find a tool. Returns (path, source) or (None, None).

    Local toolchain wins over PATH so a project is reproducible regardless of what
    else the machine has installed.
    """
    if os.path.isdir(sdk_bin()):
        hit = shutil.which(exe, path=sdk_bin())
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


def require(exe):
    path, _ = locate(exe)
    if not path:
        raise SystemExit(
            f"ncc: required tool '{exe}' not found.\n"
            f"     Run 'ncc doctor' to see what is missing."
        )
    return path


def find_duckstation():
    for d in DUCKSTATION_DIRS:
        for name in DUCKSTATION_EXES:
            p = os.path.join(d, name)
            if os.path.isfile(p):
                return p
    for name in DUCKSTATION_EXES:
        hit = shutil.which(name)
        if hit:
            return hit
    return None


def build_env():
    """Environment for invoking cmake/ninja: SDK on PATH, PSN00BSDK_LIBS set."""
    env = os.environ.copy()
    env["PSN00BSDK_LIBS"] = sdk_libs()
    extra = [sdk_bin()] + [d for d in EXTRA_DIRS if os.path.isdir(d)]
    env["PATH"] = os.pathsep.join(extra + [env.get("PATH", "")])
    return env


def build_dir_for(source_dir, config="Debug"):
    """Pick a build directory that never contains a space.

    PSn00bSDK chains its post-link steps through a nested `cmd /C "... && cmd /C
    "..."`. A space anywhere in the *build* path mangles that quoting and the build
    dies with a bare 'Access is denied.' after compiling and linking successfully.
    Source dirs are unaffected. See docs/KNOWN-ISSUES.md.

    So: build in-tree when we can, and fall back to a space-free cache dir keyed by
    a hash of the source path when we cannot.
    """
    source_dir = os.path.abspath(source_dir)
    # Debug and Release get separate directories so switching between them does
    # not force a full rebuild every time.
    suffix = "" if config == "Debug" else "-" + config.lower()
    in_tree = os.path.join(source_dir, "build" + suffix)
    if " " not in in_tree:
        return in_tree, False

    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    if " " in base:                      # extremely unusual, but be safe
        base = os.environ.get("SystemDrive", "C:") + os.sep
    tag = hashlib.sha1(source_dir.encode("utf-8")).hexdigest()[:12]
    name = "".join(c for c in os.path.basename(source_dir) if c.isalnum()) or "project"
    return os.path.join(base, "NeonCoffee", "build",
                        f"{name}-{tag}{suffix}"), True


DUCKSTATION_DATA_DIRS = [
    os.path.expandvars(r"%LOCALAPPDATA%\DuckStation"),
    os.path.join(os.path.expanduser("~"), "Documents", "DuckStation"),
]


def duckstation_data_dir():
    """Where DuckStation keeps settings.ini, bios/, memcards/ ..."""
    for d in DUCKSTATION_DATA_DIRS:
        if os.path.isdir(d):
            return d
    return None


def find_openbios():
    """The OpenBIOS image installed for DuckStation, if any."""
    d = duckstation_data_dir()
    if not d:
        return None
    p = os.path.join(d, "bios", "openbios.bin")
    return p if os.path.isfile(p) else None


GODOT_DIRS = [
    os.path.expandvars(
        r"%LOCALAPPDATA%\Microsoft\WinGet\Packages"
        r"\GodotEngine.GodotEngine_Microsoft.Winget.Source_8wekyb3d8bbwe"),
    r"C:\Program Files\Godot",
]


def find_godot(console=False):
    """The Godot 4 editor binary.

    `console=True` returns the console variant, which prints to stdout -- useful
    when driving Godot headlessly; the plain one is what a user should see.
    """
    import glob
    want = "_console.exe" if console else ".exe"
    for d in GODOT_DIRS:
        if not os.path.isdir(d):
            continue
        hits = sorted(glob.glob(os.path.join(d, "Godot_v4*.exe")))
        for h in hits:
            is_console = h.endswith("_console.exe")
            if is_console == bool(console):
                return h
    hit = shutil.which("godot")
    if hit:
        return hit
    return None

# ---- PS2 (ps2dev) ---------------------------------------------------------

PS2_PREFIX = "mips64r5900el-ps2-elf"


def ps2dev_root():
    """Where tools/install-ps2dev.sh puts the PS2 toolchain.

    The archive unpacks with its own ps2dev/ directory inside, so the real root
    is one level down from where it was extracted.
    """
    base = os.path.join(project_root(), "toolchain", "ps2dev")
    nested = os.path.join(base, "ps2dev")
    return nested if os.path.isdir(os.path.join(nested, "ee")) else base


def ps2_cc():
    """The EE compiler, or None if the toolchain is not installed."""
    exe = PS2_PREFIX + "-gcc" + (".exe" if os.name == "nt" else "")
    p = os.path.join(ps2dev_root(), "ee", "bin", exe)
    if os.path.isfile(p):
        return p
    return shutil.which(PS2_PREFIX + "-gcc") or shutil.which("ee-gcc")


def find_make():
    """GNU make. PS2SDK builds with Makefiles, not CMake."""
    hit = shutil.which("make")
    if hit:
        return hit
    # Windows has no make; ezwinports is what `ncc doctor` tells you to install,
    # and winget puts it somewhere no sane PATH includes.
    import glob
    pat = os.path.join(
        os.environ.get("LOCALAPPDATA", ""), "Microsoft", "WinGet", "Packages",
        "ezwinports.make*", "bin", "make.exe")
    hits = sorted(glob.glob(pat))
    return hits[0] if hits else None


def ps2_build_env():
    """Environment for a PS2 build: PS2DEV/PS2SDK/GSKIT set, tools on PATH.

    Every toolchain executable needs its 32-bit runtime DLLs beside it -- see
    tools/install-ps2dev.sh -- so nothing here depends on a system-wide MinGW.
    """
    root = ps2dev_root()
    env = os.environ.copy()
    env["PS2DEV"] = root
    env["PS2SDK"] = os.path.join(root, "ps2sdk")
    env["GSKIT"] = os.path.join(root, "gsKit")

    dirs = [os.path.join(root, d) for d in
            (os.path.join("ee", "bin"), os.path.join("iop", "bin"),
             os.path.join("dvp", "bin"), "bin")]
    make = find_make()
    if make:
        dirs.append(os.path.dirname(make))
    dirs = [d for d in dirs if os.path.isdir(d)]
    env["PATH"] = os.pathsep.join(dirs + [env.get("PATH", "")])
    return env
