"""Bounded conversation graph and PS2 texture compiler. No gameplay interpreter."""
import json
import textwrap
from pathlib import Path


def compile_kit(root, doc):
    root = Path(root).resolve()
    kit = doc.get('kit', {})
    characters = kit.get('characters', [])
    scenes = kit.get('scenes', [])
    items = kit.get('items', [])
    nodes = kit.get('dialogue', [])
    def table(rows, kind, maximum):
        if not isinstance(rows, list) or len(rows) > maximum:
            raise ValueError(f'{kind}: maximum {maximum} entries')
        result = {}
        for i, row in enumerate(rows):
            name = row.get('id', '')
            if not isinstance(name, str) or not name or name in result:
                raise ValueError(f'{kind}: missing or duplicate id {name!r}')
            result[name] = i
        return result
    chars = table(characters, 'characters', 16)
    locs = table(scenes, 'scenes', 32)
    inv = table(items, 'items', 16)
    graph = table(nodes, 'dialogue', 128)
    if not nodes or not scenes:
        raise ValueError('kit needs at least one scene and dialogue entry')
    def ref(mapping, value, label, optional=True):
        if optional and not value:
            return -1
        if value not in mapping:
            raise ValueError(f'{label}: unknown reference {value!r}')
        return mapping[value]
    def string(value, limit, label):
        if not isinstance(value, str) or len(value) > limit or any(ord(c)<32 or ord(c)>126 for c in value):
            raise ValueError(f'{label}: use at most {limit} printable ASCII characters')
        return json.dumps(value)
    assets = []
    asset_ids = {}
    total = 0
    def asset(path):
        nonlocal total
        if not path:
            return -1
        if path in asset_ids:
            return asset_ids[path]
        from PIL import Image
        source = (root / path).resolve()
        if not source.is_relative_to(root):
            raise ValueError(f'asset {path}: must be inside the project')
        with Image.open(source) as img:
            if img.width > 512 or img.height > 512:
                raise ValueError(f'{path}: {img.width}x{img.height}; resize to at most 512x512')
            rgba = img.convert('RGBA')
            w, h = rgba.size
            pw, ph = 1 << (w-1).bit_length(), 1 << (h-1).bit_length()
            cost = max(64,pw)*max(32,ph)*4
            total += cost
            if total > 2*1024*1024 or len(assets) >= 16:
                # The number that matters is the padded one, and it is invisible
                # from the file listing: a 432x321 background pads to 512x512 and
                # costs a full megabyte, four times what its pixels suggest.
                waste = 100 - (w*h*100)//(pw*ph)
                advice = (' Its %dx%d pixels occupy a %dx%d texture, so %d%% of '
                          'what it costs is padding.' % (w, h, pw, ph, waste)
                          if waste >= 20 else '')
                # The largest image that still lands in a cheaper padded box.
                # Cheapest is not the useful answer -- the point is to lose as
                # little of the artwork as possible while getting under budget.
                best = None
                for bw, bh in ((pw//2, ph), (pw, ph//2), (pw//2, ph//2)):
                    if bw < 1 or bh < 1:
                        continue
                    ratio = min(bw/float(w), bh/float(h))
                    nw, nh = max(1, int(w*ratio)), max(1, int(h*ratio))
                    price = (max(64, 1 << (nw-1).bit_length())
                             * max(32, 1 << (nh-1).bit_length()) * 4)
                    if price < cost and (best is None or nw*nh > best[0]*best[1]):
                        best = (nw, nh, price)
                if best:
                    advice += (' Scaling it to %dx%d would cost %d KiB instead of %d.'
                               % (best[0], best[1], best[2]//1024, cost//1024))
                raise ValueError(
                    'VN textures do not fit: %s needs %d KiB, taking the total to '
                    '%d KiB of the 2048 KiB budget (%d textures of 16).%s'
                    % (path, cost//1024, total//1024, len(assets)+1, advice))
            words = [0]*(pw*ph)
            for y in range(h):
                for x in range(w):
                    r,g,b,a = rgba.getpixel((x,y))
                    words[y*pw+x] = ((0x80<<24)|(b<<16)|(g<<8)|r) if a >= 128 else 0
        index = len(assets)
        assets.append((pw,ph,w,h,words))
        asset_ids[path] = index
        return index
    char_rows = []
    for row in characters:
        char_rows.append('{%s,%d}' % (string(row.get('name',row['id']),24,'character name'),asset(row.get('portrait',''))))
    scene_rows = []
    for row in scenes:
        color = row.get('color',[20,24,26])
        if not isinstance(color,list) or len(color)!=3 or any(type(v)!=int or not 0<=v<=255 for v in color):
            raise ValueError('scene color must contain three integers from 0 to 255')
        scene_rows.append('{%d,%d,%d,%d}' % (asset(row.get('background','')),*color))
    item_rows = [string(row.get('name',row['id']),24,'item name') for row in items]
    # Named portrait slots. One character on screen at a time is the limit that
    # makes a two-hander impossible, so a scene owns an ordered list of slots and
    # a line says who stands in which. Array order is draw order: later entries
    # are in front, which is what the ROOM list reorders.
    layout = kit.get('layout', {})
    slots = layout.get('portraits')
    if not slots:
        slots = [{'name': 'main', 'rect': layout.get('portrait', [32, 24, 128, 224])}]
    if not isinstance(slots, list) or not 1 <= len(slots) <= 4:
        raise ValueError('layout portraits: supply 1 to 4 named slots')
    slot_ids = {}
    for i, slot in enumerate(slots):
        name = slot.get('name', '')
        if not isinstance(name, str) or not name or name in slot_ids:
            raise ValueError(f'portrait slot: missing or duplicate name {name!r}')
        rect = slot.get('rect', [32, 24, 128, 224])
        if not isinstance(rect, list) or len(rect) != 4 or any(type(v) is not int for v in rect):
            raise ValueError(f'portrait slot {name}: expected integer x,y,width,height')
        x, y, w, h = rect
        if x < 0 or y < 0 or w < 16 or h < 16 or x + w > 640 or y + h > 448:
            raise ValueError(f'portrait slot {name}: rectangle must fit the 640x448 screen')
        slot_ids[name] = i

    node_rows = []
    for row in nodes:
        raw = row.get('text','')
        string(raw,256,'dialogue '+row['id'])
        wrapped = textwrap.wrap(raw,32) or ['']
        if len(wrapped)>4:
            raise ValueError(f'dialogue {row["id"]}: exceeds four wrapped lines; split into another entry')
        choices = row.get('choices',[])
        if not isinstance(choices,list) or len(choices)>2:
            raise ValueError('maximum two choices per entry')
        options=[]
        for c in choices:
            options.append('{%s,%d,%d,%d}' % (string(c.get('text',''),24,'choice'),
                ref(graph,c.get('next'),'choice next',False),ref(inv,c.get('requires'),'choice requires'),ref(inv,c.get('give'),'choice give')))
        options += ['{"",-1,-1,-1}']*(2-len(options))
        cast = row.get('cast', [])
        if not isinstance(cast, list) or len(cast) > 4:
            raise ValueError(f'dialogue {row["id"]}: at most four characters on screen')
        placed = []
        for member in cast:
            slot = member.get('slot', '')
            if slot not in slot_ids:
                raise ValueError(f'dialogue {row["id"]}: unknown portrait slot {slot!r}')
            if any(slot_ids[slot] == taken for taken, _ in placed):
                raise ValueError(f'dialogue {row["id"]}: two characters in slot {slot!r}')
            placed.append((slot_ids[slot],
                           ref(chars, member.get('character'), 'cast character', False)))
        if not placed and row.get('speaker'):
            # Content written before slots existed: the speaker stands in the
            # first slot, which is exactly what the old runtime did.
            placed.append((0, ref(chars, row['speaker'], 'speaker', False)))
        # Sorted by slot so that array order is draw order and slot order is
        # layer order. Reordering the slot list in ROOM then means what it looks
        # like it means: moving a character in front of or behind another.
        placed.sort()
        count = len(placed)
        stage = ['{%d,%d}' % pair for pair in placed]
        stage += ['{-1,-1}']*(4-len(stage))
        node_rows.append('{%s,%d,%d,%d,%d,%d,{%s},%d,{%s}}' % (json.dumps('\n'.join(wrapped)),
            ref(chars,row.get('speaker'),'speaker'),ref(locs,row.get('scene'),'scene',False),
            ref(graph,row.get('next'),'next'),ref(inv,row.get('give'),'give'),len(choices),','.join(options),
            count, ','.join(stage)))
    speed=kit.get('frames_per_character',2)
    if type(speed)!=int or not 1<=speed<=10:
        raise ValueError('frames_per_character must be 1–10')
    entry=ref(graph,kit.get('start',nodes[0]['id']),'start',False)
    lines=['/* Generated VN kit; edit vn.json or Godot resources. */',
        'typedef struct { const char *name; int portrait; } VNCharacter;',
        'typedef struct { int background,r,g,b; } VNScene;',
        'typedef struct { const char *text; int next,requires,give; } VNChoice;',
        'typedef struct { int slot, character; } VNCast;',
        'typedef struct { int x,y,w,h; } VNRect;',
        'typedef struct { const char *text; int speaker,scene,next,give,count; VNChoice choices[2]; int cast_count; VNCast cast[4]; } VNLine;',
        'typedef struct { unsigned int *pixels; int w,h,used_w,used_h; } VNAsset;',
        f'#define VN_START {entry}',f'#define VN_SPEED {speed}',f'#define VN_ITEM_COUNT {len(items)}',f'#define VN_ASSET_COUNT {len(assets)}',
        'static const VNCharacter vn_characters[] = {'+','.join(char_rows or ['{"",-1}'])+'};',
        'static const VNScene vn_scenes[] = {'+','.join(scene_rows)+'};',
        'static const char *vn_items[] = {'+','.join(item_rows or ['""'])+'};',
        'static const VNLine vn_lines[] = {'+','.join(node_rows)+'};',
        f'#define VN_SLOT_COUNT {len(slots)}',
        'static const VNRect vn_slots[] = {'+','.join('{%d,%d,%d,%d}' % tuple(s.get('rect',[32,24,128,224])) for s in slots)+'};']
    for i,(w,h,uw,uh,words) in enumerate(assets):
        lines.append(f'static unsigned int vn_pixels_{i}[{len(words)}] __attribute__((aligned(16))) = {{')
        lines.extend(','.join(hex(v) for v in words[j:j+16])+',' for j in range(0,len(words),16))
        lines.append('};')
    lines.append('static const VNAsset vn_assets[] = {'+','.join(f'{{vn_pixels_{i},{w},{h},{uw},{uh}}}' for i,(w,h,uw,uh,_) in enumerate(assets))+'};' if assets else 'static const VNAsset vn_assets[1] = {{0,0,0,0,0}};')
    for key, fallback in [('background',[0,0,640,448]),('portrait',[32,24,128,224]),('dialogue',[32,232,576,168])]:
        rect = layout.get(key, fallback)
        if not isinstance(rect,list) or len(rect)!=4 or any(type(v)!=int for v in rect):
            raise ValueError(f'layout {key}: expected integer x,y,width,height')
        x,y,w,h=rect
        if x<0 or y<0 or w<16 or h<16 or x+w>640 or y+h>448:
            raise ValueError(f'layout {key}: rectangle must fit the 640x448 screen')
        if key=='dialogue' and (w<544 or h<168):
            raise ValueError('dialogue needs at least 544x168 for four lines and choices')
        for suffix,value in zip(('X','Y','W','H'),rect):
            lines.append(f'#define VN_{key.upper()}_{suffix} {value}')
    target=root/'src/vn_kit.h'
    content='\n'.join(lines)+'\n'
    if not target.exists() or target.read_text()!=content:
        target.write_text(content)
    print(f'  VN: {len(nodes)} dialogue entries, {len(characters)} characters, {len(scenes)} scenes, {len(items)} items; textures {total//1024}/2048 KiB')
