/*
 * @NAME@ - a Neon Coffee visual novel for the PlayStation 2
 *
 * A title screen with the logo, a menu you navigate with the pad, and a scene
 * of text you advance a line at a time. That is most of what a visual novel is,
 * and it is a deliberate first game for this machine: no physics, no scrolling,
 * no per-frame budget to blow. Textured quads and text.
 *
 *   TITLE   START or X   go to the menu
 *   MENU    up/down      choose,  X select,  TRIANGLE back to the title
 *   STORY   X            next line,  TRIANGLE back to the menu
 *
 * Both textures are compiled in. The PS1 side loads its art from a .ncpkg
 * because it has a runtime that does that; the PS2 side has no runtime yet, so
 * this does what PS2SDK's own samples do and links the pixels in. That is M6.
 *
 * The alpha convention on this hardware catches everyone once: 0x80 is fully
 * opaque, not 0xFF. Texels at 0x00 are what the alpha test throws away, which
 * is how the logo and the glyphs get transparent backgrounds without blending.
 */

#include <kernel.h>
#include <stdio.h>
#include <string.h>
#include <tamtypes.h>

#include <dma.h>
#include <draw.h>
#include <draw2d.h>
#include <graph.h>
#include <gs_psm.h>
#include <libpad.h>
#include <packet.h>
#include <sifrpc.h>
#include <loadfile.h>

#define SCREEN_W 640
#define SCREEN_H 448
#define OFF_X (2048 - (SCREEN_W / 2))
#define OFF_Y (2048 - (SCREEN_H / 2))

/* The Neon Coffee ground, matching NC Studio and the PS1 runtime. */
#define BG_R 0x14
#define BG_G 0x18
#define BG_B 0x1a

/* Glyph cell, and how large a character is drawn. The sheet is 8x8; at 2x it
 * is readable from a sofa, which is the only display test that matters. */
#define CELL 8
#define GLYPH_W 16
#define GLYPH_H 16

#define FIRST_CHAR 32
#define FONT_COLUMNS 32
#define FONT_ROWS 2

extern unsigned int nc_logo[];
extern const int nc_logo_width, nc_logo_height;
/* The logo does not fill its power-of-two canvas, and it is not square. Both
 * facts have to reach the draw call or it comes out squashed. */
extern const int nc_logo_used_w, nc_logo_used_h;
extern unsigned int nc_font[];
extern const int nc_font_width, nc_font_height;

enum { SCENE_TITLE, SCENE_MENU, SCENE_STORY, SCENE_ABOUT };

static char pad_buffer[256] __attribute__((aligned(64)));

static framebuffer_t frame;
static zbuffer_t z;
static texbuffer_t logo_tex, font_tex;
static packet_t *packet;

/* How many quadwords a frame may build. A textured rect costs several, and a
 * screen of text is hundreds of them -- the story scene alone is over six
 * hundred glyphs. Sizing this by eye is how you get a packet that overruns its
 * buffer, writes through whatever follows it in memory, and leaves a console
 * showing nothing at all. 8192 qwords is 128 KB, which is nothing against
 * 32 MB, and the guard below means overshooting drops primitives instead of
 * corrupting memory. */
#define DRAW_QWORDS 8192
#define QWORD_MARGIN 16

static qword_t *packet_limit;

/* Which texture the GS is currently set to sample. Switching costs a packet, so
 * runs of text are drawn together rather than interleaved with the logo. */
static texbuffer_t *bound;

static const char *MENU_ITEMS[] = { "BEGIN", "ABOUT", "TITLE SCREEN" };
#define MENU_COUNT 3

static const char *STORY[] = {
    "THE SHOP IS SHUT. THE SIGN STILL HUMS.",
    "",
    "YOU HAVE A DEV KIT THAT IS NOT A DEV KIT,",
    "A CONSOLE FROM 2000, AND A USB STICK.",
    "",
    "THAT TURNS OUT TO BE ENOUGH.",
    "",
    "EVERYTHING ON THIS SCREEN WAS BUILT BY",
    "NEON COFFEE AND RAN ON REAL HARDWARE.",
    "",
    "THE LOGO IS A TEXTURE IN GRAPHICS MEMORY.",
    "THE TEXT IS A SHEET OF 8X8 GLYPHS.",
    "THE PAD IS READ THROUGH THE IOP.",
    "",
    "NOW GO AND MAKE SOMETHING.",
};
#define STORY_LINES (int)(sizeof(STORY) / sizeof(STORY[0]))

static const char *ABOUT[] = {
    "NEON COFFEE ENGINE",
    "",
    "PS1  PSN00BSDK, A .NCPKG OF ART AND",
    "     SCENES, AND NCSCRIPT COMPILED TO C.",
    "",
    "PS2  PS2SDK. THIS SCREEN. THE RUNTIME",
    "     ITSELF IS STILL TO COME -- M6.",
    "",
    "GODOT IS THE SCENE EDITOR, UNFORKED.",
    "NC STUDIO IS THE MANAGER.",
    "",
    "TRIANGLE TO GO BACK.",
};
#define ABOUT_LINES (int)(sizeof(ABOUT) / sizeof(ABOUT[0]))


/* ---- setup ------------------------------------------------------------- */

static void load_pad_modules(void)
{
    SifInitRpc(0);
    /* Console models disagree about the names: later ones ship the X variants.
     * Trying the plain pair first and falling back costs nothing. */
    if (SifLoadModule("rom0:SIO2MAN", 0, NULL) < 0)
        SifLoadModule("rom0:XSIO2MAN", 0, NULL);
    if (SifLoadModule("rom0:PADMAN", 0, NULL) < 0)
        SifLoadModule("rom0:XPADMAN", 0, NULL);
}


static void init_gs(void)
{
    frame.width = SCREEN_W;
    frame.height = SCREEN_H;
    frame.mask = 0;
    frame.psm = GS_PSM_32;
    frame.address = graph_vram_allocate(frame.width, frame.height, frame.psm,
                                        GRAPH_ALIGN_PAGE);

    z.enable = DRAW_DISABLE;
    z.mask = 0;
    z.method = ZTEST_METHOD_ALLPASS;
    z.zsm = GS_ZBUF_32;
    z.address = 0;

    logo_tex.width = nc_logo_width;
    logo_tex.psm = GS_PSM_32;
    logo_tex.address = graph_vram_allocate(nc_logo_width, nc_logo_height,
                                           GS_PSM_32, GRAPH_ALIGN_BLOCK);
    logo_tex.info.width = draw_log2(nc_logo_width);
    logo_tex.info.height = draw_log2(nc_logo_height);
    logo_tex.info.components = TEXTURE_COMPONENTS_RGBA;
    logo_tex.info.function = TEXTURE_FUNCTION_DECAL;

    font_tex.width = nc_font_width;
    font_tex.psm = GS_PSM_32;
    font_tex.address = graph_vram_allocate(nc_font_width, nc_font_height,
                                           GS_PSM_32, GRAPH_ALIGN_BLOCK);
    font_tex.info.width = draw_log2(nc_font_width);
    font_tex.info.height = draw_log2(nc_font_height);
    font_tex.info.components = TEXTURE_COMPONENTS_RGBA;
    font_tex.info.function = TEXTURE_FUNCTION_DECAL;

    graph_initialize(frame.address, frame.width, frame.height, frame.psm, 0, 0);
}


static void upload(void *pixels, int w, int h, texbuffer_t *tex)
{
    qword_t *q = packet->data;

    /* The DMA reads main memory directly and knows nothing about the EE cache,
     * so anything the CPU has touched has to be written back first. Texture
     * data that is never read back looks fine on an emulator and uploads
     * garbage -- or nothing -- on hardware. */
    FlushCache(0);
    q = draw_texture_transfer(q, pixels, w, h, GS_PSM_32,
                              tex->address, tex->width);
    q = draw_texture_flush(q);
    dma_channel_send_chain(DMA_CHANNEL_GIF, packet->data,
                           q - packet->data, 0, 0);
    dma_wait_fast();
}


static void init_environment(void)
{
    qword_t *q = packet->data;
    atest_t atest;
    dtest_t dtest;
    ztest_t ztest;
    lod_t lod;

    q = draw_setup_environment(q, 0, &frame, &z);
    q = draw_primitive_xyoffset(q, 0, OFF_X, OFF_Y);

    /* The alpha test is what makes cut-out textures work without blending:
     * anything at alpha 0 never reaches the framebuffer. Cheaper than blending
     * and, for hard-edged pixel art, indistinguishable from it. */
    atest.enable = DRAW_ENABLE;
    atest.method = ATEST_METHOD_GREATER;
    atest.compval = 0x00;
    atest.keep = ATEST_KEEP_FRAMEBUFFER;
    dtest.enable = DRAW_DISABLE;
    dtest.pass = 0;
    ztest.enable = DRAW_DISABLE;
    ztest.method = ZTEST_METHOD_ALLPASS;
    q = draw_pixel_test(q, 0, &atest, &dtest, &ztest);

    lod.calculation = LOD_USE_K;
    lod.max_level = 0;
    lod.mag_filter = LOD_MAG_NEAREST;   /* pixel art; filtering would smear it */
    lod.min_filter = LOD_MIN_NEAREST;
    lod.l = 0;
    lod.k = 0;
    q = draw_texture_sampling(q, 0, &lod);

    q = draw_finish(q);
    dma_channel_send_normal(DMA_CHANNEL_GIF, packet->data,
                            q - packet->data, 0, 0);
    dma_wait_fast();
}


/* ---- drawing ----------------------------------------------------------- */

static qword_t *bind_texture(qword_t *q, texbuffer_t *tex)
{
    clutbuffer_t clut;

    if (bound == tex)
        return q;
    bound = tex;

    clut.storage_mode = CLUT_STORAGE_MODE1;
    clut.start = 0;
    clut.psm = 0;
    clut.load_method = CLUT_NO_LOAD;
    clut.address = 0;

    return draw_texturebuffer(q, 0, tex, &clut);
}


static qword_t *sprite(qword_t *q, int x, int y, int w, int h,
                       int u, int v, int tw, int th, int bright)
{
    texrect_t r;

    /* Refusing to draw is always better than writing past the buffer. */
    if (q + QWORD_MARGIN >= packet_limit)
        return q;

    r.v0.x = (float)(OFF_X + x);
    r.v0.y = (float)(OFF_Y + y);
    r.v0.z = 0;
    r.t0.u = (float)u;
    r.t0.v = (float)v;

    r.v1.x = (float)(OFF_X + x + w);
    r.v1.y = (float)(OFF_Y + y + h);
    r.v1.z = 0;
    r.t1.u = (float)(u + tw);
    r.t1.v = (float)(v + th);

    /* 0x80 is neutral for both colour and alpha here. Dimming a menu item is
     * just a lower value on all three channels. */
    r.color.r = r.color.g = r.color.b = bright;
    r.color.a = 0x80;
    r.color.q = 1.0f;

    return draw_rect_textured(q, 0, &r);
}


static qword_t *text(qword_t *q, int x, int y, const char *s, int bright)
{
    int i;

    q = bind_texture(q, &font_tex);

    for (i = 0; s[i]; i++) {
        int c = (unsigned char)s[i];
        int index;

        if (c >= 'a' && c <= 'z')
            c -= 32;                    /* one case, like the PS1 side */

        index = c - FIRST_CHAR;
        if (index >= 0 && index < FONT_COLUMNS * FONT_ROWS && c != ' ')
            q = sprite(q, x, y, GLYPH_W, GLYPH_H,
                       (index % FONT_COLUMNS) * CELL,
                       (index / FONT_COLUMNS) * CELL,
                       CELL, CELL, 0x80);

        x += GLYPH_W;
    }
    return q;
}


static int text_width(const char *s)
{
    int n = 0;
    while (s[n])
        n++;
    return n * GLYPH_W;
}


static qword_t *text_center(qword_t *q, int y, const char *s, int bright)
{
    return text(q, (SCREEN_W - text_width(s)) / 2, y, s, bright);
}


static qword_t *panel(qword_t *q, int x, int y, int w, int h,
                      int r, int g, int b)
{
    rect_t box;

    if (q + QWORD_MARGIN >= packet_limit)
        return q;

    /* A flat rectangle needs no texture, and leaving the font bound while
     * drawing one would sample a glyph across the whole panel. */
    bound = 0;

    box.v0.x = (float)(OFF_X + x);
    box.v0.y = (float)(OFF_Y + y);
    box.v0.z = 0;
    box.v1.x = (float)(OFF_X + x + w);
    box.v1.y = (float)(OFF_Y + y + h);
    box.v1.z = 0;
    box.color.r = r;
    box.color.g = g;
    box.color.b = b;
    box.color.a = 0x80;
    box.color.q = 1.0f;

    return draw_rect_filled(q, 0, &box);
}


/* ---- scenes ------------------------------------------------------------ */

/* Draw the logo at a given height, keeping its own proportions. */
static qword_t *logo(qword_t *q, int x, int y, int height)
{
    int width = nc_logo_used_w * height / nc_logo_used_h;

    q = bind_texture(q, &logo_tex);
    return sprite(q, x, y, width, height, 0, 0,
                  nc_logo_used_w, nc_logo_used_h, 0x80);
}


static int logo_width_for(int height)
{
    return nc_logo_used_w * height / nc_logo_used_h;
}


static qword_t *draw_title(qword_t *q, int frames)
{
    int height = 176;

    q = logo(q, (SCREEN_W - logo_width_for(height)) / 2, 48, height);

    q = text_center(q, 272, "NEON COFFEE", 0x80);
    q = text_center(q, 300, "PLAYSTATION 2", 0x80);

    /* Blink, so it reads as waiting rather than frozen. */
    if ((frames % 60) < 40)
        q = text_center(q, 372, "PRESS START", 0x80);

    return q;
}


static qword_t *draw_menu(qword_t *q, int selected)
{
    int i;
    int height = 80;

    q = logo(q, 32, 36, height);
    q = text(q, 48 + logo_width_for(height), 64, "NEON COFFEE", 0x80);

    for (i = 0; i < MENU_COUNT; i++) {
        int y = 200 + i * 40;
        if (i == selected) {
            q = panel(q, 140, y - 6, 360, 28, 0x2e, 0x36, 0x39);
            q = text(q, 156, y, ">", 0x80);
        }
        /* The unselected items are drawn dimmer rather than in another colour:
         * one texture, one palette, and the eye still knows where it is. */
        q = text(q, 184, y, MENU_ITEMS[i], i == selected ? 0x80 : 0x48);
    }

    q = text_center(q, 400, "X SELECT   TRIANGLE BACK", 0x40);
    return q;
}


static qword_t *draw_lines(qword_t *q, const char *const *lines, int count,
                           int shown, const char *footer)
{
    int i;

    /* The text box. A visual novel is mostly this rectangle. */
    q = panel(q, 32, 96, SCREEN_W - 64, SCREEN_H - 176, 0x0a, 0x0c, 0x0d);
    q = panel(q, 32, 96, SCREEN_W - 64, 2, 0x5f, 0xd4, 0xd0);

    for (i = 0; i < shown && i < count; i++)
        q = text(q, 56, 120 + i * 20, lines[i], 0x80);

    q = text_center(q, SCREEN_H - 56, footer, 0x40);
    return q;
}


/* ---- main -------------------------------------------------------------- */

int main(void)
{
    struct padButtonStatus pad;
    unsigned int buttons = 0, last = 0, pressed;
    int have_pad = 0, state;

    int scene = SCENE_TITLE;
    int selected = 0;
    int shown = 1;
    int frames = 0;

    printf("@NAME@: Neon Coffee, PlayStation 2\n");

    load_pad_modules();
    padInit(0);
    padPortOpen(0, 0, pad_buffer);
    do {
        state = padGetState(0, 0);
        if (state == PAD_STATE_DISCONN)
            break;
        have_pad = (state == PAD_STATE_STABLE || state == PAD_STATE_FINDCTP1);
    } while (!have_pad);
    if (!have_pad)
        printf("@NAME@: no controller in port 1\n");

    packet = packet_init(DRAW_QWORDS, PACKET_NORMAL);
    if (packet == NULL) {
        printf("@NAME@: could not allocate the draw packet\n");
        SleepThread();
    }
    packet_limit = packet->data + DRAW_QWORDS;
    init_gs();
    init_environment();

    upload(nc_logo, nc_logo_width, nc_logo_height, &logo_tex);
    upload(nc_font, nc_font_width, nc_font_height, &font_tex);

    while (1) {
        qword_t *q;

        if (have_pad && padRead(0, 0, &pad) != 0)
            buttons = 0xFFFF ^ pad.btns;    /* the pad reports active-low */
        pressed = buttons & ~last;
        last = buttons;

        switch (scene) {
        case SCENE_TITLE:
            if (pressed & (PAD_START | PAD_CROSS)) {
                scene = SCENE_MENU;
                selected = 0;
            }
            break;

        case SCENE_MENU:
            if (pressed & PAD_UP)
                selected = (selected + MENU_COUNT - 1) % MENU_COUNT;
            if (pressed & PAD_DOWN)
                selected = (selected + 1) % MENU_COUNT;
            if (pressed & PAD_TRIANGLE)
                scene = SCENE_TITLE;
            if (pressed & PAD_CROSS) {
                if (selected == 0) { scene = SCENE_STORY; shown = 1; }
                else if (selected == 1) { scene = SCENE_ABOUT; shown = ABOUT_LINES; }
                else scene = SCENE_TITLE;
            }
            break;

        case SCENE_STORY:
            /* One line at a time, which is the whole interaction model of the
             * genre: the reader sets the pace. */
            if (pressed & PAD_CROSS) {
                if (shown < STORY_LINES)
                    shown++;
                else
                    scene = SCENE_MENU;
            }
            if (pressed & PAD_TRIANGLE)
                scene = SCENE_MENU;
            break;

        case SCENE_ABOUT:
            if (pressed & (PAD_CROSS | PAD_TRIANGLE))
                scene = SCENE_MENU;
            break;
        }

        q = packet->data;
        bound = 0;
        q = draw_clear(q, 0, OFF_X, OFF_Y, frame.width, frame.height,
                       BG_R, BG_G, BG_B);

        switch (scene) {
        case SCENE_TITLE:
            q = draw_title(q, frames);
            break;
        case SCENE_MENU:
            q = draw_menu(q, selected);
            break;
        case SCENE_STORY:
            q = draw_lines(q, STORY, STORY_LINES, shown,
                           shown < STORY_LINES ? "X NEXT   TRIANGLE MENU"
                                               : "X DONE   TRIANGLE MENU");
            break;
        case SCENE_ABOUT:
            q = draw_lines(q, ABOUT, ABOUT_LINES, ABOUT_LINES,
                           "X BACK");
            break;
        }

        q = draw_finish(q);

        dma_wait_fast();
        dma_channel_send_normal(DMA_CHANNEL_GIF, packet->data,
                                q - packet->data, 0, 0);
        draw_wait_finish();
        graph_wait_vsync();

        frames++;
    }

    packet_free(packet);
    return 0;
}
