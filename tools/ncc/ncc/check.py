"""`ncc check` -- what fits, what does not, and how close you are.

The PS1 has hard, small limits, and the failure mode that wastes the most time is
finding out at link time (or worse, as a lock-up on the console) that something
was too big. This runs the same converters the build uses -- so it cannot
disagree with them -- and reports the budgets before anything is compiled.

Everything here answers one of two questions: *why did that not work*, and *how
much room is left*.
"""

import json
import os

from . import audio as audio_mod
from . import ncpkg
from . import ncscript
from . import textures as tex_mod

# Mirrors the runtime caps in templates/_common/include/nc.h. If those change,
# these must too -- which is why they are named the same.
NC_MAX_TEXTURES = 8
NC_MAX_SOUNDS = 16
NC_MAX_MESHES = 64
NC_MAX_SCENES = 16
NC_MAX_OBJECTS = 128
NC_MAX_SPRITES = 64

# The console has 2 MB. The executable, the embedded package and everything the
# runtime allocates all come out of it, so a package past this is worth flagging
# well before it actually fails.
PACKAGE_WARN_BYTES = 512 * 1024


class Report:
    def __init__(self):
        self.lines = []
        self.problems = []      # things that will not build
        self.warnings = []      # things that will build but bite later

    def say(self, text=""):
        self.lines.append(text)

    def problem(self, what, why, fix):
        self.problems.append((what, why, fix))

    def warn(self, what, why, fix):
        self.warnings.append((what, why, fix))

    def ok(self):
        return not self.problems

    def render(self):
        out = list(self.lines)
        if self.problems:
            out.append("")
            out.append("  PROBLEMS -- these stop the build")
            out.append("  " + "-" * 34)
            for what, why, fix in self.problems:
                out.append(f"  [X] {what}")
                out.append(f"      {why}")
                out.append(f"      fix: {fix}")
        if self.warnings:
            out.append("")
            out.append("  WARNINGS -- these build, but watch them")
            out.append("  " + "-" * 38)
            for what, why, fix in self.warnings:
                out.append(f"  [!] {what}")
                out.append(f"      {why}")
                out.append(f"      fix: {fix}")
        if not self.problems and not self.warnings:
            out.append("")
            out.append("  No problems found.")
        return "\n".join(out)


def _bar(used, total, width=22):
    """A little usage meter -- easier to read at a glance than a percentage."""
    if total <= 0:
        return ""
    filled = min(width, int(round(width * used / float(total))))
    pct = int(round(100.0 * used / total))
    return "[%s%s] %d%%" % ("#" * filled, "." * (width - filled), pct)


def check_project(path):
    r = Report()
    name = os.path.basename(os.path.abspath(path))
    r.say()
    r.say(f"  Checking {name}")
    r.say()

    scene_path = os.path.join(path, "scene.json")
    if not os.path.isfile(scene_path):
        r.say("  No scene.json -- this project keeps its geometry in C.")
        _check_script(path, r)
        return r

    try:
        with open(scene_path, encoding="utf-8") as fh:
            doc = json.load(fh)
    except ValueError as exc:
        r.problem("scene.json is not valid JSON", str(exc),
                  "a trailing comma or a missing quote is the usual cause")
        return r

    _check_textures(path, doc, r)
    _check_sounds(path, doc, r)
    _check_meshes(doc, r)
    _check_scenes(doc, r)
    _check_script(path, r)
    _check_package(path, doc, r)
    return r


# ---- textures -----------------------------------------------------------

def _check_textures(path, doc, r):
    texs = doc.get("textures", [])
    r.say(f"  TEXTURES   {len(texs)} / {NC_MAX_TEXTURES} slots")

    if len(texs) > NC_MAX_TEXTURES:
        r.problem(
            f"{len(texs)} textures, but there are only {NC_MAX_TEXTURES} slots",
            "each texture needs its own page in the PS1's 1 MB of VRAM, and the "
            "framebuffers already take a third of it",
            "combine several images into one sheet and use uvs to pick regions")

    for t in texs:
        tname = t.get("name", "?")
        rel = t.get("file", "")
        full = rel if os.path.isabs(rel) else os.path.join(path, rel)
        try:
            idx, pal, w, h = tex_mod.convert(full, tname)
        except tex_mod.TextureError as exc:
            r.problem(f"texture '{tname}'", str(exc),
                      "see docs/LIMITS.md for the texture rules")
            continue

        vram_kb = (w // 2 * h * 2) // 1024
        transparent = " (has transparency)" if pal[0] == 0 else ""
        r.say(f"    {tname:<14} {w}x{h}  ~{max(1, vram_kb)} KB VRAM{transparent}")

        if w * h > 128 * 128 and len(texs) > 4:
            r.warn(f"texture '{tname}' is large ({w}x{h})",
                   "several textures this size will crowd VRAM",
                   "128x128 is a comfortable size for most PS1 art")


# ---- sounds -------------------------------------------------------------

def _check_sounds(path, doc, r):
    sounds = doc.get("sounds", [])
    r.say()
    r.say(f"  SOUNDS     {len(sounds)} / {NC_MAX_SOUNDS}")

    if len(sounds) > NC_MAX_SOUNDS:
        r.problem(
            f"{len(sounds)} sounds, but only {NC_MAX_SOUNDS} fit",
            "the runtime keeps a fixed table of sample addresses",
            "merge short effects, or raise NC_MAX_SOUNDS in include/nc.h")

    total = 0
    for s in sounds:
        sname = s.get("name", "?")
        rel = s.get("file", "")
        full = rel if os.path.isabs(rel) else os.path.join(path, rel)
        try:
            samples, rate = audio_mod.read_wav(full, sname)
        except audio_mod.AudioError as exc:
            r.problem(f"sound '{sname}'", str(exc),
                      "export as mono 16-bit PCM WAV at 22050 Hz or lower")
            continue

        adpcm = audio_mod.encode(samples)
        size = (len(adpcm) + 63) & ~63
        total += size
        secs = len(samples) / float(rate)
        r.say(f"    {sname:<14} {secs:>5.2f}s  {rate} Hz  {max(1, size // 1024)} KB")

        if secs > 4.0:
            r.warn(f"sound '{sname}' is {secs:.1f}s long",
                   "long samples eat the SPU's 512 KB quickly; it is meant for "
                   "effects, not music",
                   "shorten it, or drop to 11025 Hz to halve the cost")

    if sounds:
        budget = audio_mod.SPU_BUDGET
        r.say(f"    {'SPU RAM':<14} {total // 1024} KB / {budget // 1024} KB  "
              f"{_bar(total, budget)}")
        if total > budget:
            r.problem(
                f"audio needs {total // 1024} KB but the SPU has "
                f"{budget // 1024} KB",
                "samples live in the SPU's own memory, separate from the 2 MB "
                "of main RAM",
                "shorten sounds or lower their sample rate")


# ---- geometry -----------------------------------------------------------

def _check_meshes(doc, r):
    meshes = doc.get("meshes", [])
    r.say()
    r.say(f"  MESHES     {len(meshes)} / {NC_MAX_MESHES}")

    if len(meshes) > NC_MAX_MESHES:
        r.problem(f"{len(meshes)} meshes, but only {NC_MAX_MESHES} fit",
                  "the runtime keeps a fixed mesh table",
                  "reuse meshes between objects, or raise NC_MAX_MESHES")

    total_quads = 0
    for m in meshes:
        verts = len(m.get("verts", []))
        quads = len(m.get("quads", []))
        total_quads += quads
        mname = m.get("name", "?")
        tex = m.get("texture")
        r.say(f"    {mname:<14} {verts:>4} verts  {quads:>4} quads"
              + (f"  tex:{tex}" if tex else ""))
        if verts > 256:
            r.warn(f"mesh '{mname}' has {verts} vertices",
                   "the GTE transforms these one at a time; past a few hundred "
                   "per model the frame rate suffers",
                   "simplify the model -- PS1 characters were typically "
                   "150-300 vertices")

    if total_quads > 900:
        r.warn(f"{total_quads} quads across all meshes",
               "drawing much past ~900 per frame will not hold 30 fps",
               "reduce detail, or make sure they are not all on screen at once")


def _check_scenes(doc, r):
    scenes = doc.get("scenes") or [doc]
    r.say()
    r.say(f"  SCENES     {len(scenes)} / {NC_MAX_SCENES}")

    if len(scenes) > NC_MAX_SCENES:
        r.problem(f"{len(scenes)} scenes, but only {NC_MAX_SCENES} fit",
                  "the runtime keeps a fixed scene table",
                  "combine scenes, or raise NC_MAX_SCENES in include/nc.h")

    for i, sc in enumerate(scenes):
        objs = len(sc.get("instances", []))
        sprs = len(sc.get("sprites", []))
        label = sc.get("name", "scene %d" % i)
        r.say(f"    {label:<14} {objs:>3} objects  {sprs:>3} sprites")

        if objs > NC_MAX_OBJECTS:
            r.problem(f"scene '{label}' has {objs} objects, over the "
                      f"{NC_MAX_OBJECTS} limit",
                      "objects are copied into a fixed array when the scene "
                      "loads; the extras are silently dropped",
                      "split the scene, or raise NC_MAX_OBJECTS in include/nc.h")
        if sprs > NC_MAX_SPRITES:
            r.problem(f"scene '{label}' has {sprs} sprites, over the "
                      f"{NC_MAX_SPRITES} limit",
                      "sprites are copied into a fixed array when the scene "
                      "loads; the extras are silently dropped",
                      "split the scene, or raise NC_MAX_SPRITES in include/nc.h")


# ---- script -------------------------------------------------------------

def _check_script(path, r):
    script = os.path.join(path, "script.ncs")
    r.say()
    if not os.path.isfile(script):
        r.say("  SCRIPT     none (logic is in src/main.c)")
        return

    try:
        with open(script, encoding="utf-8") as fh:
            src = fh.read()
        generated = ncscript.compile_source(src, "script.ncs")
        r.say(f"  SCRIPT     ok, {len(generated.splitlines())} lines of C")
    except ncscript.ScriptError as exc:
        r.say("  SCRIPT     FAILED")
        r.problem(f"script.ncs {exc}", "the script could not be translated to C",
                  "see docs/SCRIPTING.md for what the language supports")


# ---- package ------------------------------------------------------------

def _check_package(path, doc, r):
    r.say()
    try:
        data = ncpkg.pack(doc, path)
    except (ncpkg.NcpkgError, ncpkg.TextureError, ncpkg.AudioError) as exc:
        r.problem("the package could not be built", str(exc),
                  "fix the item named above and check again")
        return

    kb = len(data) // 1024
    r.say(f"  PACKAGE    {len(data)} bytes ({kb} KB) embedded in the executable")
    if len(data) > PACKAGE_WARN_BYTES:
        r.warn(f"the package is {kb} KB",
               "it is embedded in the executable, and the console only has "
               "2 MB for everything",
               "streaming from the disc is not implemented yet, so keep it well "
               "under 1 MB")


def check_ps2(path):
    """What can honestly be said about a PS2 project today.

    The PS1 checker knows every budget because the PS1 runtime owns every
    resource. The PS2 runtime does not exist yet, so there is nothing to be
    authoritative about beyond the executable itself -- and inventing budgets
    for a renderer nobody has written would be worse than saying so.
    """
    from . import build as build_mod
    from .targets import TARGETS

    vn_path = os.path.join(path, "vn.json")
    if os.path.isfile(vn_path):
        from .vn import compile_content
        try:
            compile_content(path)
        except (OSError, ValueError) as exc:
            print(f"VN cannot export: {exc}")
            return 1
        print("VN references/font/texture limits passed. Budget excludes stack and runtime allocations.")
        return 0

    t = TARGETS["ps2"]
    name = os.path.basename(path)
    elf = os.path.join(path, "game.elf")

    print()
    print("  Checking %s  [PlayStation 2]" % name)
    print()
    print("  HARDWARE   %dx%d, %d MB RAM, %d MB VRAM, FPU"
          % (t.width, t.height, t.ram_bytes // (1024 * 1024),
             t.vram_bytes // (1024 * 1024)))

    if os.path.isfile(elf):
        size = os.path.getsize(elf)
        share = size * 100.0 / t.ram_bytes
        print("  EXECUTABLE %d bytes (%.0f KB), %.1f%% of main RAM"
              % (size, size / 1024.0, share))
    else:
        print("  EXECUTABLE not built yet -- ncc build %s" % name)

    print()
    print("  There are no asset budgets to report: the NC runtime is PS1-only")
    print("  so far, and a PS2 project owns its own main.c. See M6 in")
    print("  docs/ROADMAP.md for what that milestone actually involves.")
    print()
    return 0


def run(args):
    path = os.path.abspath(getattr(args, "path", ".") or ".")

    from . import build as build_mod
    if os.path.isfile(os.path.join(path, build_mod.PROJECT_FILE)):
        if build_mod.project_meta(path)["target"] == "ps2":
            return check_ps2(path)

    if not os.path.isfile(os.path.join(path, "CMakeLists.txt")):
        raise SystemExit(f"ncc: {path} is not a Neon Coffee project")

    report = check_project(path)
    print(report.render())
    print()
    return 0 if report.ok() else 1
