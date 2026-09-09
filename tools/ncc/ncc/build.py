"""ncc new / build / run / clean -- the PS1 development loop."""

from pathlib import Path
import json
import os
import re
import shutil
import subprocess
import sys
import time

from . import ncpkg
from . import ncscript
from . import eventflow
from . import toolchain as tc
from .targets import TARGETS

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

PROJECT_FILE = "nc.json"

def _volume_name(name):
    """ISO9660 volume id: uppercase, alnum + underscore, 32 chars max."""
    v = re.sub(r"[^A-Za-z0-9_]", "_", name).upper()
    return (v or "NC_PROJECT")[:32]


def _is_project(path):
    # A PS1 project is a CMake project; a PS2 project is a Makefile one. nc.json
    # is what both have, and what says which.
    return (os.path.isfile(os.path.join(path, "CMakeLists.txt"))
            or os.path.isfile(os.path.join(path, PROJECT_FILE)))


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


# ---- sync ---------------------------------------------------------------

# The engine files a project gets from _common and never edits. Everything else
# in a project -- main.c, script.ncs, scene.json, art -- belongs to the author.
ENGINE_FILES = [
    os.path.join("include", "nc.h"),
    os.path.join("include", "nc_script.h"),
    os.path.join("src", "nc_gfx.c"),
    os.path.join("src", "nc_input.c"),
    os.path.join("src", "nc_pkg.c"),
    os.path.join("src", "nc_phys.c"),
    os.path.join("src", "nc_scene.c"),
    os.path.join("src", "nc_script.c"),
    os.path.join("src", "nc_audio.c"),
    os.path.join("src", "nc_music.c"),
    os.path.join("src", "nc_save.c"),
]


def project_meta(root):
    """What a project says about itself.

    A project has to record its own target, because the manager cannot guess it
    from the sources -- and picking a project should reconfigure the tool around
    it rather than leave PS1 selected while you edit a PS2 game.
    """
    meta = {"format": 1, "target": "ps1", "template": "", "name": ""}
    path = os.path.join(root, PROJECT_FILE)
    try:
        with open(path, encoding="utf-8") as fh:
            meta.update(json.load(fh))
    except (OSError, ValueError):
        # A project made before nc.json existed is a PS1 project; that is what
        # the default says, and there is nothing to warn about.
        pass
    if meta.get("target") not in TARGETS:
        meta["target"] = "ps1"
    return meta


def write_project_meta(root, name, template, target):
    path = os.path.join(root, PROJECT_FILE)
    with open(path, "w", encoding="utf-8") as fh:
        meta = {"format": 1, "name": name, "template": template, "target": target}
        if template == "ps2_fixed_room" and target == "ps2":
            meta["event_adapter"] = "fixed_room_v1"
        if template == "ps2_hello":meta["event_adapter"] = "pad2d_v1"
        if template == "ps2_3d":meta["event_adapter"] = "lab3d_v1"
        if template == "ps2_vn":meta["event_adapter"] = "vn_v1"
        if template == "ps2_logo":meta["event_adapter"] = "screen2d_v1"
        json.dump(meta, fh, indent=2)
        fh.write(chr(10))


def _project_name(root):
    """The name a project was created with.

    Engine files carry placeholders -- the save path and title in nc.h -- that
    are filled in at creation. Copying a template file over a project would put
    the placeholders back and give the game a save file literally called
    @SAVEID@, so the sync has to know the name. CMakeLists.txt is where it
    survives: `ncc sync` never touches that file, so its project() line is a
    reliable record. The directory name is the fallback.
    """
    cml = os.path.join(root, "CMakeLists.txt")
    if os.path.isfile(cml):
        try:
            with open(cml, encoding="utf-8") as fh:
                text = fh.read()
        except (OSError, UnicodeDecodeError):
            text = ""
        m = re.search(r"project\s*\(\s*([^\s)]+)", text)
        if m:
            return m.group(1)
    return os.path.basename(os.path.normpath(root))


def sync(args):
    """Update a project's engine files from the templates.

    A project owns its copy of the runtime, which is what makes it a real,
    self-contained thing you can read and modify. The cost is that engine fixes
    do not reach projects made before them -- a package built by a newer `ncc`
    against an older runtime fails at boot with a version mismatch, which is a
    confusing way to learn that your project is out of date. This is the way
    back into step.

    It touches only the files above. Your game is never overwritten.
    """
    dest = os.path.abspath(args.path or ".")
    if not os.path.isdir(dest):
        raise SystemExit(f"ncc: {dest} is not a directory")

    name = _project_name(dest)
    volume = _volume_name(name)
    save_id = _save_id(name)

    def template_text(path):
        """The template file as this project should hold it."""
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        return (text.replace("@NAME@", name)
                    .replace("@VOLUME@", volume)
                    .replace("@SAVEID@", save_id))

    updated, added, same = [], [], 0
    for rel in ENGINE_FILES:
        src = os.path.join(COMMON_DIR, rel)
        dst = os.path.join(dest, rel)
        if not os.path.isfile(src):
            continue

        want = template_text(src)

        if os.path.isfile(dst):
            try:
                with open(dst, encoding="utf-8") as fh:
                    have = fh.read()
            except (OSError, UnicodeDecodeError):
                have = None
            if have == want:
                same += 1
                continue
            record = updated
        else:
            # A project that never had this file predates the feature; adding it
            # is what makes the sync useful rather than merely tidy.
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            record = added

        with open(dst, "w", encoding="utf-8", newline="") as fh:
            fh.write(want)
        record.append(rel)

    print(f"Syncing {name} with the engine templates")
    for rel in added:
        print(f"  added    {rel}")
    for rel in updated:
        print(f"  updated  {rel}")
    if not added and not updated:
        print(f"  already up to date ({same} files)")
    else:
        print(f"  {same} file(s) already current")
        print("\n  Rebuild before running:  ncc build " + os.path.relpath(dest))
    return 0


# ---- new ----------------------------------------------------------------

def new(args):
    # `ncc new path/to/mygame` is a natural thing to type, and the name is then
    # a whole path. Left alone that becomes the disc volume and the memory card
    # id, so the save shows up on the card as CUSERSBA. Take the last segment.
    name = os.path.basename(os.path.normpath(args.name.replace("\\", "/")))
    template = getattr(args, "template", None) or DEFAULT_TEMPLATE
    available = template_names()

    if template not in available:
        raise SystemExit(
            f"ncc: unknown template '{template}'.\n"
            f"     Available: {', '.join(available)}\n"
            f"     See them with:  ncc templates"
        )

    dest = os.path.abspath(args.path or args.name)
    if os.path.exists(dest) and os.listdir(dest):
        raise SystemExit(f"ncc: {dest} already exists and is not empty.")

    tpl_dir = os.path.join(TEMPLATES_DIR, template)

    meta = {}
    try:
        with open(os.path.join(tpl_dir, "template.json"), encoding="utf-8") as fh:
            meta = json.load(fh)
    except (OSError, ValueError):
        pass
    target = meta.get("target", "ps1")

    if target == "ps1":
        # The shared PS1 engine goes down first and the template lands on top.
        # A PS2 project must not get it: none of it compiles for that machine,
        # and shipping a directory of dead PS1 source would be its own lie.
        shutil.copytree(COMMON_DIR, dest, dirs_exist_ok=True)
        if not os.path.isfile(os.path.join(tpl_dir, "main.c")):
            raise SystemExit(f"ncc: template '{template}' has no main.c")
    else:
        os.makedirs(dest, exist_ok=True)

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

    write_project_meta(dest, name, template, target)

    _substitute(dest, name)

    print(f"Created {dest}")
    print(f"  template: {template}")
    print("\n  Next:")
    print(f"    ncc run {os.path.relpath(dest)}")
    if os.path.exists(os.path.join(dest, "script.ncs")):
        print("\n  Edit script.ncs for the logic and scene.json for what exists")
        print("  (or open godot/ and press \"Export to NC\"). Everything under")
        print("  src/ is the engine and needs no editing.")
    elif os.path.isfile(os.path.join(dest, "vn.json")):
        print("\n  Open godot/vn_authoring.tscn; edit VN resources in the Inspector.")
        print("  NC dock: export, check, build. See docs/VN-ESSENTIALS.md.")
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


def _build_ps2(src):
    """Build a PS2 project with PS2SDK's Makefiles.

    The PS1 side uses CMake because PSn00bSDK does; PS2SDK uses Makefiles, and
    reimplementing its link rules to force one build system would put the most
    fragile part of the toolchain in our hands for no gain.
    """
    name = os.path.basename(src)
    screens_path=Path(src)/'screens.json'
    if screens_path.exists():
        try:
            screens=json.loads(screens_path.read_text(encoding='utf-8'))
            brand=next((obj for screen in screens.get('screens',{}).values() for obj in screen.get('objects',[]) if obj.get('role')=='brand_logo' and obj.get('texture')),None)
            if brand:
                root=Path(src).resolve();source=(root/brand['texture']).resolve()
                if root not in source.parents or source.suffix.lower()!='.png' or not source.is_file():
                    raise ValueError('brand_logo must reference a project-local PNG')
                output=root/'src/logo_data.c';tool=Path(tc.project_root())/'tools/png2ps2.py'
                result=subprocess.run([sys.executable,str(tool),str(source),str(output),'nc_logo','128'],capture_output=True,text=True)
                if result.returncode:raise ValueError(result.stderr or result.stdout)
                print('  Sprite2D brand logo -> src/logo_data.c')
        except (OSError,ValueError,KeyError,TypeError) as exc:raise SystemExit(f"ncc: screens.json brand logo -- {exc}")
    if project_meta(src).get("event_adapter") == "fixed_room_v1":
        from . import roomlayout
        try:
            roomlayout.compile_project(src)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise SystemExit(f"ncc: room-layout.json -- {exc}")
    if project_meta(src).get("event_adapter") == "lab3d_v1":
        from .lablayout import compile_project
        compile_project(src)
    if project_meta(src).get("event_adapter") == "pad2d_v1":
        from .viewportdata import World
        world=World(src);world.validate()
        x,y=world.doc["objects"]["box"]
        Path(src,"src","nc_pad_layout.h").write_text(f"#define NC_PAD_X {int(x)}\n#define NC_PAD_Y {int(y)}\n",encoding="utf-8")
    material_layout=Path(src)/'room-layout.json'
    has_materials=os.path.exists(os.path.join(src,'world3d.json')) or (material_layout.exists() and 'materials' in material_layout.read_text(encoding='utf-8'))
    if has_materials:
        from .ps2materials import compile_project as compile_materials
        try:compile_materials(src)
        except (OSError,ValueError,KeyError,TypeError) as exc:raise SystemExit(f"ncc: PS2 materials -- {exc}")
    print(f"Building {name}  [PS2]")
    from .vn import compile_content
    try:
        compile_content(src)
    except (OSError, ValueError) as exc:
        raise SystemExit(f"ncc: vn.json: {exc}")

    # Audio is whatever is sitting in audio/sfx and audio/music. Adding a sound
    # is putting a file in a folder; the encoding, the sample rate and the
    # budget are handled here rather than being the author's problem. Results
    # are cached against each file's contents, so this is only slow once.
    from .audio import AudioError
    from .sfxbank import build as build_audio
    try:
        build_audio(src, os.path.join(src, "src", "audio"),
                    irx=os.path.join(tc.ps2dev_root() or "", "ps2sdk", "iop",
                                     "irx", "audsrv.irx"))
    except AudioError as exc:
        raise SystemExit(f"ncc: audio: {exc}")

    cc = tc.ps2_cc()
    if not cc:
        raise SystemExit(
            "ncc: no PS2 toolchain." + chr(10) +
            "     Install it with:  sh tools/install-ps2dev.sh" + chr(10) +
            "     Then check it with:  ncc doctor --target ps2")

    make = tc.find_make()
    if not make:
        raise SystemExit(
            "ncc: GNU make not found, and PS2SDK builds with Makefiles." + chr(10) +
            "     winget install ezwinports.make")

    env = tc.ps2_build_env()
    command = [make]
    if os.name == "nt":
        command.append("SHELL=" + env["SHELL"])
    r = subprocess.run(command, cwd=src, env=env, capture_output=True, text=True)
    sys.stdout.write(r.stdout)
    if r.returncode != 0:
        sys.stderr.write(r.stderr)
        raise SystemExit("ncc: build failed.")

    for line in (r.stdout or "").splitlines():
        if "warning:" in line.lower():
            print(f"  {line.strip()}")

    elf = os.path.join(src, "game.elf")
    if not os.path.isfile(elf):
        raise SystemExit("ncc: make succeeded but produced no game.elf")

    size = os.path.getsize(elf)
    print(f"  ok  {elf}  ({size / 1024:.0f} KB)")
    print()
    print("  On a FreeMcBoot console: copy game.elf to a USB stick and launch")
    print("  it from uLaunchELF or OPL. In PCSX2 it needs a PS2 BIOS dumped")
    print("  from your own machine -- there is no OpenBIOS equivalent for PS2.")
    return 0


def build(args):
    src = _resolve(getattr(args, "path", None))

    target = project_meta(src)["target"]
    if os.path.exists(os.path.join(src,"triggers.json")):
        from .viewportdata import load_triggers
        try:load_triggers(src)
        except (OSError,ValueError,KeyError,TypeError) as exc:raise SystemExit(f"ncc: triggers.json -- {exc}")
    if target == "ps2":
        try:
            from .ps2flow import compile_project
            compile_project(src)
        except (ValueError, KeyError, TypeError) as exc:
            raise SystemExit(f"ncc: event-flow.json -- {exc}")
        return _build_ps2(src)
    if target != "ps1":
        # Refusing here, by name, beats letting cmake fail three layers down
        # with a missing compiler.
        t = TARGETS[target]
        raise SystemExit(
            f"ncc: {os.path.basename(src)} targets {t.name}, and the {target} "
            f"backend is not implemented yet." + chr(10) +
            f"     Its renderer shares nothing with the PS1 one -- see M6 in "
            f"docs/ROADMAP.md." + chr(10) +
            f"     What exists today: the hardware profile, the toolchain "
            f"check (ncc doctor --target {target})," + chr(10) +
            f"     and this project's own declaration of what it is.")

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
    if os.path.isfile(script) or os.path.isfile(os.path.join(src, "event-flow.json")):
        gen = os.path.join(src, "src", "nc_script_generated.c")
        try:
            source = open(script, encoding="utf-8").read() if os.path.isfile(script) else ""
            source = eventflow.compose(src, target, source)
            generated = ncscript.compile_source(source)
            with open(gen, "w", encoding="utf-8") as output:
                output.write(generated)
            lines = len(generated.splitlines())
        except (ncscript.ScriptError, ValueError, KeyError, TypeError) as exc:
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
        output = r.stdout + r.stderr
        if "Access is denied" in output:
            print("\nncc: this is the spaces-in-build-path failure. The build dir was\n"
                  f"     {build_dir}\n"
                  "     See docs/KNOWN-ISSUES.md.", file=sys.stderr)
        if "Cannot open or create output image file" in output:
            # Everything compiled and linked; only writing the disc image failed.
            # On Windows that means something else has the file open, and the
            # only thing that ever does is the emulator still running the last
            # build. The mkpsxiso message does not say so.
            print("\nncc: the compile succeeded -- writing the disc image did not.\n"
                  "     Something has game.bin open. Close DuckStation and build\n"
                  "     again; `ncc run` does this for you.", file=sys.stderr)
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

def _close_running_emulator():
    """Close a DuckStation left over from the last run, before rebuilding.

    It holds game.bin open, and mkpsxiso cannot overwrite a file Windows has
    locked -- so the build fails after compiling and linking cleanly, with a
    message about an output image that says nothing about the emulator. Closing
    it first is what makes `ncc run` twice in a row work the way you expect.
    """
    if os.name != "nt":
        return
    for image in ("duckstation-qt-x64-ReleaseLTCG.exe", "duckstation-qt.exe",
                  "duckstation-nogui-x64-ReleaseLTCG.exe"):
        subprocess.run(["taskkill", "/IM", image, "/F"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _run_ps2(src):
    """Launch a PS2 build, or explain why it cannot be launched here.

    PCSX2 needs a PS2 BIOS, and unlike the PS1 there is no open replacement for
    it -- so this cannot be made to work by installing something. Saying so, and
    saying what to do instead, is the useful thing.
    """
    elf = os.path.join(src, "game.elf")
    pcsx2 = tc.find_pcsx2()
    bios = tc.pcsx2_bios()

    if pcsx2 and bios:
        print("  launching PCSX2")
        subprocess.Popen([pcsx2, "-fastboot", "--", elf], cwd=os.path.dirname(elf))
        return 0

    print()
    if not pcsx2:
        print("  PCSX2 is not installed, so there is nothing to run this in here.")
    else:
        print("  PCSX2 is installed but has no BIOS, and it will not boot without")
        print("  one. A PS2 BIOS is copyrighted and has no open replacement the")
        print("  way OpenBIOS covers the PS1 -- dump it from your own console")
        print("  (FreeMcBoot ships a dumper) into:")
        print("    %s" % tc.pcsx2_bios_dir())
    print()
    print("  On hardware, which needs none of that:")
    print("    copy this to a FAT32 USB stick and launch it from uLaunchELF or OPL")
    print("    %s" % elf)
    return 0


def run(args):
    src = _resolve(getattr(args, "path", None))
    if project_meta(src)["target"] == "ps2":
        rc = _build_ps2(src)
        return rc if rc else _run_ps2(src)

    _close_running_emulator()

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
    if project_meta(src)["target"] == "ps2":
        # Remove only generated objects and the linked ELF inside this project.
        root = os.path.realpath(src)
        outputs = [os.path.join(root, "game.elf")]
        for directory, _, files in os.walk(os.path.join(root, "src")):
            outputs.extend(os.path.join(directory, f) for f in files if f.endswith(".o"))
        for output in outputs:
            resolved = os.path.realpath(output)
            if os.path.commonpath([root, resolved]) != root:
                raise SystemExit("ncc: refusing to clean an output outside the project")
        for output in outputs:
            if os.path.isfile(output):
                os.remove(output)
                print(f"Removed {output}")
        return 0
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
