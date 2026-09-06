"""WAV -> PlayStation SPU-ADPCM.

The SPU does not play PCM. It plays a 4-bit ADPCM format in 16-byte blocks, each
holding 28 samples plus a header describing how to reconstruct them. Encoding is
done here so audio needs no extra tool -- the alternative is psxavenc, which is
another binary to install and pin.

Block layout (16 bytes)
-----------------------
    byte 0   (filter << 4) | shift
    byte 1   flags: 1 = loop end, 2 = repeat, 4 = loop start
    2..15    28 samples, two 4-bit nibbles per byte, low nibble first

Decoding is: take the 4-bit value, shift it left by (12 - shift), add a
prediction made from the previous two output samples, clamp to 16 bits. Encoding
is that in reverse, and because the predictor depends on what was actually
decoded, the encoder has to simulate the decoder as it goes -- otherwise error
accumulates and the tail of a sound drifts into noise.

There are five predictor filters. We try every filter and every shift for each
block and keep whichever reproduces the block most accurately: 65 trials per 28
samples, which is nothing at build time and gives noticeably cleaner audio than
the usual heuristic.
"""

import os
import struct
import wave

SAMPLES_PER_BLOCK = 28
BLOCK_BYTES = 16

# Predictor coefficients, scaled by 64.
FILTERS = [(0, 0), (60, 0), (115, -52), (98, -55), (122, -60)]

# SPU RAM is 512 KB and the first 4 KB plus a dummy block are reserved. Being
# strict here is kinder than letting a long sample quietly overwrite another.
SPU_RAM_BYTES = 512 * 1024
SPU_RESERVED = 0x1010
SPU_BUDGET = SPU_RAM_BYTES - SPU_RESERVED

MAX_SAMPLE_RATE = 44100


class AudioError(Exception):
    pass


def _clamp16(v):
    if v > 32767:
        return 32767
    if v < -32768:
        return -32768
    return v


def _encode_block(samples, prev1, prev2, flags):
    """Encode 28 samples, returning (bytes, prev1, prev2).

    Exhaustive over filter and shift. The decoder is simulated inside the loop
    so the predictor state matches what the console will actually have.
    """
    best = None

    for filt, (c0, c1) in enumerate(FILTERS):
        for shift in range(13):
            p1, p2 = prev1, prev2
            nibbles = []
            error = 0

            for s in samples:
                predicted = (p1 * c0 + p2 * c1) >> 6
                diff = s - predicted
                step = 1 << (12 - shift)

                n = int(round(diff / step))
                if n > 7:
                    n = 7
                elif n < -8:
                    n = -8

                decoded = _clamp16((n << (12 - shift)) + predicted)
                error += (decoded - s) ** 2
                nibbles.append(n & 0x0F)
                p2, p1 = p1, decoded

            if best is None or error < best[0]:
                best = (error, filt, shift, nibbles, p1, p2)
            if error == 0:
                break
        if best is not None and best[0] == 0:
            break

    _, filt, shift, nibbles, p1, p2 = best

    out = bytearray(BLOCK_BYTES)
    out[0] = ((filt & 0x0F) << 4) | (shift & 0x0F)
    out[1] = flags
    for i in range(0, SAMPLES_PER_BLOCK, 2):
        out[2 + i // 2] = nibbles[i] | (nibbles[i + 1] << 4)
    return bytes(out), p1, p2


def encode(samples):
    """PCM (list of int16) -> SPU-ADPCM bytes."""
    data = bytearray()
    prev1 = prev2 = 0

    total = len(samples)
    blocks = (total + SAMPLES_PER_BLOCK - 1) // SAMPLES_PER_BLOCK

    for b in range(blocks):
        chunk = list(samples[b * SAMPLES_PER_BLOCK:(b + 1) * SAMPLES_PER_BLOCK])
        while len(chunk) < SAMPLES_PER_BLOCK:
            chunk.append(0)

        # The final block carries "loop end" with the repeat bit clear, which is
        # what makes the SPU stop rather than run on into whatever sample was
        # uploaded after this one.
        flags = 1 if b == blocks - 1 else 0
        block, prev1, prev2 = _encode_block(chunk, prev1, prev2, flags)
        data += block

    return bytes(data)


def read_wav(path, name):
    """Load a WAV as mono int16. Raises AudioError with something actionable."""
    if not os.path.isfile(path):
        raise AudioError(f"sound '{name}': no such file: {path}")

    try:
        with wave.open(path, "rb") as w:
            channels = w.getnchannels()
            width = w.getsampwidth()
            rate = w.getframerate()
            frames = w.readframes(w.getnframes())
    except wave.Error as exc:
        raise AudioError(
            f"sound '{name}': not a readable WAV ({exc}). Export as "
            f"uncompressed PCM WAV -- mp3 and ogg are not supported.")

    if width == 1:
        # 8-bit WAV is unsigned; centre it and scale up.
        samples = [(b - 128) << 8 for b in frames]
    elif width == 2:
        samples = list(struct.unpack("<%dh" % (len(frames) // 2), frames))
    else:
        raise AudioError(
            f"sound '{name}': {width * 8}-bit WAV is not supported. Use 8- or "
            f"16-bit PCM.")

    if channels == 2:
        # Mix to mono: the SPU plays one channel per voice, and a stereo sample
        # would just cost twice the RAM for the same sound.
        samples = [(samples[i] + samples[i + 1]) // 2
                   for i in range(0, len(samples) - 1, 2)]
    elif channels != 1:
        raise AudioError(
            f"sound '{name}': {channels} channels. Use mono or stereo.")

    if rate > MAX_SAMPLE_RATE:
        raise AudioError(
            f"sound '{name}' is {rate} Hz; the SPU tops out at "
            f"{MAX_SAMPLE_RATE} Hz. Resample it down -- 22050 or 11025 is "
            f"typical for this hardware and uses half or a quarter the RAM.")

    if not samples:
        raise AudioError(f"sound '{name}' is empty")

    return samples, rate


def build_chunk(sound_id, adpcm, rate):
    """SND0: the id, the sample rate, then the ADPCM blocks."""
    out = bytearray()
    out += struct.pack("<HHII", sound_id, 0, rate, len(adpcm))
    out += adpcm
    return bytes(out)


def build(sounds, base_dir):
    """Convert every sound in a document. Returns (chunks, name -> id)."""
    chunks = []
    ids = {}
    used = 0

    for sound_id, snd in enumerate(sounds):
        name = snd.get("name") or f"snd{sound_id}"
        rel = snd.get("file")
        if not rel:
            raise AudioError(f"sound '{name}' has no 'file'")
        path = rel if os.path.isabs(rel) else os.path.join(base_dir, rel)

        samples, rate = read_wav(path, name)
        adpcm = encode(samples)

        # SPU DMA moves 64-byte blocks, so that is the real cost of a sample.
        used += (len(adpcm) + 63) & ~63
        if used > SPU_BUDGET:
            seconds = len(samples) / float(rate)
            raise AudioError(
                f"sound '{name}' ({seconds:.1f}s at {rate} Hz) pushes total "
                f"audio to {used // 1024} KB, past the {SPU_BUDGET // 1024} KB "
                f"of usable SPU RAM. Shorten it, or drop the sample rate.")

        chunks.append(build_chunk(sound_id, adpcm, rate))
        ids[name] = sound_id

    return chunks, ids


def describe(samples, rate, adpcm):
    """A one-line summary for build output."""
    return "%.2fs %dHz -> %d KB" % (len(samples) / float(rate), rate,
                                    max(1, len(adpcm) // 1024))
