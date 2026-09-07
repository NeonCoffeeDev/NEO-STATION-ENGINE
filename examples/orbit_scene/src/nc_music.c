/*
 * Neon Coffee - music, via CD audio
 *
 * Sound effects live in the SPU's 512 KB, which is nowhere near enough for a
 * song. Music instead goes on the disc as a Red Book CD-DA track -- exactly how
 * most PlayStation games did it -- and the drive streams it straight into the
 * SPU's mixer. It costs no main RAM, no SPU RAM and no CPU time at all.
 *
 * The trade is that the drive is busy while it plays, so a game that also
 * streams data off the disc has to share. Nothing here does that yet.
 *
 * Track 1 is the data track holding the game, so music starts at track 2.
 */

#include <psxcd.h>
#include <stdio.h>

#include "nc.h"

static int cd_ready;
static int current_track;


void nc_music_init(void)
{
    if (cd_ready)
        return;

    CdInit();

    /* Route the drive's audio output into the SPU, then set the CD-to-SPU
     * mixing volumes. Without both of these the track plays silently. */
    SpuSetCommonCDVolume(0x3fff, 0x3fff);
    {
        CdlATV atv;
        atv.val0 = 0x80;    /* left  -> left  */
        atv.val1 = 0x00;    /* left  -> right */
        atv.val2 = 0x80;    /* right -> right */
        atv.val3 = 0x00;    /* right -> left  */
        CdMix(&atv);
    }

    cd_ready = 1;
    current_track = 0;
}


void nc_music_play(int track)
{
    uint8_t mode, t;

    if (!cd_ready)
        nc_music_init();
    if (track < 2) {
        printf("nc_music: track %d is not audio (1 is the data track)\n", track);
        return;
    }

    /* CdlModeDA enables CD-DA playback at all; CdlModeRept makes the drive
     * repeat the track instead of running on into the next one. */
    mode = CdlModeDA | CdlModeRept;
    CdControl(CdlSetmode, &mode, 0);

    t = (uint8_t)track;
    CdControl(CdlPlay, &t, 0);
    current_track = track;
}


void nc_music_stop(void)
{
    if (!cd_ready)
        return;
    CdControl(CdlPause, 0, 0);
    current_track = 0;
}


int nc_music_track(void)
{
    return current_track;
}
