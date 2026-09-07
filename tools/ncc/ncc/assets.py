"""Adding art, sound and music to a project without editing JSON by hand.

Every asset here is a two-part act: a file has to land somewhere in the project
*and* `scene.json` has to name it. Doing that by hand is not hard, but it is
exactly the kind of chore where the file arrives and the JSON edit is forgotten,
and the symptom -- a texture that silently is not there -- costs far more than
the edit saved.

So this does both, and refuses up front rather than at build time. A 512x512 PNG
is going to be rejected by the packer either way; being told when you add it,
naming the limit and the reason, is worth more than being told twenty minutes
later in the middle of a build log.
"""

import json
import os
import shutil

from . import audio as audio_mod
from . import textures as tex_mod

KINDS = ("texture", "sound", "music")

# Where each kind lives inside a project, and what the packer calls the list.
LAYOUT = {
    "texture": ("textures", "textures", (".png",)),
    "sound":   ("sounds", "sounds", (".wav",)),
    "music":   ("music", "music", (".wav",)),
}


class AssetError(Exception):
    pass


def _scene_path(project):
    p = os.path.join(project, "scene.json")
    if not os.path.isfile(p):
        raise AssetError(
            "this project has no scene.json, so there is nothing to add an "
            "asset to.\n     Its content is in C -- see docs/GETTING-STARTED.md.")
    return p


def _load(project):
    with open(_scene_path(project), encoding="utf-8") as fh:
        return json.load(fh)


def _save(project, doc):
    # Two spaces and a trailing newline, matching what the templates ship, so
    # adding an asset does not rewrite the whole file in a diff.
    with open(_scene_path(project), "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2)
        fh.write("\n")


def _clean_name(path):
    base = os.path.splitext(os.path.basename(path))[0]
    out = "".join(c if (c.isalnum() or c == "_") else "_" for c in base)
    return out.lower() or "asset"


def _unique(name, taken):
    if name not in taken:
        return name
    n = 2
    while "%s_%d" % (name, n) in taken:
        n += 1
    return "%s_%d" % (name, n)


def _validate(kind, src, doc):
    """Refuse now, with the reason, rather than at build time."""
    if kind == "texture":
        if len(doc.get("textures", [])) >= tex_mod.MAX_SLOTS:
            raise AssetError(
                "this project already uses all %d texture slots. Each one needs "
                "its own\n     page in VRAM. Combine images into a sheet and "
                "select them with u/v." % tex_mod.MAX_SLOTS)
        # convert() does the real checking -- size, even width, colour depth --
        # and its messages already say what to do about each failure.
        tex_mod.convert(src, os.path.basename(src))

    elif kind == "sound":
        from .check import NC_MAX_SOUNDS
        if len(doc.get("sounds", [])) >= NC_MAX_SOUNDS:
            raise AssetError(
                "this project already has %d sounds, which is the size of the "
                "runtime's sample table." % NC_MAX_SOUNDS)
        # Reading it now is the check: read_wav rejects anything the packer
        # would reject later, and says what to export instead.
        audio_mod.read_wav(src, os.path.basename(src))

    elif kind == "music":
        # Red Book is a fixed format; a track that is not 44100 stereo will be
        # rejected by the disc builder, so check it here where it can be fixed.
        import wave
        try:
            with wave.open(src, "rb") as w:
                rate, channels, width = (w.getframerate(), w.getnchannels(),
                                         w.getsampwidth())
        except (wave.Error, OSError) as exc:
            raise AssetError("not a readable WAV (%s). Export uncompressed PCM."
                             % exc)
        if rate != 44100 or channels != 2 or width != 2:
            raise AssetError(
                "music has to be 44100 Hz, 16-bit, stereo. Red Book CD audio is "
                "a fixed format\n     and the drive streams it without decoding, "
                "so there is nothing to convert it with\n     on the console. "
                "This file is %d Hz, %d-bit, %d channel(s)."
                % (rate, width * 8, channels))


def add(project, kind, src, name=None):
    """Copy an asset into a project and register it in scene.json.

    Returns (name, relative path) so the caller can say what it did.
    """
    if kind not in LAYOUT:
        raise AssetError("unknown asset kind '%s'. One of: %s"
                         % (kind, ", ".join(KINDS)))
    if not os.path.isfile(src):
        raise AssetError("no such file: %s" % src)

    folder, key, exts = LAYOUT[kind]
    ext = os.path.splitext(src)[1].lower()
    if ext not in exts:
        raise AssetError("a %s has to be %s; this is %s"
                         % (kind, " or ".join(exts), ext or "extensionless"))

    doc = _load(project)
    doc.setdefault(key, [])
    _validate(kind, src, doc)

    dest_dir = os.path.join(project, folder)
    os.makedirs(dest_dir, exist_ok=True)

    if kind == "music":
        # Music is a bare list of paths; there is nothing to name.
        rel = "%s/%s" % (folder, os.path.basename(src))
        dest = os.path.join(project, rel.replace("/", os.sep))
        if os.path.abspath(src) != os.path.abspath(dest):
            shutil.copy2(src, dest)
        if rel not in doc[key]:
            doc[key].append(rel)
        _save(project, doc)
        return (os.path.basename(src), rel)

    taken = {e.get("name") for e in doc[key] if isinstance(e, dict)}
    final = _unique(name or _clean_name(src), taken)
    rel = "%s/%s%s" % (folder, final, ext)
    dest = os.path.join(project, rel.replace("/", os.sep))
    if os.path.abspath(src) != os.path.abspath(dest):
        shutil.copy2(src, dest)

    doc[key].append({"name": final, "file": rel})
    _save(project, doc)
    return (final, rel)


def listing(project):
    """What a project already has, for reporting."""
    doc = _load(project)
    return {
        "textures": [e.get("name", "?") for e in doc.get("textures", [])],
        "sounds": [e.get("name", "?") for e in doc.get("sounds", [])],
        "music": list(doc.get("music", [])),
    }


def run(args):
    """`ncc add <kind> <file> [project]`."""
    project = os.path.abspath(getattr(args, "path", ".") or ".")
    kind = args.kind
    try:
        name, rel = add(project, kind, args.file, getattr(args, "name", None))
    except AssetError as exc:
        raise SystemExit("ncc: %s" % exc)
    except (tex_mod.TextureError, audio_mod.AudioError) as exc:
        raise SystemExit("ncc: %s" % exc)

    print("Added %s '%s'" % (kind, name))
    print("  %s" % rel)
    if kind == "texture":
        print("  Use it from a sprite or mesh in scene.json:  \"texture\": \"%s\""
              % name)
    elif kind == "sound":
        got = listing(project)["sounds"]
        print("  Play it from a script:  play_sound(%d)" % (len(got) - 1))
    else:
        got = listing(project)["music"]
        # Track 1 is the game data, so the first song is track 2.
        print("  Play it from a script:  play_music(%d)" % (len(got) + 1))
    print()
    print("  Rebuild to pick it up:  ncc build %s" % os.path.basename(project))
    return 0
