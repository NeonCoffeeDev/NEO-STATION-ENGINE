/*
 * @NAME@ - a Neon Coffee PlayStation 2 project
 *
 * This does not build yet, and that is deliberate rather than an oversight.
 *
 * The PS2 is not a faster PS1. It has a 294 MHz MIPS core with two vector
 * units, a real FPU, 32 MB of RAM and 4 MB of VRAM, and a GPU with a depth
 * buffer -- so the ordering table, the fixed-point maths and the GTE transform
 * path that make up most of the PS1 runtime have no counterpart here. Porting
 * the renderer is not a translation; it is a second renderer. That is M6 in
 * docs/ROADMAP.md.
 *
 * What already works for PS2 today:
 *
 *   ncc doctor --target ps2     checks for PS2SDK and ee-gcc
 *   ncc targets                 the hardware profile and its budgets
 *   nc.json                     this project declares target "ps2", and NC
 *                               Studio reconfigures itself when you select it
 *
 * What does not:
 *
 *   ncc build                   refuses, by name, rather than failing three
 *                               layers down inside cmake
 *
 * The shape below is what the PS2 entry point will look like against PS2SDK and
 * gsKit. It is left as a comment because a file that looks buildable and is not
 * is worse than one that says so.
 */

/*
 * #include <kernel.h>
 * #include <gsKit.h>
 * #include <dmaKit.h>
 *
 * int main(void)
 * {
 *     GSGLOBAL *gs = gsKit_init_global();
 *
 *     dmaKit_init(D_CTRL_RELE_OFF, D_CTRL_MFD_OFF, D_CTRL_STS_UNSPEC,
 *                 D_CTRL_STD_OFF, D_CTRL_RCYC_8, 1 << 8);
 *     dmaKit_chan_init(DMA_CHANNEL_GIF);
 *
 *     gsKit_init_screen(gs);
 *     gsKit_mode_switch(gs, GS_ONESHOT);
 *
 *     while (1) {
 *         gsKit_clear(gs, GS_SETREG_RGBAQ(0x14, 0x18, 0x1a, 0x80, 0x00));
 *         gsKit_sync_flip(gs);
 *         gsKit_queue_exec(gs);
 *     }
 *
 *     return 0;
 * }
 */

int main(void)
{
    return 0;
}
