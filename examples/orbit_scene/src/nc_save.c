/*
 * Neon Coffee - saving to a memory card
 *
 * The BIOS exposes the memory card as a tiny filesystem: open/read/write/close
 * on a path like "bu00:BASLUS-99999NAME". Card 1 is bu00, card 2 is bu10.
 *
 * A file is always a whole number of 8 KB blocks, and the first 512 bytes are a
 * header the console's own memory-card screen reads to show a name and an icon.
 * We write a real one -- a save that shows up as "corrupted" in the BIOS is
 * alarming even when the game reads it back fine.
 *
 * What the game actually stores is deliberately small: a fixed array of ints.
 * There is no allocator and no serialisation format worth writing for a machine
 * with 2 MB; a high score, a level number and some flags is what this is for.
 */

#include <psxapi.h>
#include <stdio.h>
#include <string.h>

#include "nc.h"

/* BIOS open() flags. These are the classic PlayStation values; creating a file
 * additionally needs the block count in the upper 16 bits. */
#define NC_O_RDONLY  0x0001
#define NC_O_WRONLY  0x0002
#define NC_O_CREAT   0x0200

#define SAVE_BLOCKS  1
#define SAVE_BYTES   8192
#define DATA_OFFSET  512            /* user data starts after the header */
#define DATA_MAGIC   0x5653434E     /* "NCSV" little-endian */
#define DATA_VERSION 1

static int values[NC_SAVE_SLOTS];
static int started;

/* One 8 KB block, built in RAM and written in a single pass. 8 KB of a 2 MB
 * machine is a real cost, so it is a local in the functions that need it rather
 * than a permanent static. */


static void save_init_once(void)
{
    int i;

    if (started)
        return;

    /* Bring up the BIOS card driver. The argument enables sharing the SIO port
     * with the controllers, which is what we want since we poll pads too. */
    InitCARD(1);
    StartCARD();

    /* Wait before reading the card's directory. The driver talks to the card
     * over the controller port, driven by the vertical blank, so immediately
     * after StartCARD() it has not yet exchanged a single byte. _bu_init() run
     * that early does not report an error -- it quietly leaves the directory
     * blank, and then every save fails with "card full", because a directory
     * of fifteen zeroed entries has no free block in it. */
    for (i = 0; i < 8; i++)
        VSync(0);

    _bu_init();

    /* Deliberately no _card_info() here. It marks the card busy and only the
     * driver's completion interrupt clears that flag again -- and every open()
     * refuses while the flag is set. It is a query, and it costs you the card.
     */

    started = 1;
}


/* Why not report the BIOS errno? _get_errno() is B(0x54), and OpenBIOS -- the
 * BIOS this project ships -- leaves that entry unimplemented: calling it prints
 * "Unimplemented B0:54" and halts the console. So the card's own status byte is
 * what we report instead. */

/* The first access after the driver starts can report the card busy: the driver
 * talks to it over the controller port a frame at a time, so nothing is known
 * about the card until a few frames have gone by. */
static int open_retry(const char *path, int flags)
{
    int fd, tries;

    for (tries = 0; tries < 16; tries++) {
        fd = open(path, flags);
        if (fd >= 0)
            return fd;
        VSync(0);
    }
    return -1;
}


/* Build the 512-byte header the console's memory card screen expects. */
static void write_header(unsigned char *buf)
{
    int i;

    memset(buf, 0, DATA_OFFSET);

    buf[0] = 'S';                 /* magic */
    buf[1] = 'C';
    buf[2] = 0x11;                /* one icon frame */
    buf[3] = SAVE_BLOCKS;

    /* Title, in Shift-JIS. Plain ASCII is valid Shift-JIS, so an English name
     * needs no conversion. */
    {
        const char *title = NC_SAVE_TITLE;
        for (i = 0; i < 60 && title[i]; i++)
            buf[4 + i] = (unsigned char)title[i];
    }

    /* 16-colour CLUT at 0x60, BGR555 with the top bit set so nothing reads as
     * transparent. Entry 0 stays 0 so the icon has a clear background. */
    {
        static const unsigned short clut[16] = {
            0x0000, 0x8000, 0xFFFF, 0xFC00, 0x83FF, 0x8FE0, 0xBDEF, 0x9CE7,
            0xF800, 0x801F, 0xFFE0, 0x8410, 0xC618, 0xE71C, 0x9294, 0xAD6B,
        };
        for (i = 0; i < 16; i++) {
            buf[0x60 + i * 2 + 0] = (unsigned char)(clut[i] & 0xFF);
            buf[0x60 + i * 2 + 1] = (unsigned char)(clut[i] >> 8);
        }
    }

    /* 16x16 icon at 0x80, 4 bits per pixel, two pixels per byte. A small
     * diamond so the save is recognisable at a glance. */
    {
        int x, y;
        for (y = 0; y < 16; y++) {
            for (x = 0; x < 16; x += 2) {
                int d0 = (x - 8 < 0 ? 8 - x : x - 8) + (y - 8 < 0 ? 8 - y : y - 8);
                int d1 = (x + 1 - 8 < 0 ? 7 - x : x - 7)
                         + (y - 8 < 0 ? 8 - y : y - 8);
                unsigned char p0 = (d0 < 5) ? 4 : ((d0 < 8) ? 6 : 0);
                unsigned char p1 = (d1 < 5) ? 4 : ((d1 < 8) ? 6 : 0);
                buf[0x80 + y * 8 + x / 2] = (unsigned char)(p0 | (p1 << 4));
            }
        }
    }
}


void nc_save_init(void)
{
    int i;
    save_init_once();
    for (i = 0; i < NC_SAVE_SLOTS; i++)
        values[i] = 0;
}


int nc_save_get(int slot)
{
    if (slot < 0 || slot >= NC_SAVE_SLOTS)
        return 0;
    return values[slot];
}


void nc_save_set(int slot, int value)
{
    if (slot < 0 || slot >= NC_SAVE_SLOTS)
        return;
    values[slot] = value;
}


int nc_save_store(void)
{
    static unsigned char block[SAVE_BYTES];
    int fd, written, i;
    int *data;

    save_init_once();

    memset(block, 0, sizeof(block));
    write_header(block);

    data = (int *)(block + DATA_OFFSET);
    data[0] = DATA_MAGIC;
    data[1] = DATA_VERSION;
    for (i = 0; i < NC_SAVE_SLOTS; i++)
        data[2 + i] = values[i];

    /* Try the existing file first. Creating needs the block count in the high
     * half of the flags, and on some BIOS revisions asking to create a file
     * that is already there fails rather than reusing it. */
    fd = open_retry(NC_SAVE_PATH, NC_O_WRONLY);
    if (fd < 0)
        fd = open_retry(NC_SAVE_PATH, NC_O_CREAT | (SAVE_BLOCKS << 16));
    if (fd < 0) {
        printf("nc_save: cannot open %s (card status %d)\n",
               NC_SAVE_PATH, _card_status(0));
        return 0;
    }

    written = write(fd, block, SAVE_BYTES);
    close(fd);

    if (written != SAVE_BYTES) {
        printf("nc_save: wrote %d of %d bytes\n", written, SAVE_BYTES);
        return 0;
    }

    printf("nc_save: saved\n");
    return 1;
}


int nc_save_load(void)
{
    static unsigned char block[SAVE_BYTES];
    int fd, got, i;
    const int *data;

    save_init_once();

    fd = open_retry(NC_SAVE_PATH, NC_O_RDONLY);
    if (fd < 0)
        return 0;                       /* no save yet: not an error */

    got = read(fd, block, SAVE_BYTES);
    close(fd);

    if (got != SAVE_BYTES) {
        printf("nc_save: read %d of %d bytes\n", got, SAVE_BYTES);
        return 0;
    }

    data = (const int *)(block + DATA_OFFSET);
    if (data[0] != DATA_MAGIC) {
        printf("nc_save: file is not a Neon Coffee save\n");
        return 0;
    }
    if (data[1] != DATA_VERSION) {
        /* A save from an older build. Ignoring it is kinder than reading
         * fields that have moved. */
        printf("nc_save: save version %d, expected %d -- ignoring\n",
               data[1], DATA_VERSION);
        return 0;
    }

    for (i = 0; i < NC_SAVE_SLOTS; i++)
        values[i] = data[2 + i];

    printf("nc_save: loaded\n");
    return 1;
}


int nc_save_erase(void)
{
    save_init_once();
    return erase(NC_SAVE_PATH) >= 0 ? 1 : 0;
}
