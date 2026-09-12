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
#include <iopcontrol.h>
#include <timer.h>

#define SCREEN_W 640
#define SCREEN_H 448
#define OFF_X (-(SCREEN_W / 2))
#define OFF_Y (-(SCREEN_H / 2))

/* Frame buffers are 16-bit. Two of them occupy exactly the same graphics
 * memory as the single 32-bit buffer this used to have -- 140 pages either
 * way -- so double buffering costs nothing here, and 16-bit halves the write
 * bandwidth for every pixel the GS lays down. The console is fill-limited
 * long before it is polygon-limited, and the visual novel is the most
 * fill-heavy screen in the project.
 *
 * The cost is 5 bits per channel instead of 8. Dithering hides the banding,
 * and a flat terminal palette has little for it to band across. If a
 * television disagrees, this is the only line that has to change. */
#define FRAME_PSM GS_PSM_16S

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
extern unsigned int nc_ui_skin[];
extern const int nc_ui_skin_width, nc_ui_skin_height;
extern const int nc_ui_skin_used_w, nc_ui_skin_used_h;
extern unsigned int nc_font[];
extern const int nc_font_width, nc_font_height;

enum { SCENE_INIT, SCENE_SPLASH, SCENE_INTRO, SCENE_TITLE, SCENE_MENU, SCENE_WORLD3D, SCENE_STORY, SCENE_ABOUT, SCENE_UI_LAB, SCENE_PAUSE };

/* Where START was pressed, so RESUME puts you back rather than somewhere
 * sensible-looking. */
static int scene_before_pause;

static char pad_buffer[256] __attribute__((aligned(64)));

/* Drawing into the buffer the television is scanning out is what made the top
 * of the picture crawl: the loop starts redrawing the instant vsync returns,
 * which is exactly when the beam is on the first rows. Whatever the GS has not
 * finished by then is caught mid-repaint. Lower rows are drawn before the beam
 * gets to them, which is why only the top band showed it. */
static framebuffer_t frame[2];
static int frame_count = 1;     /* 2 once the second buffer is really there */
static int frame_draw;          /* the buffer being drawn into right now */
static zbuffer_t z;
static texbuffer_t logo_tex, ui_skin_tex, font_tex;
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

#include "nc_ui_generated.h"

#include "vn_content.h"
#include "nc_audio.h"
#include "nc_world3d.h"

/* How many frames each character of dialogue takes. vn_runtime.h reads it,
 * so it is declared here and seeded from the kit once VN_SPEED exists. */
static int text_speed = 2;



/* ---- setup ------------------------------------------------------------- */

static void load_pad_modules(void)
{
    SifInitRpc(0);
    /* Own the IOP lifecycle before creating any pad/audio RPC handles.
     * Embedded assets do not require the launcher's USB driver.
     */
    while (!SifIopReset("", 0)) { }
    while (!SifIopSync()) { }
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
    int buffer;

    for (buffer = 0; buffer < 2; buffer++) {
        frame[buffer].width = SCREEN_W;
        frame[buffer].height = SCREEN_H;
        frame[buffer].mask = 0;
        frame[buffer].psm = FRAME_PSM;
        frame[buffer].address = graph_vram_allocate(SCREEN_W, SCREEN_H,
                                                    FRAME_PSM, GRAPH_ALIGN_PAGE);
    }
    /* Never trade a picture for a smoother one. If graphics memory cannot hold
     * the second buffer, fall back to the single-buffered behaviour, which at
     * least shows something rather than refusing to start. */
    if (frame[1].address == (unsigned int)-1 || frame[1].address == frame[0].address) {
        frame[1] = frame[0];
    } else {
        frame_count = 2;
        /* graph_initialize is about to display buffer 0, so the first frame is
         * drawn into buffer 1. Starting the other way round would tear once at
         * startup for no reason. */
        frame_draw = 1;
    }

    z.enable = DRAW_DISABLE;
    z.mask = 0;
    z.method = ZTEST_METHOD_ALLPASS;
    z.zsm = GS_ZBUF_32;
    z.address = 0;

    logo_tex.width = nc_logo_width;
    logo_tex.psm = GS_PSM_32;
    logo_tex.address = graph_vram_allocate(nc_logo_width, nc_logo_height,
                                           GS_PSM_32, GRAPH_ALIGN_PAGE);
    logo_tex.info.width = draw_log2(nc_logo_width);
    logo_tex.info.height = draw_log2(nc_logo_height);
    logo_tex.info.components = TEXTURE_COMPONENTS_RGBA;
    logo_tex.info.function = TEXTURE_FUNCTION_DECAL;

    ui_skin_tex.width = nc_ui_skin_width;
    ui_skin_tex.psm = GS_PSM_32;
    ui_skin_tex.address = graph_vram_allocate(nc_ui_skin_width, nc_ui_skin_height,
                                               GS_PSM_32, GRAPH_ALIGN_PAGE);
    ui_skin_tex.info.width = draw_log2(nc_ui_skin_width);
    ui_skin_tex.info.height = draw_log2(nc_ui_skin_height);
    ui_skin_tex.info.components = TEXTURE_COMPONENTS_RGBA;
    ui_skin_tex.info.function = TEXTURE_FUNCTION_DECAL;

    font_tex.width = nc_font_width;
    font_tex.psm = GS_PSM_32;
    font_tex.address = graph_vram_allocate(nc_font_width, (nc_font_height + 31) & ~31,
                                           GS_PSM_32, GRAPH_ALIGN_PAGE);
    font_tex.info.width = draw_log2(nc_font_width);
    font_tex.info.height = draw_log2(nc_font_height);
    font_tex.info.components = TEXTURE_COMPONENTS_RGBA;
    font_tex.info.function = TEXTURE_FUNCTION_DECAL;

    graph_initialize(frame[0].address, SCREEN_W, SCREEN_H, FRAME_PSM, 0, 0);
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


static const signed char dither_matrix[16] = {
    -4,  2, -3,  3,
     0, -2,  1, -1,
    -3,  3, -4,  2,
     1, -1,  0, -2
};


static void init_environment(void)
{
    qword_t *q = packet->data;
    atest_t atest;
    dtest_t dtest;
    ztest_t ztest;
    lod_t lod;

    q = draw_setup_environment(q, 0, &frame[0], &z);
    q = draw_primitive_xyoffset(q, 0, 2048 + OFF_X, 2048 + OFF_Y);

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

    /* 16-bit colour is 5 bits a channel. Dithering spends a little spatial
     * noise to buy back the missing levels, which is the difference between a
     * gradient that steps and one that does not. This is the standard 4x4
     * matrix from the GS documentation. */
    q = draw_dither_matrix(q, (char *)dither_matrix);
    q = draw_dithering(q, 1);

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
    int width = nc_logo_used_w * height * NC_LOGO_SCALE_X / (nc_logo_used_h * 100);

    q = bind_texture(q, &logo_tex);
    return sprite(q, x, y, width, height, 0, 0,
                  nc_logo_used_w, nc_logo_used_h, 0x80);
}


static int logo_width_for(int height)
{
    return nc_logo_used_w * height * NC_LOGO_SCALE_X / (nc_logo_used_h * 100);
}


static qword_t *draw_title(qword_t *q, int frames)
{
    int height = 176;

    q = logo(q, (SCREEN_W - logo_width_for(height)) / 2, 48, height);

    q = text_center(q, 272, NC_VN_TITLE, 0x80);
    q = text_center(q, 300, NC_VN_SUBTITLE, 0x80);

    /* Blink, so it reads as waiting rather than frozen. */
    if ((frames % 60) < 40)
        q = text_center(q, 372, "PRESS START", 0x80);

    return q;
}

static qword_t *ui_skin(qword_t *q, int x, int y, int w, int h)
{
    q = bind_texture(q, &ui_skin_tex);
    return sprite(q, x, y, w, h, 0, 0,
                  nc_ui_skin_used_w, nc_ui_skin_used_h, 0x80);
}

static qword_t *draw_boot(qword_t *q, int scene)
{
    if (scene == SCENE_INIT) return text_center(q, 214, "INITIALIZING...", 0x80);
    if (scene == SCENE_SPLASH) {
        q = logo(q, (SCREEN_W - logo_width_for(176)) / 2, 72, 176);
        return text_center(q, 376, "UNOFFICIAL HOMEBREW SOFTWARE", 0x60);
    }
    q = text_center(q, 196, "INTRO / VIDEO SLOT", 0x80);
    return text_center(q, 226, "START: SKIP", 0x48);
}


static qword_t *draw_menu(qword_t *q, int selected)
{
    int i;
    int height = 80;

    q = ui_skin(q, 132, 154, 376, 190);
    q = logo(q, 32, 36, height);
    q = text(q, 48 + logo_width_for(height), 64, "NEON COFFEE", 0x80);

    for (i = 0; i < NC_UI_MENU_COUNT; i++) {
        int y = 200 + i * 40;
        if (i == selected) {
            q = panel(q, 140, y - 6, 360, 28, 0x2e, 0x36, 0x39);
            q = text(q, 156, y, ">", 0x80);
        }
        /* The unselected items are drawn dimmer rather than in another colour:
         * one texture, one palette, and the eye still knows where it is. */
        q = text(q, 184, y, NC_UI_MENU_LABELS[i], i == selected ? 0x80 : 0x48);
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

    for (i = (shown > 11 ? shown - 11 : 0); i < shown && i < count; i++)
        q = text(q, 56, 120 + (i - (shown > 11 ? shown - 11 : 0)) * 20, lines[i], 0x80);

    q = text_center(q, SCREEN_H - 56, footer, 0x40);
    return q;
}


#include "vn_runtime.h"
static int nc_requested_room=-1,nc_request_menu,nc_request_inventory,nc_request_level=-1,nc_vn_scene=-1;
static void nc_action(int action,int value) {
    if(action==4) nc_requested_room=value;
    if(action==6) nc_request_menu=1;
    if(action==7) nc_request_inventory=1;
    if(action==8) nc_request_level=value;
}
#include "nc_events.h"


/* ---- pause and options ------------------------------------------------- */
/* START opens this from anywhere, including mid-conversation, and it draws over
 * whatever was underneath rather than replacing it, so pausing never costs you
 * your place. */

enum { OPT_MUSIC, OPT_SFX, OPT_TRACK, OPT_SPEED, OPT_TEST, OPT_RESUME,
       OPT_TITLE, OPT_COUNT };

static int option_selected;
static int option_test_family;      /* which family the sound test is walking */

static const char *const OPTION_NAMES[OPT_COUNT] = {
    "MUSIC VOLUME", "EFFECT VOLUME", "MUSIC TRACK", "TEXT SPEED",
    "SOUND TEST", "RESUME", "RETURN TO TITLE"
};


static void option_value(int row, char *out)
{
    int i = 0;
    switch (row) {
    case OPT_MUSIC:
    case OPT_SFX: {
        /* A ten-segment bar reads faster than a number at television distance. */
        int level = (row == OPT_MUSIC ? nc_music_volume : nc_sfx_volume) / 10;
        for (i = 0; i < 10; i++)
            out[i] = i < level ? '=' : '-';
        out[10] = 0;
        return;
    }
    case OPT_TRACK:
        if (NC_MUSIC_COUNT <= 0) { strcpy(out, "NONE"); return; }
        if (nc_music_track < 0) { strcpy(out, "OFF"); return; }
        strncpy(out, nc_music[nc_music_track].name, 20);
        out[20] = 0;
        return;
    case OPT_SPEED:
        strcpy(out, text_speed <= 1 ? "FAST" : text_speed <= 3 ? "NORMAL" : "SLOW");
        return;
    case OPT_TEST:
        if (NC_FAMILY_COUNT <= 0) { strcpy(out, "NONE"); return; }
        strncpy(out, nc_families[option_test_family].name, 20);
        out[20] = 0;
        return;
    default:
        out[0] = 0;
    }
}


static qword_t *draw_options(qword_t *q)
{
    char value[24];
    int i;

    q = panel(q, 64, 48, SCREEN_W - 128, SCREEN_H - 128, 0x0a, 0x0c, 0x12);
    q = panel(q, 64, 48, SCREEN_W - 128, 2, 0x5f, 0xd4, 0xd0);
    q = text_center(q, 66, "PAUSED", 0x80);

    for (i = 0; i < OPT_COUNT; i++) {
        int y = 110 + i * 30;
        int bright = i == option_selected ? 0x80 : 0x44;
        q = text(q, 96, y, i == option_selected ? ">" : " ", bright);
        q = text(q, 120, y, OPTION_NAMES[i], bright);
        option_value(i, value);
        if (value[0])
            q = text(q, 360, y, value, bright);
    }

    if (option_selected == OPT_TEST) {
        char label[36];
        int index = nc_families[option_test_family].first
                  + (nc_family_cursor[option_test_family]
                     % nc_families[option_test_family].count);
        sprintf(label, "%d OF %d",
                (nc_family_cursor[option_test_family]
                 % nc_families[option_test_family].count) + 1,
                nc_families[option_test_family].count);
        q = text_center(q, SCREEN_H - 116, label, 0x50);
        q = text_center(q, SCREEN_H - 96, nc_sfx[index].name, 0x50);
    }
    q = text_center(q, SCREEN_H - 74, "LEFT / RIGHT ADJUST   X PLAY", 0x40);
    q = text_center(q, SCREEN_H - 54, "START OR TRIANGLE CLOSE", 0x40);
    return q;
}


/* Returns 0 when the pause screen should close, -1 to leave for the title. */
static int options_update(unsigned int pressed)
{
    int step = 0;

    if (pressed & PAD_UP)
        option_selected = (option_selected + OPT_COUNT - 1) % OPT_COUNT;
    if (pressed & PAD_DOWN)
        option_selected = (option_selected + 1) % OPT_COUNT;
    if (pressed & (PAD_UP | PAD_DOWN))
        nc_sfx_family(nc_role_move);

    if (pressed & PAD_LEFT) step = -1;
    if (pressed & PAD_RIGHT) step = 1;

    if (step) {
        switch (option_selected) {
        case OPT_MUSIC:
            nc_music_volume += step * 10;
            if (nc_music_volume < 0) nc_music_volume = 0;
            if (nc_music_volume > 100) nc_music_volume = 100;
            break;
        case OPT_SFX:
            nc_sfx_volume += step * 10;
            if (nc_sfx_volume < 0) nc_sfx_volume = 0;
            if (nc_sfx_volume > 100) nc_sfx_volume = 100;
            nc_sfx_family(nc_role_confirm);   /* so the level can be heard */
            break;
        case OPT_TRACK:
            if (NC_MUSIC_COUNT > 0)
                nc_music_play(nc_music_track + step);
            break;
        case OPT_SPEED:
            text_speed -= step;             /* right is faster */
            if (text_speed < 1) text_speed = 1;
            if (text_speed > 6) text_speed = 6;
            break;
        case OPT_TEST:
            if (NC_FAMILY_COUNT > 0)
                option_test_family = (option_test_family + step + NC_FAMILY_COUNT)
                                   % NC_FAMILY_COUNT;
            break;
        default:
            break;
        }
    }

    if (pressed & PAD_CROSS) {
        switch (option_selected) {
        case OPT_TEST:
            nc_sfx_family(option_test_family);
            break;
        case OPT_RESUME:
            return 0;
        case OPT_TITLE:
            return -1;
        default:
            break;
        }
    }
    if (pressed & (PAD_START | PAD_TRIANGLE))
        return 0;
    return 1;
}


/* ---- main -------------------------------------------------------------- */

#include "nc_lab.h"


int main(void)
{
    struct padButtonStatus pad;
    unsigned int buttons = 0, last = 0, pressed;
    int have_pad = 0, state;

    int scene = SCENE_INIT;
    int selected = 0;
    int inventory_selected = 0;
    int inventory_return_scene = SCENE_MENU;
    int frames = 0;
    int limit_qwords;

    /* Initialize GIF and select it for dma_wait_fast, as in PS2SDK samples. */
    dma_channel_initialize(DMA_CHANNEL_GIF, NULL, 0);
    dma_channel_fast_waits(DMA_CHANNEL_GIF);

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

    /* Ask for a generous packet, but never stop dead if it cannot be had. A
     * console that hangs at startup is indistinguishable from a crash, and a
     * smaller packet still draws most of a frame. */
    limit_qwords = DRAW_QWORDS;
    packet = packet_init(limit_qwords, PACKET_NORMAL);
    if (packet == NULL) {
        limit_qwords = 1024;
        packet = packet_init(limit_qwords, PACKET_NORMAL);
        printf("@NAME@: large packet refused, using %d qwords\n", limit_qwords);
    }
    if (packet == NULL) {
        printf("@NAME@: no draw packet at all\n");
        return 1;
    }
    packet_limit = packet->data + limit_qwords;
    init_gs();
    init_environment();

    upload(nc_logo, nc_logo_width, nc_logo_height, &logo_tex);
    upload(nc_ui_skin, nc_ui_skin_width, nc_ui_skin_height, &ui_skin_tex);
    upload(nc_font, nc_font_width, nc_font_height, &font_tex);
    nc_world_upload();
    nc_lab_init();
    if (!vn_init()) return 1;
    text_speed = VN_SPEED;

    nc_events(1,0,-1);
    while (1) {
        qword_t *q;

        nc_lab_frame_begin();

        if (have_pad && padRead(0, 0, &pad) != 0)
            buttons = 0xFFFF ^ pad.btns;    /* the pad reports active-low */
        pressed = buttons & ~last;
        last = buttons;

        /* Shoulder buttons change track wherever you are -- it is the kind of
         * thing you want to do while reading, not from a menu. */
        if (scene != SCENE_PAUSE && NC_MUSIC_COUNT > 1) {
            if (pressed & PAD_L1) nc_music_play(nc_music_track - 1);
            if (pressed & PAD_R1) nc_music_play(nc_music_track + 1);
        }
        if (scene != SCENE_PAUSE && scene != SCENE_TITLE && (pressed & PAD_START)) {
            scene_before_pause = scene;
            scene = SCENE_PAUSE;
            option_selected = OPT_RESUME;
            nc_sfx_family(nc_role_shift);
            pressed = 0;                /* do not also act on it below */
        }

        switch (scene) {
        case SCENE_INIT:
            if (frames >= 30) scene = SCENE_SPLASH;
            break;
        case SCENE_SPLASH:
            if (frames >= 180 || (pressed & (PAD_START | PAD_CROSS))) scene = SCENE_INTRO;
            break;
        case SCENE_INTRO:
            if (frames >= 330 || (pressed & (PAD_START | PAD_CROSS))) scene = SCENE_TITLE;
            break;
        case SCENE_PAUSE: {
            int verdict = options_update(pressed);
            if (verdict == 0) {
                scene = scene_before_pause;
                nc_sfx_family(nc_role_shift);
            } else if (verdict < 0) {
                scene = SCENE_TITLE;
                nc_sfx_family(nc_role_shift);
            }
            break;
        }

        case SCENE_TITLE:
            if (pressed & (PAD_START | PAD_CROSS)) {
                scene = SCENE_MENU;
                selected = 0;
                nc_sfx_family(nc_role_confirm);
            }
            break;

        case SCENE_MENU:
            if (pressed & PAD_UP)
                selected = (selected + NC_UI_MENU_COUNT - 1) % NC_UI_MENU_COUNT;
            if (pressed & PAD_DOWN)
                selected = (selected + 1) % NC_UI_MENU_COUNT;
            if (pressed & (PAD_UP | PAD_DOWN))
                nc_sfx_family(nc_role_move);
            if (pressed & PAD_TRIANGLE) {
                scene = SCENE_TITLE;
                nc_sfx_family(nc_role_shift);
            }
            if (pressed & PAD_CROSS) {
                int action = NC_UI_MENU_ACTIONS[selected];
                nc_sfx_family(nc_role_confirm);
                if (action == NC_UI_LOAD_WORLD3D) scene = SCENE_WORLD3D;
                else if (action == NC_UI_LOAD_VN) { scene = SCENE_STORY; vn_begin(); }
                else if (action == NC_UI_LOAD_LAB) { scene = SCENE_UI_LAB; inventory_selected = 0; }
                else if (action == NC_UI_OPTIONS) { scene_before_pause = SCENE_MENU; scene = SCENE_PAUSE; option_selected = OPT_RESUME; }
                else scene = SCENE_TITLE;
            }
            break;

        case SCENE_STORY:
            if (pressed & PAD_SQUARE) { inventory_return_scene=SCENE_STORY; scene=SCENE_UI_LAB; }
            if (!vn_update(pressed)) scene = SCENE_MENU;
            break;

        case SCENE_WORLD3D:
            {   /* A count reads; a bit mask does not. */
                unsigned int bag = vn_inventory;
                for (nc_persist.carried = 0; bag; bag &= bag - 1)
                    nc_persist.carried++;
            }
            nc_world_animate();
            /* The lab swallows the pad while its menu is open, so adjusting a
             * row never also walks the character off the edge of the world. */
            if (!nc_lab_update(pressed, buttons)) {
                if (pressed & PAD_SQUARE) { inventory_return_scene=SCENE_WORLD3D; scene=SCENE_UI_LAB; }
                if (pressed & PAD_TRIANGLE) scene = SCENE_MENU;
            }
            break;

        case SCENE_UI_LAB:
            if (pressed & PAD_LEFT && inventory_selected % 4) inventory_selected--;
            if (pressed & PAD_RIGHT && inventory_selected % 4 < 3) inventory_selected++;
            if (pressed & PAD_UP && inventory_selected >= 4) inventory_selected -= 4;
            if (pressed & PAD_DOWN && inventory_selected < 8) inventory_selected += 4;
            if (pressed & (PAD_LEFT|PAD_RIGHT|PAD_UP|PAD_DOWN)) nc_sfx_family(nc_role_move);
            if (pressed & PAD_TRIANGLE) { scene=inventory_return_scene; nc_sfx_family(nc_role_shift); }
            break;

        case SCENE_ABOUT:
            if (pressed & (PAD_CROSS | PAD_TRIANGLE))
                scene = SCENE_MENU;
            break;
        }

        q = packet->data;
        bound = 0;
        /* Point the GS at whichever buffer is not on screen. The environment
         * is set up once; only the destination changes each frame. */
        q = draw_framebuffer(q, 0, &frame[frame_draw]);
        q = draw_clear(q, 0, OFF_X, OFF_Y, SCREEN_W, SCREEN_H,
                       BG_R, BG_G, BG_B);

        /* Diagnostic marker: absence alone cannot identify a stale binary. */


        nc_vn_scene=(scene==SCENE_STORY && vn_current>=0)?vn_lines[vn_current].scene:-1;
        nc_events(0,pressed,-1);
        if(nc_requested_room>=0) {
            int i;
            for(i=0;i<(int)(sizeof(vn_lines)/sizeof(vn_lines[0]));i++) {
                if(vn_lines[i].scene==nc_requested_room) {vn_enter(i);scene=SCENE_STORY;break;}
            }
            nc_requested_room=-1;
        }
        if(nc_request_menu) {scene=SCENE_MENU;nc_request_menu=0;}
        if(nc_request_inventory) {inventory_return_scene=scene;scene=SCENE_UI_LAB;nc_request_inventory=0;}
        if(nc_request_level>=0) {scene=nc_request_level==0?SCENE_WORLD3D:nc_request_level==1?SCENE_STORY:SCENE_UI_LAB;if(scene==SCENE_STORY)vn_begin();nc_request_level=-1;}
        switch (scene == SCENE_PAUSE ? scene_before_pause : scene) {
        case SCENE_INIT:
        case SCENE_SPLASH:
        case SCENE_INTRO:
            q = draw_boot(q, scene);
            break;
        case SCENE_TITLE:
            q = draw_title(q, frames);
            break;
        case SCENE_MENU:
            q = draw_menu(q, selected);
            break;
        case SCENE_WORLD3D:
            /* The 2D layer goes down before the world, which is the whole
             * point of it: it measures full-screen overdraw arriving before
             * anything else is drawn. */
            q = nc_lab_backdrop(q);
            q = nc_world_draw(q);
            /* The world is drawn first and the readout over it, so the numbers
             * describe the frame underneath them. */
            q = nc_lab_draw(q);
            break;
        case SCENE_STORY:
            q = vn_draw(q);
            q = text(q, 24, 22, "VISUAL NOVEL LAB", 0x48);
            break;
        case SCENE_UI_LAB: {
            static const char *const item[4]={"KEY","COFFEE","RELIC","MAP"};
            int i;
            q=panel(q,120,44,400,340,0x0a,0x0c,0x12);
            q=ui_skin(q,176,50,288,80);
            q=text_center(q,66,"GRID INVENTORY",0x80);
            for(i=0;i<12;i++) {
                int x=150+(i%4)*84,y=116+(i/4)*72;
                q=panel(q,x,y,72,60,i==inventory_selected?0x38:0x18,i==inventory_selected?0x48:0x20,i==inventory_selected?0x48:0x24);
                if(i<4) q=text(q,x+8,y+22,item[i],i==inventory_selected?0x80:0x50);
            }
            q=text_center(q,402,"D-PAD SELECT   TRIANGLE BACK",0x48);
            break;
        }
        case SCENE_ABOUT:
            q = draw_lines(q, ABOUT, ABOUT_LINES, ABOUT_LINES,
                           "X BACK");
            break;
        }
        if (scene == SCENE_PAUSE)
            q = draw_options(q);

        /* Visible until the audio is running. On a console there is no TTY to
         * read, so the stage has to be on the television or it may as well not
         * be recorded at all. */
        if (nc_audio_step != NC_AUDIO_DONE) {
            char line[48];
            sprintf(line, "AUDIO %d/9 %s%s", nc_audio_step + 1,
                    NC_AUDIO_STAGE[nc_audio_step],
                    nc_audio_step == NC_AUDIO_FAILED ? "" : " ...");
            q = text(q, 24, SCREEN_H - 26, line, 0x80);
            if (nc_audio_step == NC_AUDIO_FAILED) {
                sprintf(line, "AT %s  CODE %d", NC_AUDIO_STAGE[nc_audio_failed_at],
                        nc_audio_detail);
                q = text(q, 24, SCREEN_H - 46, line, 0x80);
            }
        }

        q = draw_finish(q);
        nc_lab_draw_end();

        dma_wait_fast();
        dma_channel_send_normal(DMA_CHANNEL_GIF, packet->data,
                                q - packet->data, 0, 0);
        draw_wait_finish();
        graph_wait_vsync();

        /* Show the buffer that was just finished and start drawing into the
         * other one. Swapping after vsync means the display address never
         * changes part-way down a field. */
        if (frame_count == 2) {
            graph_set_framebuffer_filtered(frame[frame_draw].address,
                                           SCREEN_W, FRAME_PSM, 0, 0);
            frame_draw ^= 1;
        }

        /* Sound starts once a picture is already on screen, one step per frame.
         * Bringing up the IOP's audio driver touches the only part of this
         * program that can hang a console outright, and the stage is drawn
         * before the step runs -- so whatever is on screen when it stops is
         * the thing that stopped it. */
        if (frames > 2 && nc_audio_busy()) {
            nc_audio_advance();
            if (!nc_audio_busy() && nc_audio_step == NC_AUDIO_DONE)
                nc_music_play(0);
        }
        nc_audio_pump();
        frames++;
    }

    packet_free(packet);
    return 0;
}
