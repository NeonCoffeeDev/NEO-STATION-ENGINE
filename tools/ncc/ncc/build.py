"""ncc new / build / run / clean -- the PS1 development loop."""

import os
import re
import shutil
import subprocess
import sys

from . import toolchain as tc

TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "template")
SUBST_EXTS = {".c", ".h", ".txt", ".xml", ".cnf", ".md"}


def _volume_name(name):
    """ISO9660 volume id: uppercase, alnum + underscore, 32 chars max."""
    v = re.sub(r"[^A-Za-z0-9_]", "_", name).upper()
    return (v or "NC_PROJECT")[:32]


def _is_project(path):
    return os.path.isfile(os.path.join(path, "CMakeLists.txt"))


def _resolve(path):
    path = os.path.abspath(path or ".")
    if not _is_project(path):
        raise SystemExit(
            f"ncc: no CMakeLists.txt in {path}\n"
            f"     Not a Neon Coffee project. Create one with:  ncc new <name>"
        )
    return path


# ---- new ----------------------------------------------------------------

def new(args):
    name = args.name
    dest = os.path.abspath(args.path or name)

    if os.path.exists(dest) and os.listdir(dest):
        raise SystemExit(f"ncc: {dest} already exists and is not empty.")

    shutil.copytree(TEMPLATE_DIR, dest, dirs_exist_ok=True)

    volume = _volume_name(name)
    for root, _, files in os.walk(dest):
        for f in files:
            p = os.path.join(root, f)
            if os.path.splitext(f)[1].lower() not in SUBST_EXTS:
                continue
            with open(p, encoding="utf-8") as fh:
                text = fh.read()
            new_text = text.replace("@NAME@", name).replace("@VOLUME@", volume)
            if new_text != text:
                with open(p, "w", encoding="utf-8") as fh:
                    fh.write(new_text)

    print(f"Created {dest}")
    print("\n  Next:")
    print(f"    ncc run {os.path.relpath(dest)}")
    print("\n  Edit src/main.c to change the game; nc_gfx.c and nc_input.c are the")
    print("  engine. See docs/GETTING-STARTED.md.")
    return 0


# ---- build --------------------------------------------------------------

def _configure(src, build_dir, env):
    cmake = tc.require("cmake")
    print(f"  configuring -> {build_dir}")
    r = subprocess.run(
        [cmake, "-G", "Ninja", "-S", src, "-B", build_dir,
         f"-DCMAKE_TOOLCHAIN_FILE={os.path.join(tc.sdk_libs(), 'cmake', 'sdk.cmake')}",
         "-DPSN00BSDK_TARGET=mipsel-none-elf",
         "-DCMAKE_BUILD_TYPE=Debug"],
        env=env, capture_output=True, text=True,
    )
    if r.returncode != 0:
        sys.stdout.write(r.stdout)
        sys.stderr.write(r.stderr)
        raise SystemExit("ncc: cmake configure failed.")


def build(args):
    src = _resolve(getattr(args, "path", None))
    build_dir, redirected = tc.build_dir_for(src)
    env = tc.build_env()

    print(f"Building {os.path.basename(src)}")
    if redirected:
        print("  note: project path contains a space, so the build directory is")
        print(f"        redirected out of tree (docs/KNOWN-ISSUES.md)")

    os.makedirs(build_dir, exist_ok=True)
    if not os.path.isfile(os.path.join(build_dir, "build.ninja")):
        _configure(src, build_dir, env)

    cmake = tc.require("cmake")
    r = subprocess.run([cmake, "--build", build_dir], env=env,
                       capture_output=True, text=True)
    if r.returncode != 0:
        sys.stdout.write(r.stdout)
        sys.stderr.write(r.stderr)
        if "Access is denied" in (r.stdout + r.stderr):
            print("\nncc: this is the spaces-in-build-path failure. The build dir was\n"
                  f"     {build_dir}\n"
                  "     See docs/KNOWN-ISSUES.md.", file=sys.stderr)
        raise SystemExit("ncc: build failed.")

    cue = os.path.join(build_dir, "game.cue")
    binf = os.path.join(build_dir, "game.bin")
    if not os.path.isfile(cue):
        sys.stdout.write(r.stdout)
        raise SystemExit("ncc: build reported success but produced no game.cue.")

    size = os.path.getsize(binf) if os.path.isfile(binf) else 0
    print(f"  ok  {cue}  ({size / 1048576:.1f} MB)")
    return 0


# ---- run ----------------------------------------------------------------

def run(args):
    rc = build(args)
    if rc != 0:
        return rc

    src = _resolve(getattr(args, "path", None))
    build_dir, _ = tc.build_dir_for(src)
    cue = os.path.join(build_dir, "game.cue")

    duck = tc.find_duckstation()
    if not duck:
        print("\nncc: DuckStation not found. Build output is at:")
        print(f"     {cue}")
        return 1

    print(f"  launching DuckStation")
    subprocess.Popen([duck, cue])
    return 0


# ---- clean --------------------------------------------------------------

def clean(args):
    src = _resolve(getattr(args, "path", None))
    build_dir, _ = tc.build_dir_for(src)
    if os.path.isdir(build_dir):
        shutil.rmtree(build_dir)
        print(f"Removed {build_dir}")
    else:
        print("Nothing to clean.")
    return 0
