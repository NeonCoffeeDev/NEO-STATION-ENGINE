"""Audio banks: a folder of sound files becomes something the PS2 can play.

The rule this follows is that adding a sound should mean putting a file in a
folder. Everything after that -- bit depth, channel count, sample rate, the
ADPCM encoding, the budget -- is the engine's problem, not the author's.

    <project>/audio/sfx/*.wav      one voice each, resident in SPU2 RAM
    <project>/audio/music/*.ogg    streamed, one at a time

Import normalises: whatever comes in is written back out as 16-bit mono at the
project's sample rate. The pack that prompted this was 24-bit 44.1k stereo and
60 MB, which is 12x what the console will ever hear, and keeping the original
in the project would mean carrying that forever for no audible gain.

Sounds are ordered by filename and that order is the index the game uses, so a
build is reproducible and a sound's number does not change because a directory
listing came back differently.

Two files are generated. The bytes go into .bin and are pulled in with .incbin
from a .S, because a megabyte of ADPCM written as a C array is thirty megabytes
of text for the compiler to parse. The names, offsets and sizes go into a header.
"""

import hashlib
import json
import os
import re
import struct
import wave
from pathlib import Path

import numpy as np

from .audio import AudioError
from . import sound

SFX_DIR = "audio/sfx"
MUSIC_DIR = "audio/music"

# SPU2 has 2 MB of local RAM and audsrv keeps its streaming ring buffer in there
# too, so this is what is safely available for resident samples.
SPU2_BUDGET = 1700 * 1024


def _cache_dir(project):
    path = Path(project) / ".ncc-cache" / "audio"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _cached(project, source, rate, encode):
    """ADPCM for this file at this rate, encoding only when something changed.

    Encoding the whole pack is a minute or two. Doing that on every build would
    make the audio the slowest part of a project that otherwise compiles in
    seconds, so the result is kept against a hash of the file's own bytes.
    """
    digest = hashlib.sha1()
    digest.update(Path(source).read_bytes())
    digest.update(b"|%d|v1" % rate)
    target = _cache_dir(project) / (digest.hexdigest() + ".adp")
    if target.exists():
        return target.read_bytes(), True
    data = encode()
    target.write_bytes(data)
    return data, False


def family_of(name):
    """`Ocean Crystal (12)` -> `Ocean Crystal`. Numbered variations group up."""
    return re.sub(r"[ _-]*[\(\[]?\d+[\)\]]?$", "", Path(name).stem).strip() or "sound"


def _write_wav(path, data, rate):
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(np.clip(np.rint(data * 32767.0), -32768, 32767)
                           .astype("<i2").tobytes())


def import_sounds(sources, project, rate=sound.SFX_RATE, do_trim=True):
    """Bring sound files into a project, normalised to 16-bit mono at `rate`."""
    target = Path(project) / SFX_DIR
    target.mkdir(parents=True, exist_ok=True)
    report = []
    for source in sorted(sources, key=lambda p: str(p).lower()):
        source = Path(source)
        data, source_rate = sound.load(str(source))
        before = len(data) / float(source_rate)
        if do_trim:
            data = sound.trim(data)
        data = sound.resample(data, source_rate, rate)
        destination = target / (source.stem + ".wav")
        _write_wav(destination, data, rate)
        report.append((destination.name, before, len(data) / float(rate)))
    return report


def import_music(sources, project):
    """Music is kept in its original compressed form; it is decoded at build."""
    target = Path(project) / MUSIC_DIR
    target.mkdir(parents=True, exist_ok=True)
    names = []
    for source in sorted(sources, key=lambda p: str(p).lower()):
        source = Path(source)
        destination = target / source.name
        if source.resolve() != destination.resolve():
            destination.write_bytes(source.read_bytes())
        names.append(destination.name)
    return names


def _title(stem):
    """A filename turned into something printable on a 32-column screen."""
    text = re.sub(r"[_-]+", " ", stem).strip().upper()
    text = re.sub(r"\s+", " ", text)
    return text[:24]


def build(project, out_dir, sfx_rate=sound.SFX_RATE, music_rate=sound.MUSIC_RATE,
          log=print, irx=None):
    """Encode everything in the project's audio folders into a linked bank.

    Returns a summary dict, or None when the project has no audio at all.
    """
    root = Path(project)
    sfx_files = sorted((root / SFX_DIR).glob("*.*")) if (root / SFX_DIR).is_dir() else []
    sfx_files = [p for p in sfx_files if p.suffix.lower() in sound.READABLE]
    music_files = sorted((root / MUSIC_DIR).glob("*.*")) if (root / MUSIC_DIR).is_dir() else []
    music_files = [p for p in music_files if p.suffix.lower() in sound.READABLE]
    if not sfx_files and not music_files:
        return None

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    # ---- sound effects, resident ------------------------------------
    blob = bytearray()
    entries = []
    reused = 0
    for path in sfx_files:
        adpcm, hit = _cached(project, path, sfx_rate,
                             lambda p=path: sound.convert(str(p), sfx_rate,
                                                          p.name, do_trim=False)[0])
        reused += 1 if hit else 0
        # The SPU addresses samples in 64-byte units, so that is the real cost
        # and the real alignment.
        while len(blob) % 64:
            blob.append(0)
        entries.append((path.stem, len(blob), len(adpcm)))
        blob += adpcm

    if len(blob) > SPU2_BUDGET:
        raise AudioError(
            "sound effects total %d KiB of ADPCM, past the %d KiB that fits in "
            "SPU2 RAM alongside the streaming buffer. Lower the sample rate "
            "(currently %d Hz -- halving it halves this), shorten the longest "
            "sounds, or move some out of %s."
            % (len(blob) // 1024, SPU2_BUDGET // 1024, sfx_rate, SFX_DIR))
    (out / "sfx.bin").write_bytes(bytes(blob))

    # ---- music, streamed --------------------------------------------
    tracks = []
    for index, path in enumerate(music_files):
        adpcm, hit = _cached(project, path, music_rate,
                             lambda p=path: sound.convert(str(p), music_rate,
                                                          p.name, do_trim=False)[0])
        reused += 1 if hit else 0
        (out / ("music_%d.bin" % index)).write_bytes(adpcm)
        seconds = len(adpcm) / 16.0 * 28.0 / music_rate
        tracks.append((_title(path.stem), len(adpcm), seconds))

    # ---- generated sources ------------------------------------------
    families = []
    for name, _, _ in entries:
        group = family_of(name)
        if families and families[-1][0] == group:
            families[-1][2] += 1
        else:
            families.append([group, len(families) and sum(f[2] for f in families), 1])
    # `first` above is only correct when families are contiguous; recompute.
    position = 0
    for family in families:
        family[1] = position
        position += family[2]

    # incbin resolves against the assembler's working directory, and make runs
    # from the project root -- not from wherever the .S happens to live. An
    # `audio/sfx.bin` here would point at the *source* folder and fail to
    # assemble, so the path is spelled out from the root.
    here = os.path.relpath(out.resolve(), root.resolve()).replace(os.sep, "/")
    asm = ['/* Generated by ncc from %s and %s -- do not edit. */' % (SFX_DIR, MUSIC_DIR),
           '\t.section .data', '\t.align 6',
           '\t.globl nc_sfx_bin', 'nc_sfx_bin:', '\t.incbin "%s/sfx.bin"' % here]
    for index in range(len(tracks)):
        asm += ['\t.align 6', '\t.globl nc_music_%d_bin' % index,
                'nc_music_%d_bin:' % index,
                '\t.incbin "%s/music_%d.bin"' % (here, index)]
    # audsrv has to reach the IOP somehow, and an ELF launched from a USB stick
    # has no working directory to load it from. Carrying it inside the
    # executable is the only arrangement that does not depend on where the game
    # was started from.
    if irx and os.path.isfile(irx):
        (out / "audsrv.irx").write_bytes(Path(irx).read_bytes())
        asm += ['\t.align 6', '\t.globl nc_audsrv_irx', 'nc_audsrv_irx:',
                '\t.incbin "%s/audsrv.irx"' % here,
                '\t.globl nc_audsrv_irx_end', 'nc_audsrv_irx_end:']
    (out / "audio_data.S").write_text("\n".join(asm) + "\n", encoding="utf-8")

    header = ['/* Generated by ncc. Sound indices follow filename order. */',
              '#ifndef NC_AUDIO_DATA_H', '#define NC_AUDIO_DATA_H', '',
              'typedef struct { const char *name; int offset, size; } NCSound;',
              'typedef struct { const char *name; int first, count; } NCFamily;',
              'typedef struct { const char *name; unsigned char *data; int size; } NCTrack;',
              '',
              '#define NC_SFX_RATE %d' % sfx_rate,
              '#define NC_MUSIC_RATE %d' % music_rate,
              '#define NC_SFX_COUNT %d' % len(entries),
              '#define NC_FAMILY_COUNT %d' % len(families),
              '#define NC_MUSIC_COUNT %d' % len(tracks),
              '',
              'extern unsigned char nc_sfx_bin[];']
    for index in range(len(tracks)):
        header.append('extern unsigned char nc_music_%d_bin[];' % index)
    header += ['', 'static const NCSound nc_sfx[] = {']
    header += ['    {"%s", %d, %d},' % (_title(name), offset, size)
               for name, offset, size in entries] or ['    {"", 0, 0},']
    header += ['};', '', 'static const NCFamily nc_families[] = {']
    header += ['    {"%s", %d, %d},' % (_title(name), first, count)
               for name, first, count in families] or ['    {"", 0, 0},']
    header += ['};', '', 'static const NCTrack nc_music[] = {']
    header += ['    {"%s", nc_music_%d_bin, %d},' % (name, index, size)
               for index, (name, size, _) in enumerate(tracks)] or ['    {"", 0, 0},']
    header += ['};', '', '#endif']
    (out / "audio_data.h").write_text("\n".join(header) + "\n", encoding="utf-8")

    summary = {"sfx": len(entries), "sfx_bytes": len(blob), "families": len(families),
               "tracks": len(tracks),
               "music_bytes": sum(size for _, size, _ in tracks), "reused": reused}
    log("  audio: %d effects in %d families, %d KiB of SPU2 RAM (%d KiB free); "
        "%d tracks, %d KiB streamed%s"
        % (summary["sfx"], summary["families"], len(blob) // 1024,
           (SPU2_BUDGET - len(blob)) // 1024, summary["tracks"],
           summary["music_bytes"] // 1024,
           "" if not reused else "; %d cached" % reused))
    return summary
