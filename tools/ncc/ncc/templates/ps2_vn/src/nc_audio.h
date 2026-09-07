/* Software mixer over one audsrv PCM stream.
 *
 * audsrv offers two ways to make noise: a PCM stream, and ADPCM samples uploaded
 * into SPU2 RAM and played on its voices. The second is the obvious choice for
 * sound effects and it is not the one used here.
 *
 * ps2sdk's own encoder writes a container this code would have to match exactly,
 * and it does not survive inspection: no block carries the SPU's loop-end flag,
 * and the first sixteen bytes change with the audio rather than with the sample
 * rate. Guessing wrong produces either silence or noise, and neither can be told
 * apart from a photograph of a television. Mixing here removes the question.
 *
 * What it buys, beyond certainty:
 *
 *   - Samples live in EE RAM, which is 32 MB, instead of SPU2's 2 MB. The
 *     budget that made 95 sounds a tight fit stops being a constraint.
 *   - Music and effects share one path, so there is one thing to get right.
 *   - Per-voice volume is a multiply in a loop we already own, which is what
 *     the options screen needs.
 *
 * What it costs is EE time: decoding ADPCM and mixing five voices at 22050 Hz
 * is a few hundred thousand operations a second on a 294 MHz machine, against a
 * frame budget of about five million. It does not show.
 *
 * Effects are encoded at half the output rate, which is deliberate -- 22050 is
 * exactly twice 11025, so upsampling is emitting each sample twice rather than
 * an interpolation with a phase accumulator.
 */
#ifndef NC_AUDIO_H
#define NC_AUDIO_H

#include <audsrv.h>
#include <kernel.h>
#include <loadfile.h>
#include <sbv_patches.h>
#include <sifrpc.h>
#include <string.h>

#include "audio/audio_data.h"

extern unsigned char nc_audsrv_irx[];
extern unsigned char nc_audsrv_irx_end[];

#if (NC_MUSIC_RATE != NC_SFX_RATE * 2)
#error "the mixer assumes effects run at exactly half the output rate"
#endif

#define NC_VOICES 4                 /* effects that may overlap */
#define NC_CHUNK 512                /* samples handed to audsrv at a time */

/* The SPU's predictor coefficients, scaled by 64. Same table the encoder uses;
 * decoding has to reproduce the encoder's arithmetic exactly or the two drift
 * apart over a block. */
static const short nc_adpcm_coef[5][2] = {
    {0, 0}, {60, 0}, {115, -52}, {98, -55}, {122, -60}
};

typedef struct {
    const unsigned char *data;
    int blocks;                     /* length in 16-byte ADPCM blocks */
    int block;                      /* next block to decode */
    short pcm[28];
    int position;                   /* how far through pcm we are */
    int phase;                      /* second copy of this sample pending */
    int prev1, prev2;
    int playing, loop;
} NCVoice;

static NCVoice nc_music_voice;
static NCVoice nc_sfx_voice[NC_VOICES];
static short nc_mix_buffer[NC_CHUNK];
static int nc_audio_ready;

/* 0..100, straight out of the options screen. */
static int nc_music_volume = 70;
static int nc_sfx_volume = 90;
static int nc_music_track = -1;

/* One cursor per family, advanced on every play and wrapped. Deterministic on
 * purpose: a variation set exists to be heard, and shuffling means never being
 * sure you have heard it all. */
static int nc_family_cursor[NC_FAMILY_COUNT];


/* What each family is used for. Resolved by name at startup rather than fixed
 * as indices, so replacing the sound pack with a differently named one still
 * produces a game that makes noise in the right places -- and one with fewer
 * families than roles simply reuses them instead of falling silent. */
static int nc_role_move;            /* moving a selection */
static int nc_role_confirm;         /* taking a choice, turning a page */
static int nc_role_reward;          /* receiving an item */
static int nc_role_shift;           /* scene change, inventory, pausing */


static int nc_family_named(const char *want, int fallback)
{
    int i;
    if (NC_FAMILY_COUNT <= 0)
        return -1;
    for (i = 0; i < NC_FAMILY_COUNT; i++)
        if (strstr(nc_families[i].name, want))
            return i;
    return fallback % NC_FAMILY_COUNT;
}


static void nc_roles_resolve(void)
{
    nc_role_move = nc_family_named("OCEAN", 0);
    nc_role_confirm = nc_family_named("SKY", 1);
    nc_role_reward = nc_family_named("SPIRIT", 2);
    nc_role_shift = nc_family_named("WIND", 3);
}


static void nc_voice_decode(NCVoice *voice)
{
    const unsigned char *block;
    int filter, shift, i;

    if (voice->block >= voice->blocks) {
        if (!voice->loop) {
            voice->playing = 0;
            return;
        }
        voice->block = 0;
        voice->prev1 = voice->prev2 = 0;
    }

    block = voice->data + voice->block * 16;
    filter = block[0] >> 4;
    shift = block[0] & 0x0F;
    if (filter > 4) filter = 0;
    if (shift > 12) shift = 12;

    for (i = 0; i < 28; i++) {
        int nibble = (block[2 + (i >> 1)] >> ((i & 1) * 4)) & 0x0F;
        int sample = nibble > 7 ? nibble - 16 : nibble;
        int value = (sample << (12 - shift))
                  + ((voice->prev1 * nc_adpcm_coef[filter][0]
                      + voice->prev2 * nc_adpcm_coef[filter][1]) >> 6);
        if (value > 32767) value = 32767;
        else if (value < -32768) value = -32768;
        voice->pcm[i] = (short)value;
        voice->prev2 = voice->prev1;
        voice->prev1 = value;
    }
    voice->block++;
    voice->position = 0;
}


static void nc_voice_start(NCVoice *voice, const unsigned char *data, int bytes,
                           int loop)
{
    memset(voice, 0, sizeof(*voice));
    voice->data = data;
    voice->blocks = bytes / 16;
    voice->loop = loop;
    voice->playing = voice->blocks > 0;
    voice->position = 28;           /* forces a decode on the first sample */
}


/* Next sample from a voice, or 0 when it has finished. `twice` upsamples by
 * holding each source sample for two output samples. */
static int nc_voice_next(NCVoice *voice, int twice)
{
    if (!voice->playing)
        return 0;
    if (twice && voice->phase) {
        voice->phase = 0;
        return voice->pcm[voice->position - 1];
    }
    if (voice->position >= 28) {
        nc_voice_decode(voice);
        if (!voice->playing)
            return 0;
    }
    voice->phase = twice;
    return voice->pcm[voice->position++];
}


/* Start-up, one step per frame.
 *
 * Doing this as a single blocking call was a mistake twice over. Two of these
 * steps can hang rather than return -- SifExecModuleBuffer against an unpatched
 * loader, and audsrv_init, which spins binding its RPC until the module answers
 * and never gives up if it never will. A hang inside one call is invisible: the
 * console simply stops, and every step looks equally guilty.
 *
 * Split up, the step number is on screen before the step runs. Whatever is
 * showing when it stops is the thing that stopped it, and one boot identifies
 * it instead of a round of guesses.
 */
enum {
    NC_AUDIO_PATCH, NC_AUDIO_LIBSD, NC_AUDIO_IRX, NC_AUDIO_START,
    NC_AUDIO_FORMAT, NC_AUDIO_DONE, NC_AUDIO_FAILED
};

static int nc_audio_step = NC_AUDIO_PATCH;
static int nc_audio_detail;             /* whatever the failing step returned */
static int nc_audio_failed_at;          /* the step that failed, not FAILED */

static const char *const NC_AUDIO_STAGE[] = {
    "PATCH LOADER", "LOAD LIBSD", "SEND AUDSRV", "START AUDSRV",
    "SET FORMAT", "READY", "FAILED"
};


/* Performs one step. Call once a frame until it stops changing. */
static void nc_audio_advance(void)
{
    int result = 0;

    switch (nc_audio_step) {
    case NC_AUDIO_PATCH:
        /* The IOP loader will not take a module from a buffer as it ships; the
         * entry point is disabled. Without this, SifExecModuleBuffer hangs. */
        nc_audio_detail = sbv_patch_enable_lmb();
        if (nc_audio_detail < 0) { nc_audio_failed_at = nc_audio_step; nc_audio_step = NC_AUDIO_FAILED; return; }
        nc_audio_step = NC_AUDIO_LIBSD;
        return;

    case NC_AUDIO_LIBSD:
        /* libsd is in the console's own ROM, so it is the one module that does
         * not have to be carried. */
        nc_audio_detail = SifLoadModule("rom0:LIBSD", 0, NULL);
        if (nc_audio_detail < 0) { nc_audio_failed_at = nc_audio_step; nc_audio_step = NC_AUDIO_FAILED; return; }
        nc_audio_step = NC_AUDIO_IRX;
        return;

    case NC_AUDIO_IRX:
        /* An ELF launched from a USB stick has no working directory to load
         * audsrv from, so it travels inside the executable. The transfer is a
         * DMA out of main memory and does not see the EE's cache. */
        FlushCache(0);
        nc_audio_detail = SifExecModuleBuffer(
            nc_audsrv_irx, (unsigned int)(nc_audsrv_irx_end - nc_audsrv_irx),
            0, NULL, &result);
        /* `result` is the module's own verdict. A module that loaded but
         * refused to stay resident leaves audsrv_init spinning on an RPC that
         * will never be answered, so it is checked here rather than there. */
        if (nc_audio_detail < 0 || result == 1) {
            nc_audio_failed_at = nc_audio_step;
            nc_audio_step = NC_AUDIO_FAILED;
            return;
        }
        nc_audio_step = NC_AUDIO_START;
        return;

    case NC_AUDIO_START:
        nc_audio_detail = audsrv_init();
        if (nc_audio_detail != 0) { nc_audio_failed_at = nc_audio_step; nc_audio_step = NC_AUDIO_FAILED; return; }
        nc_audio_step = NC_AUDIO_FORMAT;
        return;

    case NC_AUDIO_FORMAT: {
        struct audsrv_fmt_t format;
        format.freq = NC_MUSIC_RATE;
        format.bits = 16;
        format.channels = 1;
        nc_audio_detail = audsrv_set_format(&format);
        if (nc_audio_detail != 0) { nc_audio_failed_at = nc_audio_step; nc_audio_step = NC_AUDIO_FAILED; return; }
        audsrv_set_volume(MAX_VOLUME);
        nc_roles_resolve();
        nc_audio_ready = 1;
        nc_audio_step = NC_AUDIO_DONE;
        return;
    }

    default:
        return;
    }
}


static int nc_audio_busy(void)
{
    return nc_audio_step < NC_AUDIO_DONE;
}


static void nc_music_play(int track)
{
    if (!nc_audio_ready || NC_MUSIC_COUNT <= 0)
        return;
    track = ((track % NC_MUSIC_COUNT) + NC_MUSIC_COUNT) % NC_MUSIC_COUNT;
    nc_music_track = track;
    nc_voice_start(&nc_music_voice, nc_music[track].data, nc_music[track].size, 1);
}


static void nc_music_stop(void)
{
    nc_music_voice.playing = 0;
    nc_music_track = -1;
}


/* Play one effect by absolute index. Returns the index played, or -1. */
static int nc_sfx_play(int index)
{
    int i, quietest = 0;
    if (!nc_audio_ready || index < 0 || index >= NC_SFX_COUNT)
        return -1;
    for (i = 0; i < NC_VOICES; i++) {
        if (!nc_sfx_voice[i].playing) {
            quietest = i;
            break;
        }
        /* All busy: take the one furthest through, which is the one closest to
         * finishing and so the least missed. */
        if (nc_sfx_voice[i].block > nc_sfx_voice[quietest].block)
            quietest = i;
    }
    nc_voice_start(&nc_sfx_voice[quietest], nc_sfx_bin + nc_sfx[index].offset,
                   nc_sfx[index].size, 0);
    return index;
}


/* Play the next variation from a family, in order, wrapping at the end. */
static int nc_sfx_family(int family)
{
    int index;
    if (family < 0 || family >= NC_FAMILY_COUNT)
        return -1;
    index = nc_families[family].first
          + (nc_family_cursor[family] % nc_families[family].count);
    nc_family_cursor[family]++;
    return nc_sfx_play(index);
}


/* Fill whatever room audsrv has. Called once a frame; the ring buffer is what
 * absorbs a frame that runs long, so this must not be skipped. */
static void nc_audio_pump(void)
{
    int room;
    if (!nc_audio_ready)
        return;

    room = audsrv_available();
    while (room >= (int)sizeof(nc_mix_buffer)) {
        int i, v;
        for (i = 0; i < NC_CHUNK; i++) {
            int total = (nc_voice_next(&nc_music_voice, 0) * nc_music_volume) / 100;
            for (v = 0; v < NC_VOICES; v++)
                total += (nc_voice_next(&nc_sfx_voice[v], 1) * nc_sfx_volume) / 100;
            if (total > 32767) total = 32767;
            else if (total < -32768) total = -32768;
            nc_mix_buffer[i] = (short)total;
        }
        audsrv_play_audio((char *)nc_mix_buffer, sizeof(nc_mix_buffer));
        room -= sizeof(nc_mix_buffer);
    }
}

#endif
