/*
 * Neon Coffee - sound
 *
 * The SPU has 512 KB of its own RAM and 24 voices. Samples are uploaded once at
 * startup and then played by pointing a voice at an address, so playing a sound
 * costs almost nothing at run time -- there is no mixing on the CPU at all.
 *
 * Voices are handed out round-robin. With 24 of them a sound effect has to be
 * very unlucky to get cut off, and tracking which are still playing would cost
 * more than it saves.
 */

#include <stdio.h>

#include "nc.h"

/* The first 4 KB of SPU RAM are capture buffers, and psxspu puts a dummy block
 * at 0x1000, so samples start after that. */
#define SPU_ALLOC_START 0x1010
#define SPU_VOICES 24

typedef struct {
    int addr;
    int rate;
} NC_SoundSlot;

static NC_SoundSlot slots[NC_MAX_SOUNDS];
static int slot_count;
static int next_addr = SPU_ALLOC_START;
static int next_voice;
static int ready;


void nc_audio_init(void)
{
    SpuInit();
    slot_count = 0;
    next_addr = SPU_ALLOC_START;
    next_voice = 0;
    ready = 1;
}


int nc_audio_add(const void *adpcm, int size, int rate)
{
    int addr, padded;

    if (!ready)
        nc_audio_init();

    if (slot_count >= NC_MAX_SOUNDS) {
        printf("nc_audio: more than %d sounds, ignoring the rest\n",
               NC_MAX_SOUNDS);
        return -1;
    }

    /* SPU DMA moves 64 bytes at a time, so round up. */
    addr = next_addr;
    padded = (size + 63) & ~63;

    SpuSetTransferMode(SPU_TRANSFER_BY_DMA);
    SpuSetTransferStartAddr(addr);
    SpuWrite((const uint32_t *)adpcm, padded);
    SpuIsTransferCompleted(SPU_TRANSFER_WAIT);

    next_addr = addr + padded;

    slots[slot_count].addr = addr;
    slots[slot_count].rate = rate;
    return slot_count++;
}


void nc_audio_play(int id)
{
    int ch;

    if (id < 0 || id >= slot_count)
        return;

    ch = next_voice;
    next_voice = (next_voice + 1) % SPU_VOICES;

    /* Stop the voice before repointing it, or it plays from the wrong place
     * for a moment. */
    SpuSetKey(0, 1 << ch);

    /* The SPU wants the rate in 4.12 fixed point where 1.0 is 44100 Hz, and the
     * address in 8-byte units. These macros do both conversions. */
    SPU_CH_FREQ(ch) = getSPUSampleRate(slots[id].rate);
    SPU_CH_ADDR(ch) = getSPUAddr(slots[id].addr);

    SPU_CH_VOL_L(ch) = 0x3fff;
    SPU_CH_VOL_R(ch) = 0x3fff;
    /* Dummy ADSR values that disable the envelope: the sample plays as-is. */
    SPU_CH_ADSR1(ch) = 0x00ff;
    SPU_CH_ADSR2(ch) = 0x0000;

    SpuSetKey(1, 1 << ch);
}


int nc_audio_count(void)
{
    return slot_count;
}
