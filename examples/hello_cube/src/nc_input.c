/*
 * Neon Coffee - controller input
 *
 * Uses the BIOS pad driver, which fills a buffer for us in the background. The
 * low-level SPI approach (see PSn00bSDK's io/pads example) gives more control over
 * analog and multitap, but this is enough for digital input and far less code.
 */

#include <psxapi.h>

#include "nc.h"

/* The BIOS writes controller state straight into these, one per port. */
static uint8_t pad_buff[2][34];

static uint16_t btn_now;
static uint16_t btn_prev;

void nc_input_init(void)
{
    InitPAD(pad_buff[0], 34, pad_buff[1], 34);
    StartPAD();

    /* Stop the BIOS clearing the buffer every frame, so we can read it whenever. */
    ChangeClearPAD(0);

    btn_now = btn_prev = 0;
}

void nc_input_poll(void)
{
    const PADTYPE *pad = (const PADTYPE *)pad_buff[0];

    btn_prev = btn_now;

    /* stat 0 means "a controller replied". The hardware reports buttons active-low,
     * so invert to get the friendlier 1 = pressed. */
    if (pad->stat == 0)
        btn_now = ~pad->btn;
    else
        btn_now = 0;
}

int nc_held(uint16_t button)
{
    return (btn_now & button) != 0;
}

int nc_pressed(uint16_t button)
{
    return ((btn_now & ~btn_prev) & button) != 0;
}
