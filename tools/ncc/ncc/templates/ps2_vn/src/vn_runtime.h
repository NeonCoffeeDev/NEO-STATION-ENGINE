/* Small data-driven conversation player. Included after the drawing helpers. */
#include "vn_kit.h"
static texbuffer_t vn_textures[16];
static int vn_current, vn_reveal, vn_tick, vn_selection, vn_inventory_open;
static unsigned int vn_inventory;

static int vn_init(void)
{
    int i;
    for (i=0;i<VN_ASSET_COUNT;i++) {
        texbuffer_t *t=&vn_textures[i];
        const VNAsset *a=&vn_assets[i];
        t->width=a->w<64?64:a->w; t->psm=GS_PSM_32;
        t->address=graph_vram_allocate(t->width,(a->h+31)&~31,GS_PSM_32,GRAPH_ALIGN_PAGE);
        if (t->address == (unsigned int)-1) return 0;
        t->info.width=draw_log2(a->w); t->info.height=draw_log2(a->h);
        t->info.components=TEXTURE_COMPONENTS_RGBA;
        t->info.function=TEXTURE_FUNCTION_DECAL;
        upload(a->pixels,a->w,a->h,t);
    }
    return 1;
}

static void vn_enter(int index)
{
    vn_current=index; vn_reveal=0; vn_tick=0; vn_selection=0;
    if (index>=0 && vn_lines[index].give>=0)
        vn_inventory |= 1u << vn_lines[index].give;
}

static void vn_begin(void)
{
    vn_inventory=0; vn_inventory_open=0; vn_enter(VN_START);
}

/* Returns false when the conversation ends or TRIANGLE returns to menu. */
static int vn_update(unsigned int pressed)
{
    const VNLine *line=&vn_lines[vn_current];
    int length=(int)strlen(line->text);
    if (pressed & PAD_SQUARE) vn_inventory_open=!vn_inventory_open;
    if (vn_inventory_open) {
        if (pressed & PAD_TRIANGLE) vn_inventory_open=0;
        return 1;
    }
    if (pressed & PAD_TRIANGLE) return 0;
    if (++vn_tick>=VN_SPEED) {
        vn_tick=0;
        if (vn_reveal<length) vn_reveal++;
    }
    if (vn_reveal>=length && line->count) {
        if (pressed & PAD_UP) vn_selection=(vn_selection+line->count-1)%line->count;
        if (pressed & PAD_DOWN) vn_selection=(vn_selection+1)%line->count;
    }
    if (pressed & PAD_CROSS) {
        int next=line->next;
        if (vn_reveal<length) { vn_reveal=length; return 1; }
        if (line->count) {
            const VNChoice *c=&line->choices[vn_selection];
            if (c->requires>=0 && !(vn_inventory & (1u<<c->requires))) return 1;
            if (c->give>=0) vn_inventory |= 1u<<c->give;
            next=c->next;
        }
        if (next<0) return 0;
        vn_enter(next);
    }
    return 1;
}

static qword_t *vn_picture(qword_t *q,int id,int x,int y,int width,int height)
{
    const VNAsset *a;
    if (id<0) return q;
    a=&vn_assets[id];
    q=bind_texture(q,&vn_textures[id]);
    return sprite(q,x,y,width,height,0,0,a->used_w,a->used_h,0x80);
}

static qword_t *vn_draw(qword_t *q)
{
    const VNLine *line=&vn_lines[vn_current];
    const VNScene *location=&vn_scenes[line->scene];
    int i, row=0, column=0;
    char visible[33];
    q=panel(q,0,0,SCREEN_W,SCREEN_H,location->r,location->g,location->b);
    q=vn_picture(q,location->background,VN_BACKGROUND_X,VN_BACKGROUND_Y,VN_BACKGROUND_W,VN_BACKGROUND_H);
    /* The cast, in array order: later entries draw over earlier ones, so the
     * list order in ROOM is the layer order on screen. Each portrait keeps its
     * own aspect ratio and stands on the bottom edge of its slot, so characters
     * of different heights line up on the floor rather than at the top. */
    for (i=0;i<line->cast_count;i++) {
        const VNCast *member=&line->cast[i];
        const VNRect *slot;
        int portrait,w,h;
        if (member->slot<0 || member->slot>=VN_SLOT_COUNT || member->character<0)
            continue;
        portrait=vn_characters[member->character].portrait;
        if (portrait<0) continue;
        slot=&vn_slots[member->slot];
        h=slot->h; w=vn_assets[portrait].used_w*h/vn_assets[portrait].used_h;
        if (w>slot->w) { w=slot->w; h=vn_assets[portrait].used_h*w/vn_assets[portrait].used_w; }
        q=vn_picture(q,portrait,slot->x,slot->y+slot->h-h,w,h);
    }
    q=panel(q,VN_DIALOGUE_X,VN_DIALOGUE_Y,VN_DIALOGUE_W,VN_DIALOGUE_H,10,12,18);
    if (line->speaker>=0) q=text(q,VN_DIALOGUE_X+16,VN_DIALOGUE_Y+6,vn_characters[line->speaker].name,0x80);
    for (i=0;i<vn_reveal && line->text[i];i++) {
        if (line->text[i]=='\n') {
            visible[column]=0; q=text(q,VN_DIALOGUE_X+16,VN_DIALOGUE_Y+30+row*20,visible,0x80);
            row++;column=0;
        } else if (column<32) visible[column++]=line->text[i];
    }
    visible[column]=0; q=text(q,VN_DIALOGUE_X+16,VN_DIALOGUE_Y+30+row*20,visible,0x80);
    if (vn_reveal>=(int)strlen(line->text)) {
        for(i=0;i<line->count;i++) {
            const VNChoice *c=&line->choices[i];
            int locked=c->requires>=0 && !(vn_inventory & (1u<<c->requires));
            q=text(q,VN_DIALOGUE_X+16,VN_DIALOGUE_Y+116+i*20,locked?"!":(i==vn_selection?">":" "),0x80);
            q=text(q,VN_DIALOGUE_X+40,VN_DIALOGUE_Y+116+i*20,c->text,0x80);
        }
    }
    q=text(q,48,404,"X NEXT  SQUARE BAG  TRI MENU",0x80);
    if (vn_inventory_open) {
        q=panel(q,96,32,448,380,15,22,30);
        q=text(q,112,48,"INVENTORY",0x80);
        row=0;
        for(i=0;i<VN_ITEM_COUNT;i++) if(vn_inventory & (1u<<i))
            q=text(q,112,80+18*row++,vn_items[i],0x80);
        if(!row) q=text(q,112,80,"EMPTY",0x80);
        q=text(q,112,388,"SQUARE / TRI CLOSE",0x80);
    }
    return q;
}
