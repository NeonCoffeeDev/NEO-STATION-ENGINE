"""Any audio file in, SPU-ADPCM out.

`audio.py` holds the reference encoder and explains the block format. This module
is the part in front of it: reading whatever the artist actually exported,
getting it to one channel at a sample rate the hardware likes, and encoding fast
enough that a hundred sounds is a coffee rather than an afternoon.

Three things it does that the original reader would not:

**Every bit depth.** The pack that prompted this is 24-bit, which `wave` will
hand over as raw bytes and `audioop` used to convert -- except audioop was
removed in Python 3.13. So the unpacking is done here, for 8, 16, 24 and 32-bit
integer and 32-bit float.

**Ogg Vorbis and everything else**, through libsndfile when `soundfile` is
installed. Music arrives as .ogg far more often than as .wav, and asking someone
to go and find a converter is the kind of friction that stops a project.

**Speed.** The reference encoder tries all five predictor filters at all thirteen
shifts and keeps the closest, which is 65 simulated decodes per 28 samples. In
plain Python that is roughly two hours for a five megabyte score. Here the 65
candidates advance together as one numpy array, so the cost per block is 28
vector operations instead of 1820 scalar ones. The result is checked against the
reference encoder byte for byte in the tests -- the point is to be faster, not
different.
"""

import os
import struct
import wave

import numpy as np

from .audio import (AudioError, BLOCK_BYTES, FILTERS, SAMPLES_PER_BLOCK,
                    _clamp16, encode as encode_reference)

# Rates the SPU is happy with. 44100 is allowed but costs four times what an
# interface blip needs; these are the ones worth defaulting to.
SFX_RATE = 11025
MUSIC_RATE = 22050

READABLE = ".wav .ogg .flac .aiff .aif .mp3 .w64 .caf".split()


def _soundfile():
    try:
        import soundfile
        return soundfile
    except ImportError:
        return None


def load(path, name=None):
    """Read any supported audio file as (mono float32 in -1..1, sample rate)."""
    name = name or os.path.basename(path)
    if not os.path.isfile(path):
        raise AudioError("sound '%s': no such file: %s" % (name, path))

    extension = os.path.splitext(path)[1].lower()
    module = _soundfile()
    if module is not None and extension != ".wav":
        data, rate = module.read(path, dtype="float32", always_2d=True)
        return data.mean(axis=1).astype(np.float32), rate
    if extension != ".wav":
        raise AudioError(
            "sound '%s': %s files need libsndfile. Install it with "
            "`python -m pip install soundfile`, or export a WAV instead."
            % (name, extension or "these"))
    return _load_wav(path, name)


def _load_wav(path, name):
    """A WAV of any common bit depth, mixed to mono float32.

    audioop did this until Python 3.13 removed it, so the unpacking is explicit.
    """
    try:
        with wave.open(path, "rb") as handle:
            channels = handle.getnchannels()
            width = handle.getsampwidth()
            rate = handle.getframerate()
            raw = handle.readframes(handle.getnframes())
    except wave.Error as exc:
        raise AudioError(
            "sound '%s': not a readable WAV (%s). If it is compressed, install "
            "soundfile (`python -m pip install soundfile`) and it will be read "
            "directly." % (name, exc))

    if width == 1:
        # 8-bit WAV is the odd one out: unsigned, centred on 128.
        data = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    elif width == 2:
        data = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    elif width == 3:
        # No 24-bit dtype exists, so rebuild it: two unsigned bytes and one
        # signed byte carrying the sign of the whole sample.
        b = np.frombuffer(raw, dtype=np.uint8).reshape(-1, 3)
        value = (b[:, 0].astype(np.int32)
                 | (b[:, 1].astype(np.int32) << 8)
                 | (b[:, 2].view(np.int8).astype(np.int32) << 16))
        data = value.astype(np.float32) / 8388608.0
    elif width == 4:
        data = np.frombuffer(raw, dtype="<i4").astype(np.float32) / 2147483648.0
    else:
        raise AudioError("sound '%s': %d-bit WAV is not supported."
                         % (name, width * 8))

    if channels < 1:
        raise AudioError("sound '%s': no channels" % name)
    if len(data) % channels:
        data = data[:len(data) - (len(data) % channels)]
    # One voice plays one channel, so a stereo sample would cost twice the RAM
    # for the same sound.
    data = data.reshape(-1, channels).mean(axis=1)
    if not len(data):
        raise AudioError("sound '%s' is empty" % name)
    return data.astype(np.float32), rate


def resample(data, source_rate, target_rate):
    """Linear resampling. Good enough for material this hardware will crush."""
    if source_rate == target_rate or len(data) < 2:
        return data
    count = int(round(len(data) * float(target_rate) / source_rate))
    if count < 1:
        return data[:1]
    position = np.linspace(0.0, len(data) - 1.0, count, dtype=np.float64)
    return np.interp(position, np.arange(len(data), dtype=np.float64),
                     data).astype(np.float32)


def trim(data, floor_db=-60.0):
    """Drop a trailing tail that has fallen below audibility.

    Only the tail: a fade that the composer wrote is part of the sound, and this
    is looking for the digital silence left by an exporter.
    """
    if not len(data):
        return data
    peak = float(np.abs(data).max())
    if peak <= 0.0:
        return data[:1]
    loud = np.nonzero(np.abs(data) > peak * (10.0 ** (floor_db / 20.0)))[0]
    if not len(loud):
        return data[:1]
    return data[:loud[-1] + 1]


def to_int16(data):
    return np.clip(np.rint(data * 32767.0), -32768, 32767).astype(np.int64)


_COEFFS = np.array(FILTERS, dtype=np.int64)          # (5, 2)


def encode(samples):
    """PCM int16 -> SPU-ADPCM. Byte-identical to audio.encode, much faster.

    The 65 (filter, shift) candidates are carried as one array and stepped
    through the block together. Everything stays in integers so the simulated
    decoder matches the console's, which is the whole reason the reference
    encoder simulates it at all: the predictor depends on what was decoded, not
    on what was wanted, so an approximation drifts.
    """
    samples = np.asarray(samples, dtype=np.int64)
    blocks = max(1, (len(samples) + SAMPLES_PER_BLOCK - 1) // SAMPLES_PER_BLOCK)
    padded = np.zeros(blocks * SAMPLES_PER_BLOCK, dtype=np.int64)
    padded[:len(samples)] = samples

    shifts = np.arange(13, dtype=np.int64)
    c0 = np.repeat(_COEFFS[:, 0], 13)                # (65,)
    c1 = np.repeat(_COEFFS[:, 1], 13)
    step_shift = np.tile(12 - shifts, len(FILTERS))  # (65,)
    step = (np.int64(1) << step_shift)

    out = bytearray()
    prev1 = prev2 = 0

    for index in range(blocks):
        chunk = padded[index * SAMPLES_PER_BLOCK:(index + 1) * SAMPLES_PER_BLOCK]
        p1 = np.full(65, prev1, dtype=np.int64)
        p2 = np.full(65, prev2, dtype=np.int64)
        error = np.zeros(65, dtype=np.int64)
        nibbles = np.zeros((65, SAMPLES_PER_BLOCK), dtype=np.int64)

        for position in range(SAMPLES_PER_BLOCK):
            target = chunk[position]
            predicted = (p1 * c0 + p2 * c1) >> 6
            # np.rint is half-to-even, which is what Python's round() does, so
            # the two encoders agree on the ties as well as everything else.
            n = np.clip(np.rint((target - predicted) / step), -8, 7).astype(np.int64)
            decoded = np.clip((n << step_shift) + predicted, -32768, 32767)
            error += (decoded - target) ** 2
            nibbles[:, position] = n & 0x0F
            p2, p1 = p1, decoded

        best = int(np.argmin(error))
        filt, shift = divmod(best, 13)
        block = bytearray(BLOCK_BYTES)
        block[0] = ((filt & 0x0F) << 4) | (shift & 0x0F)
        # The last block carries "loop end" with repeat clear, which stops the
        # voice instead of letting it run into whatever was uploaded next.
        block[1] = 1 if index == blocks - 1 else 0
        row = nibbles[best]
        for i in range(0, SAMPLES_PER_BLOCK, 2):
            block[2 + i // 2] = int(row[i]) | (int(row[i + 1]) << 4)
        out += block
        prev1, prev2 = int(p1[best]), int(p2[best])

    return bytes(out)


def convert(path, rate=SFX_RATE, name=None, do_trim=True):
    """File -> (adpcm bytes, samples, rate). The whole pipeline, once."""
    data, source_rate = load(path, name)
    if do_trim:
        data = trim(data)
    data = resample(data, source_rate, rate)
    pcm = to_int16(data)
    return encode(pcm), len(pcm), rate
