/*
 * Neon Coffee - controller input
 *
 * Uses the BIOS pad driver, which fills a buffer for us in the background. The
 * low-level SPI approach (see PSn00bSDK's io/pads example) gives more control over
 * analog and multitap, but this is enough for digital input and far less code.
 */

#include <psxapi.h>
#include <string.h>

#include "nc.h"

/* The BIOS writes controller state straight into these, one per port. */
static uint8_t pad_buff[2][34];

static uint16_t btn_now;
static uint16_t btn_prev;
static int primed;

void nc_input_init(void)
{
    /* Buttons are reported active-low, so a zeroed buffer reads as EVERY button
     * held down. Before the BIOS driver has filled it in, that makes the first
     * frame look like the player is mashing everything -- which instantly
     * dismisses any menu waiting on a button press. Start it at 0xFF so an
     * unpolled pad reads as idle. */
    memset(pad_buff, 0xFF, sizeof(pad_buff));

    InitPAD(pad_buff[0], 34, pad_buff[1], 34);
    StartPAD();

    /* Stop the BIOS clearing the buffer every frame, so we can read it whenever. */
    ChangeClearPAD(0);

    btn_now = btn_prev = 0;
    primed = 0;
}

void nc_input_poll(void)
{
    const PADTYPE *pad = (const PADTYPE *)pad_buff[0];

    btn_prev = btn_now;

    /* stat 0 means "a controller replied". The hardware reports buttons
     * active-low, so invert to get the friendlier 1 = pressed. */
    if (pad->stat == 0)
        btn_now = ~pad->btn;
    else
        btn_now = 0;

    /* On the very first poll btn_prev is still whatever we started with. Seed
     * it from btn_now so nothing counts as "newly pressed" on frame one. */
    if (!primed) {
        btn_prev = btn_now;
        primed = 1;
    }
}

int nc_held(uint16_t button)
{
    return (btn_now & button) != 0;
}

int nc_pressed(uint16_t button)
{
    return ((btn_now & ~btn_prev) & button) != 0;
}
