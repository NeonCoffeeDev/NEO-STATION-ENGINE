"""ncc new / build / run / clean -- the PS1 development loop."""

import json
import os
import re
import shutil
import subprocess
import sys
import time

from . import ncpkg
from . import ncscript
from . import toolchain as tc

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")
COMMON_DIR = os.path.join(TEMPLATES_DIR, "_common")
# The Godot editor plugin is shared by every template that ships a Godot project.
# Keeping one copy avoids the two drifting apart.
GODOT_ADDON_DIR = os.path.join(TEMPLATES_DIR, "_godot_addon")
DEFAULT_TEMPLATE = "cube"

# Files that get @NAME@ / @VOLUME@ substituted.
SUBST_EXTS = {".c", ".h", ".txt", ".xml", ".cnf", ".md",
              ".gd", ".tscn", ".godot", ".cfg", ".json"}


# ---- templates ----------------------------------------------------------

def list_templates():
    """Every template except the shared _common overlay, in display order."""
    out = []
    if not os.path.isdir(TEMPLATES_DIR):
        return out
    for name in sorted(os.listdir(TEMPLATES_DIR)):
        path = os.path.join(TEMPLATES_DIR, name)
        if name.startswith("_") or not os.path.isdir(path):
            continue
        meta = {"name": name, "title": name, "description": "", "detail": "",
                "order": 99}
        meta_path = os.path.join(path, "template.json")
        if os.path.isfile(meta_path):
            try:
                with open(meta_path, encoding="utf-8") as fh:
                    meta.update(json.load(fh))
            except (OSError, ValueError):
                pass          # a broken template.json should not hide the template
        meta["path"] = path
        out.append(meta)
    out.sort(key=lambda m: (m.get("order", 99), m["name"]))
    return out


def template_names():
    return [t["name"] for t in list_templates()]


def templates(args):
    for t in list_templates():
        mark = " (default)" if t["name"] == DEFAULT_TEMPLATE else ""
        print(f"\n  {t['name']}{mark}")
        print(f"    {t['title']}")
        if t.get("description"):
            print(f"    {t['description']}")
        if t.get("detail"):
            print(f"    {t['detail']}")
    print()
    return 0


# ---- helpers ------------------------------------------------------------

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


def _save_id(name):
    """A memory card filename fragment: 8 uppercase alphanumerics.

    The BIOS caps a card filename at 20 characters and the region/serial prefix
    already uses 12, so this is what is left. It also has to be unique per game
    -- the card is shared with every other title on the shelf.
    """
    v = "".join(c for c in name.upper() if c.isalnum())
    return (v or "NCGAME")[:8].ljust(8, "X")


def _substitute(root, name):
    volume = _volume_name(name)
    save_id = _save_id(name)
    for base, _, files in os.walk(root):
        for f in files:
            p = os.path.join(base, f)
            if os.path.splitext(f)[1].lower() not in SUBST_EXTS:
                continue
            try:
                with open(p, encoding="utf-8") as fh:
                    text = fh.read()
            except (OSError, UnicodeDecodeError):
                continue
            new_text = (text.replace("@NAME@", name)
                            .replace("@VOLUME@", volume)
                            .replace("@SAVEID@", save_id))
            if new_text != text:
                with open(p, "w", encoding="utf-8") as fh:
                    fh.write(new_text)


# ---- new ----------------------------------------------------------------

def new(args):
    name = args.name
    template = getattr(args, "template", None) or DEFAULT_TEMPLATE
    available = template_names()

    if template not in available:
        raise SystemExit(
            f"ncc: unknown template '{template}'.\n"
            f"     Available: {', '.join(available)}\n"
            f"     See them with:  ncc templates"
        )

    dest = os.path.abspath(args.path or name)
    if os.path.exists(dest) and os.listdir(dest):
        raise SystemExit(f"ncc: {dest} already exists and is not empty.")

    # Shared engine + build files first, then the template's own main.c on top.
    shutil.copytree(COMMON_DIR, dest, dirs_exist_ok=True)

    tpl_dir = os.path.join(TEMPLATES_DIR, template)
    if not os.path.isfile(os.path.join(tpl_dir, "main.c")):
        raise SystemExit(f"ncc: template '{template}' has no main.c")

    # Copy everything the template provides, not just main.c -- a template may
    # also ship data files such as scene.json. main.c lands in src/; anything
    # else keeps its relative path.
    for base, _, files in os.walk(tpl_dir):
        for f in files:
            if f == "template.json":
                continue                    # metadata, not project content
            abs_src = os.path.join(base, f)
            rel = os.path.relpath(abs_src, tpl_dir)
            rel = os.path.join("src", "main.c") if rel == "main.c" else rel
            abs_dst = os.path.join(dest, rel)
            os.makedirs(os.path.dirname(abs_dst), exist_ok=True)
            shutil.copy2(abs_src, abs_dst)

    # Any template with a godot/ folder gets the shared editor plugin.
    godot_dir = os.path.join(dest, "godot")
    if os.path.isdir(godot_dir) and os.path.isdir(GODOT_ADDON_DIR):
        shutil.copytree(GODOT_ADDON_DIR, os.path.join(godot_dir, "addons"),
                        dirs_exist_ok=True)

    _substitute(dest, name)

    print(f"Created {dest}")
    print(f"  template: {template}")
    print("\n  Next:")
    print(f"    ncc run {os.path.relpath(dest)}")
    if os.path.exists(os.path.join(dest, "script.ncs")):
        print("\n  Edit script.ncs for the logic and scene.json for what exists")
        print("  (or open godot/ and press \"Export to NC\"). Everything under")
        print("  src/ is the engine and needs no editing.")
    else:
        print("\n  Edit src/main.c to change the game; the other files in src/")
        print("  are the engine.")
    print("  See docs/GETTING-STARTED.md.")
    return 0


MUSIC_BEGIN = "<!-- NC:MUSIC -->"
MUSIC_END = "<!-- /NC:MUSIC -->"


def _sync_music_tracks(src):
    """Rewrite iso.xml's music region from scene.json's "music" list.

    Music is a CD-DA track rather than an SPU sample -- a song is far larger
    than the SPU's 512 KB -- and mkpsxiso needs each one declared in the disc
    layout. Keeping that in step by hand is exactly the sort of thing that
    silently produces a game with no music.
    """
    iso = os.path.join(src, "iso.xml")
    scene = os.path.join(src, "scene.json")
    if not (os.path.isfile(iso) and os.path.isfile(scene)):
        return

    with open(scene, encoding="utf-8") as fh:
        try:
            tracks = json.load(fh).get("music", [])
        except ValueError:
            return                      # the scene check reports this properly

    with open(iso, encoding="utf-8") as fh:
        text = fh.read()
    if MUSIC_BEGIN not in text or MUSIC_END not in text:
        if tracks:
            print("  note: iso.xml has no NC:MUSIC markers, so music tracks "
                  "were not added")
        return

    lines = []
    for n, rel in enumerate(tracks):
        path = rel if os.path.isabs(rel) else os.path.join(src, rel)
        if not os.path.isfile(path):
            raise SystemExit(
                "ncc: music track %d not found: %s\n"
                "     'music' in scene.json lists files relative to the "
                "project." % (n + 2, path))
        lines.append(
            '\t<track type="audio" source="${PROJECT_SOURCE_DIR}/%s" />'
            % rel.replace("\\", "/"))

    head = text.split(MUSIC_BEGIN)[0]
    tail = text.split(MUSIC_END, 1)[1]
    body = ("\n" + "\n".join(lines) + "\n\t") if lines else "\n\t"
    new = head + MUSIC_BEGIN + body + MUSIC_END + tail
    if new != text:
        with open(iso, "w", encoding="utf-8") as fh:
            fh.write(new)
    if tracks:
        print(f"  music: {len(tracks)} CD track(s) -> tracks 2..{len(tracks) + 1}")


# ---- build --------------------------------------------------------------

def _configure(src, build_dir, env, config):
    cmake = tc.require("cmake")
    print(f"  configuring -> {build_dir}")
    r = subprocess.run(
        [cmake, "-G", "Ninja", "-S", src, "-B", build_dir,
         f"-DCMAKE_TOOLCHAIN_FILE={os.path.join(tc.sdk_libs(), 'cmake', 'sdk.cmake')}",
         "-DPSN00BSDK_TARGET=mipsel-none-elf",
         f"-DCMAKE_BUILD_TYPE={config}"],
        env=env, capture_output=True, text=True,
    )
    if r.returncode != 0:
        sys.stdout.write(r.stdout)
        sys.stderr.write(r.stderr)
        raise SystemExit("ncc: cmake configure failed.")


def _config_of(args):
    """Release is -O2 and inlines the thin script wrappers; Debug is -Og."""
    return "Release" if getattr(args, "release", False) else "Debug"


def build(args):
    src = _resolve(getattr(args, "path", None))
    config = _config_of(args)
    build_dir, redirected = tc.build_dir_for(src, config)
    env = tc.build_env()
    started = time.time()

    print(f"Building {os.path.basename(src)}  [{config}]")
    if redirected:
        print("  note: project path contains a space, so the build directory is")
        print("        redirected out of tree (docs/KNOWN-ISSUES.md)")

    # Compile scene.json -> scene.ncpkg before configuring, so CMake sees the
    # package and links it in. Projects with geometry in C have no scene.json.
    scene = os.path.join(src, "scene.json")
    if os.path.isfile(scene):
        pkg_path = os.path.join(src, "scene.ncpkg")
        try:
            (size, n_mesh, n_inst, n_scene, n_tex,
             n_snd) = ncpkg.pack_file(scene, pkg_path)
        except (ncpkg.NcpkgError, ncpkg.TextureError,
                ncpkg.AudioError) as exc:
            raise SystemExit(f"ncc: scene.json is not valid -- {exc}")
        except ValueError as exc:
            raise SystemExit(f"ncc: scene.json is not valid JSON -- {exc}")
        print(f"  scene.json -> scene.ncpkg  ({size} bytes, {n_mesh} mesh(es), "
              f"{n_tex} texture(s), {n_snd} sound(s), {n_scene} scene(s), "
              f"{n_inst} object(s))")

    # Transpile script.ncs -> C before configuring. The generated file lands in
    # src/ so the existing glob picks it up; it is gitignored, because it is
    # build output rather than something anyone should edit.
    script = os.path.join(src, "script.ncs")
    if os.path.isfile(script):
        gen = os.path.join(src, "src", "nc_script_generated.c")
        try:
            lines = ncscript.compile_file(script, gen)
        except ncscript.ScriptError as exc:
            raise SystemExit(f"ncc: script.ncs -- {exc}")
        print(f"  script.ncs -> C  ({lines} lines)")

    _sync_music_tracks(src)

    os.makedirs(build_dir, exist_ok=True)
    if not os.path.isfile(os.path.join(build_dir, "build.ninja")):
        _configure(src, build_dir, env, config)

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

    # Surface compiler warnings even on success -- they are easy to miss.
    for line in (r.stdout or "").splitlines():
        if "warning:" in line.lower():
            print(f"  {line.strip()}")

    cue = os.path.join(build_dir, "game.cue")
    binf = os.path.join(build_dir, "game.bin")
    if not os.path.isfile(cue):
        sys.stdout.write(r.stdout)
        raise SystemExit("ncc: build reported success but produced no game.cue.")

    size = os.path.getsize(binf) if os.path.isfile(binf) else 0
    print(f"  ok  {cue}  ({size / 1048576:.1f} MB, {time.time() - started:.1f}s)")
    return 0


# ---- run ----------------------------------------------------------------

def run(args):
    rc = build(args)
    if rc != 0:
        return rc

    src = _resolve(getattr(args, "path", None))
    build_dir, _ = tc.build_dir_for(src, _config_of(args))
    cue = os.path.join(build_dir, "game.cue")

    duck = tc.find_duckstation()
    if not duck:
        print("\nncc: DuckStation not found. Build output is at:")
        print(f"     {cue}")
        return 1

    if not tc.find_openbios():
        print("\nncc: warning -- no BIOS found in DuckStation's bios/ folder.")
        print("     It will refuse to boot. Build one with tools/build-openbios.sh")

    print("  launching DuckStation")
    # Launch with the build dir as cwd, never the project. A child process
    # inheriting the project directory holds a lock on it, which blocks
    # renaming or moving the project while the emulator is open.
    subprocess.Popen([duck, cue], cwd=build_dir)
    return 0


# ---- clean --------------------------------------------------------------

def clean(args):
    """Remove both configurations -- 'clean' should mean clean."""
    src = _resolve(getattr(args, "path", None))
    removed = False
    for config in ("Debug", "Release"):
        build_dir, _ = tc.build_dir_for(src, config)
        if os.path.isdir(build_dir):
            shutil.rmtree(build_dir)
            print(f"Removed {build_dir}")
            removed = True
    if not removed:
        print("Nothing to clean.")
    return 0
