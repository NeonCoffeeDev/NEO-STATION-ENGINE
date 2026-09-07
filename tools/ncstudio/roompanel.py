"""Visual room layout over existing PS1 scenes and the PS2 VN kit."""
import copy
import json
import shutil
import textwrap
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
from PIL import Image, ImageTk
from theme import (BG, FG, CYAN, AMBER, DIM, GREEN, RED, SUNKEN, PANEL, BORDER,
                   MONO_SM, UI_BOLD, Button, dialog, entry, label)


class IdPicker(ttk.Combobox):
    """A dropdown over (id, label) pairs that never invents or loses an id.

    An id the kit no longer defines is shown as missing rather than quietly
    replaced with the first entry in the list: silently rewriting a dangling
    reference hides the very mistake the build is about to report.
    """

    def __init__(self, parent, pairs, width=26):
        super().__init__(parent, state='readonly', width=width)
        self._raw = ''
        self.set_pairs(pairs)

    def set_pairs(self, pairs):
        self.pairs = list(pairs)
        self['values'] = [text for _, text in self.pairs]

    def set_id(self, value):
        self._raw = value or ''
        for i, (raw, _) in enumerate(self.pairs):
            if raw == self._raw:
                self.current(i)
                return
        self.set('%s  (missing)' % value if value else '')

    def get_id(self):
        shown = self.get()
        for raw, text in self.pairs:
            if text == shown:
                return raw
        return self._raw


class RoomPanel(tk.Frame):
    def __init__(self, parent, on_log):
        super().__init__(parent, bg=BG)
        self.group = self
        self.log = on_log
        self.project = None
        self.doc = None
        self.history = []
        self.photos = []
        self.boxes = []
        self.selected = 0
        self.drag = None
        self.dirty = False
        bar = tk.Frame(self, bg=BG)
        bar.pack(fill='x')
        self.scene = ttk.Combobox(bar, state='readonly', width=24)
        self.scene.pack(side='left', padx=4)
        self.scene.bind('<<ComboboxSelected>>', lambda e: self.draw())
        Button(bar, 'SAVE ROOM', self.save, AMBER).pack(side='left', padx=4)
        Button(bar, 'UNDO', self.undo, CYAN).pack(side='left')
        Button(bar, 'RELOAD', self.reload, DIM).pack(side='left', padx=4)
        self.snap = tk.BooleanVar(value=True)
        tk.Checkbutton(bar, text='8px snap', variable=self.snap, bg=BG, fg=FG,
                       selectcolor=SUNKEN).pack(side='left')
        Button(bar, 'NEW ROOM', self.new_room, CYAN).pack(side='left', padx=4)
        self.note = tk.Label(self, bg=BG, fg=CYAN, anchor='w')
        self.note.pack(fill='x', padx=6)
        body = tk.Frame(self, bg=BG)
        body.pack(fill='both', expand=True)
        left = tk.Frame(body, bg=BG, width=210)
        left.pack(side='left', fill='y', padx=4)
        self.actor = ttk.Combobox(left, state='readonly', width=22)
        self.actor.pack(fill='x')
        self.actor.bind('<<ComboboxSelected>>', lambda e: self.draw())
        self.objects = tk.Listbox(left, bg=SUNKEN, fg=FG, exportselection=False, height=8)
        self.objects.pack(fill='both', expand=True)
        self.objects.bind('<<ListboxSelect>>', self.select)
        self.values = []
        for caption in ('X', 'Y', 'Width', 'Height'):
            row = tk.Frame(left, bg=BG); row.pack(fill='x')
            tk.Label(row, text=caption, width=7, bg=BG, fg=FG).pack(side='left')
            box = entry(row, width=9); box.pack(side='left'); self.values.append(box)
        # A HUD element is an ordinary sprite that does not move with the screen
        # shake. Without this flag exposed the only way to add one was to edit
        # scene.json by hand and know the flag existed.
        self.fixed = tk.BooleanVar(value=False)
        self.fixed_box = tk.Checkbutton(
            left, text='fixed  (HUD: ignores screen shake)', variable=self.fixed,
            command=self.toggle_fixed, bg=BG, fg=FG, selectcolor=SUNKEN,
            activebackground=BG, activeforeground=FG, anchor='w', font=MONO_SM,
            bd=0, highlightthickness=0)
        self.fixed_box.pack(fill='x', pady=2)
        Button(left, 'APPLY SIZE / POSITION', self.apply, AMBER).pack(fill='x', pady=4)
        Button(left, 'REPLACE IMAGE', self.replace_image, CYAN).pack(fill='x')
        Button(left, 'EDIT CONVERSATION', self.conversation, CYAN).pack(fill='x', pady=4)
        Button(left, 'ADD SPRITE / SLOT', self.add_object, CYAN).pack(fill='x', pady=4)
        order = tk.Frame(left, bg=BG)
        order.pack(fill='x')
        Button(order, 'FRONT', lambda: self.move_layer(1), CYAN).pack(side='left', expand=True, fill='x')
        Button(order, 'BACK', lambda: self.move_layer(-1), CYAN).pack(side='left', expand=True, fill='x')
        names = tk.Frame(left, bg=BG)
        names.pack(fill='x', pady=4)
        Button(names, 'RENAME', self.rename_object, CYAN).pack(side='left', expand=True, fill='x')
        Button(names, 'DELETE', self.delete_object, RED).pack(side='left', expand=True, fill='x')
        self.canvas = tk.Canvas(body, bg=SUNKEN, highlightthickness=0, width=660, height=480)
        self.canvas.pack(side='left', fill='both', expand=True)
        self.canvas.bind('<Configure>', lambda e: self.draw())
        self.canvas.bind('<Button-1>', self.press)
        self.canvas.bind('<B1-Motion>', self.motion)
        self.canvas.bind('<ButtonRelease-1>', lambda e: setattr(self, 'drag', None))

    def load(self, project, force=False):
        if project == self.project and not force:
            return
        if self.dirty and self.project:
            self.save()
            if self.dirty:
                return
        self.scene.set('')
        self.scene['values'] = []
        self.actor.set('')
        self.actor['values'] = []
        self.vn = False
        self.selected = 0
        self.project = project
        self.doc = None
        self.history = []
        if project:
            root = Path(project)
            self.path = root / ('vn.json' if (root/'vn.json').exists() else 'scene.json')
            try:
                self.doc = json.loads(self.path.read_text(), parse_float=lambda x: int(float(x)) if float(x).is_integer() else float(x))
                self.stamp = self.path.stat().st_mtime_ns
            except (OSError, ValueError) as exc:
                self.log(str(exc))
        if self.doc:
            self.vn = 'kit' in self.doc
            self.actor['values'] = [c.get('name',c['id']) for c in self.doc['kit'].get('characters',[])] if self.vn else []
            if self.actor['values']: self.actor.current(0)
            scenes = self.doc['kit']['scenes'] if self.vn else self.doc.get('scenes',[self.doc])
            self.scene['values'] = ["%s [%s]" % (
                s.get('name') or s.get('title') or s.get('id') or 'Room '+str(i),
                s.get('id', i)) for i,s in enumerate(scenes)]
            if scenes: self.scene.current(0)
            self.note.configure(text='PS2 VN · drag portrait/dialogue; replace scene background or character portrait.' if self.vn
                                else 'PS1 320x240 · drag existing sprites; script-assigned positions may override room placement.')
        else:
            self.scene['values'] = []
            self.note.configure(text='Select a PS1 scene project or the PS2 VN. No room data here yet.')
        self.draw()

    def reload(self):
        if self.dirty and not messagebox.askyesno('Reload', 'Discard unsaved room edits?', parent=self): return
        self.dirty = False
        self.load(self.project, True)

    def slots(self):
        """The VN's named portrait slots, migrating older single-portrait data.

        A conversation with one portrait rectangle can only ever be a monologue.
        The slot list is what lets two characters share a screen, and its order
        is the order they are drawn in.
        """
        layout = self.doc['kit'].setdefault('layout', {})
        if not layout.get('portraits'):
            layout['portraits'] = [{'name': 'main',
                                    'rect': layout.get('portrait', [32, 24, 128, 224])}]
        return layout['portraits']

    def entries(self):
        """(name, rect) for everything in the room, in draw order."""
        if not self.doc: return []
        i = max(0, self.scene.current())
        if self.vn:
            layout = self.doc['kit'].setdefault('layout', {})
            rows = [('background', layout.setdefault('background', [0,0,640,448]))]
            rows += [('portrait: '+s.get('name','?'), s['rect']) for s in self.slots()]
            rows.append(('dialogue', layout.setdefault('dialogue', [32,232,576,168])))
            return rows
        scenes = self.doc.get('scenes',[self.doc])
        return [(s.get('name') or 'sprite '+str(j), [s.get('x',0),s.get('y',0),s['w'],s['h']])
                for j,s in enumerate(scenes[i].get('sprites',[]))]

    def is_portrait(self, index):
        """True for a VN portrait slot: drawn bottom-anchored and aspect-fitted."""
        return self.vn and 1 <= index <= len(self.slots())

    def dialogue_index(self):
        """Index of the dialogue box, which is always last in a VN room."""
        return len(self.slots()) + 1

    def image_path(self, index):
        if self.vn:
            kit = self.doc['kit']
            if index==0: return kit['scenes'][max(0,self.scene.current())].get('background','')
            if 1 <= index <= len(self.slots()) and kit.get('characters'):
                return kit['characters'][max(0,self.actor.current())].get('portrait','')
            return ''
        sc=self.doc.get('scenes',[self.doc])[max(0,self.scene.current())]
        sprite=sc['sprites'][index]
        return next((t['file'] for t in self.doc.get('textures',[]) if t['name']==sprite['texture']), '')

    def draw(self):
        self.canvas.delete('all'); self.photos=[]; self.boxes=[]
        self.objects.delete(0,'end')
        if not self.doc: return
        w,h=(640,448) if self.vn else (320,240)
        self.scale=max(0.1,min((self.canvas.winfo_width()-24)/w,(self.canvas.winfo_height()-24)/h))
        z=self.scale
        self.canvas.create_rectangle(12,12,12+w*z,12+h*z,fill='#19232d',outline=CYAN)
        entries=self.entries()
        order=list(range(len(entries))) if self.vn else list(reversed(range(len(entries))))
        for name,rect in entries: self.objects.insert('end', name)
        for index in order:
            name,(x,y,rw,rh)=entries[index]
            box=(12+x*z,12+y*z,12+(x+rw)*z,12+(y+rh)*z)
            self.boxes.append((index,box))
            path=self.image_path(index)
            try:
                if path:
                    with Image.open(Path(self.project)/path) as source:
                        im=source.convert('RGBA')
                    if not self.vn:
                        sprite=self.doc.get('scenes',[self.doc])[max(0,self.scene.current())]['sprites'][index]
                        u,v=sprite.get('u',0),sprite.get('v',0)
                        im=im.crop((u,v,u+rw,v+rh))
                    if self.is_portrait(index):
                        im.thumbnail((max(1,int(rw*z)),max(1,int(rh*z))),Image.Resampling.NEAREST)
                    else: im=im.resize((max(1,int(rw*z)),max(1,int(rh*z))),Image.Resampling.NEAREST)
                    photo=ImageTk.PhotoImage(im);self.photos.append(photo)
                    portrait=self.is_portrait(index)
                    self.canvas.create_image(box[0],box[3] if portrait else box[1],
                                             anchor='sw' if portrait else 'nw',image=photo)
                else:
                    self.canvas.create_rectangle(*box,fill='#0a0c12' if name=='dialogue' else '#476775',outline=DIM)
                    self.canvas.create_text(box[0]+8,box[1]+8,anchor='nw',fill='white',text='NAME\nDialogue preview\nX: reveal / next' if name=='dialogue' else name)
            except (OSError, ValueError):
                self.canvas.create_rectangle(*box,outline='red')
        if self.vn:
            self.canvas.create_rectangle(12+32*z,12+24*z,12+608*z,12+424*z,outline=AMBER,dash=(4,4))
        if entries:
            self.selected=min(self.selected,len(entries)-1)
            x,y,rw,rh=entries[self.selected][1]
            self.canvas.create_rectangle(12+x*z,12+y*z,12+(x+rw)*z,12+(y+rh)*z,outline=AMBER,width=2)
            self.objects.selection_set(self.selected)
            for field,value in zip(self.values,(x,y,rw,rh)):
                field.delete(0,'end');field.insert(0,str(value))
        self._sync_fixed()

    def select(self, event):
        if self.objects.curselection(): self.selected=self.objects.curselection()[0];self.draw()

    def checkpoint(self):
        self.history.append(copy.deepcopy(self.doc));self.history=self.history[-40:];self.dirty=True

    def undo(self):
        if self.history: self.doc=self.history.pop();self.dirty=True;self.draw()

    def set_rect(self, rect):
        if self.vn:
            layout=self.doc['kit']['layout']
            if self.selected==0: layout['background']=rect
            elif self.selected==self.dialogue_index(): layout['dialogue']=rect
            else: self.slots()[self.selected-1]['rect']=rect
        else:
            sprite=self.doc.get('scenes',[self.doc])[max(0,self.scene.current())]['sprites'][self.selected]
            sprite.update(zip(('x','y','w','h'),rect))

    def press(self,event):
        for index,box in reversed(self.boxes):
            if box[0]<=event.x<=box[2] and box[1]<=event.y<=box[3]:
                self.selected=index;self.checkpoint()
                self.drag=(event.x,event.y,list(self.entries()[index][1]));self.draw();break

    def motion(self,event):
        if not self.drag:return
        px,py,rect=self.drag; step=8 if self.snap.get() else 1
        w,h=(640,448) if self.vn else (320,240)
        x=round((rect[0]+(event.x-px)/self.scale)/step)*step
        y=round((rect[1]+(event.y-py)/self.scale)/step)*step
        self.set_rect([max(0,min(w-rect[2],x)),max(0,min(h-rect[3],y)),rect[2],rect[3]]);self.draw()

    def apply(self):
        if not self.doc:return
        try:
            rect=[int(e.get()) for e in self.values]
            w,h=(640,448) if self.vn else (320,240)
            if min(rect)<0 or rect[2]<1 or rect[3]<1 or rect[0]+rect[2]>w or rect[1]+rect[3]>h: raise ValueError('Rectangle must fit the room.')
            self.checkpoint();self.set_rect(rect);self.draw()
        except ValueError as exc:messagebox.showerror('Room property',str(exc),parent=self)

    def save(self):
        if not self.doc or not self.dirty:return
        if self.path.stat().st_mtime_ns!=self.stamp:
            messagebox.showerror('Room changed outside Studio','Reload before saving: Godot or another editor changed this file.',parent=self);return
        tmp=self.path.with_suffix('.json.tmp');tmp.write_text(json.dumps(self.doc,indent=2)+'\n');tmp.replace(self.path)
        self.stamp=self.path.stat().st_mtime_ns;self.dirty=False
        self.log('Room saved. Build to apply on console. Reload Godot layout before exporting there.')

    def replace_image(self):
        if not self.doc:return
        if self.vn and self.selected==self.dialogue_index():return
        file=filedialog.askopenfilename(parent=self,filetypes=[('PNG image','*.png')])
        if not file:return
        with Image.open(file) as image:
            limit=(512,512) if self.vn else (256,240)
            if image.width>limit[0] or image.height>limit[1]:
                messagebox.showerror('Image too large',f'Resize to at most {limit[0]}x{limit[1]} before importing.',parent=self);return
        directory=Path(self.project)/('godot/assets' if self.vn else 'textures');directory.mkdir(parents=True,exist_ok=True)
        dest=directory/Path(file).name
        n=1
        while dest.exists() and dest.resolve()!=Path(file).resolve():
            dest=directory/(Path(file).stem+f'_{n}.png');n+=1
        if dest.resolve()!=Path(file).resolve():shutil.copy2(file,dest)
        self.checkpoint();rel=dest.relative_to(self.project).as_posix()
        if self.vn:
            if self.selected==0:self.doc['kit']['scenes'][max(0,self.scene.current())]['background']=rel
            elif self.doc['kit'].get('characters'):self.doc['kit']['characters'][max(0,self.actor.current())]['portrait']=rel
        else:
            old=self.image_path(self.selected)
            for texture in self.doc.get('textures',[]):
                if texture['file']==old:texture['file']=rel
        self.draw()

    # ---- naming and layer order -----------------------------------------

    def toggle_fixed(self):
        """Mark the selected PS1 sprite as HUD, or let it move with the shake."""
        if not self.doc or self.vn:
            return
        sprites = self._sprites()
        if not 0 <= self.selected < len(sprites):
            return
        self.checkpoint()
        if self.fixed.get():
            sprites[self.selected]['fixed'] = True
        else:
            sprites[self.selected].pop('fixed', None)

    def _sync_fixed(self):
        sprites = [] if self.vn or not self.doc else self._sprites()
        usable = bool(sprites) and 0 <= self.selected < len(sprites)
        self.fixed_box.configure(state='normal' if usable else 'disabled')
        self.fixed.set(bool(sprites[self.selected].get('fixed')) if usable else False)

    def _sprites(self):
        return self.doc.get('scenes', [self.doc])[max(0, self.scene.current())].setdefault('sprites', [])

    def move_layer(self, toward_viewer):
        """Move the selected object one step through the draw order.

        The two machines store depth in opposite directions. On PS1 every 2D
        sprite lands in one ordering-table bucket and addPrim prepends, so the
        first sprite in the file is drawn last and ends up in front. The PS2 VN
        draws its list in order, so its last entry is in front. FRONT means the
        same thing on screen either way; only the arithmetic differs.
        """
        if not self.doc:
            return
        if self.vn:
            slots = self.slots()
            a = self.selected - 1
            b = a + toward_viewer
            if not (0 <= a < len(slots) and 0 <= b < len(slots)):
                return
            self.checkpoint()
            slots[a], slots[b] = slots[b], slots[a]
            self.selected = b + 1
        else:
            sprites = self._sprites()
            a = self.selected
            b = a - toward_viewer          # lower index is nearer the viewer
            if not (0 <= a < len(sprites) and 0 <= b < len(sprites)):
                return
            self.checkpoint()
            sprites[a], sprites[b] = sprites[b], sprites[a]
            self.selected = b
        self.draw()

    def rename_object(self):
        """Name the selected object. Unnamed sprites are why nothing is findable."""
        if not self.doc:
            return
        entries = self.entries()
        if not entries:
            return
        if self.vn and not 1 <= self.selected <= len(self.slots()):
            messagebox.showinfo('Rename', 'The background and the dialogue box are '
                                'part of every room and keep their names.', parent=self)
            return
        old = entries[self.selected][0]
        name = simpledialog.askstring('Rename', 'Name for this object:',
                                      initialvalue=old.replace('portrait: ', ''), parent=self)
        if not name:
            return
        self.checkpoint()
        if self.vn:
            slots = self.slots()
            if any(s.get('name') == name for s in slots):
                messagebox.showerror('Rename', 'Another slot is already called %s.' % name,
                                     parent=self)
                return
            previous = slots[self.selected - 1].get('name')
            slots[self.selected - 1]['name'] = name
            # Lines cast characters into slots by name, so a rename has to follow
            # them or the next build fails on every line that used the old one.
            for line in self.doc['kit'].get('dialogue', []):
                for member in line.get('cast', []):
                    if member.get('slot') == previous:
                        member['slot'] = name
        else:
            self._sprites()[self.selected]['name'] = name
        self.draw()

    def delete_object(self):
        if not self.doc:
            return
        if self.vn:
            slots = self.slots()
            if not 1 <= self.selected <= len(slots):
                messagebox.showinfo('Delete', 'The background and dialogue box cannot '
                                    'be removed.', parent=self)
                return
            if len(slots) < 2:
                messagebox.showinfo('Delete', 'A conversation needs at least one '
                                    'portrait slot.', parent=self)
                return
            name = slots[self.selected - 1].get('name')
            if not messagebox.askyesno('Delete', 'Remove slot %s? Any line that casts '
                                       'a character into it loses that portrait.' % name,
                                       parent=self):
                return
            self.checkpoint()
            slots.pop(self.selected - 1)
            for line in self.doc['kit'].get('dialogue', []):
                if line.get('cast'):
                    line['cast'] = [m for m in line['cast'] if m.get('slot') != name]
        else:
            sprites = self._sprites()
            if not sprites:
                return
            if not messagebox.askyesno('Delete', 'Remove %s from this room?'
                                       % self.entries()[self.selected][0], parent=self):
                return
            self.checkpoint()
            sprites.pop(self.selected)
        self.selected = max(0, self.selected - 1)
        self.draw()

    # ---- conversation editor -------------------------------------------

    def _pickers(self):
        """Every id in the kit, as (id, label) pairs ready for a dropdown.

        Typing ids by hand was the old design and it is the reason a build could
        fail on a name nobody could see was wrong. A dropdown cannot produce a
        dangling reference in the first place.
        """
        kit = self.doc['kit']
        def named(rows, blank):
            pairs = [('', blank)] if blank else []
            return pairs + [(r['id'], '%s  [%s]' % (r.get('name', r['id']), r['id']))
                            for r in rows]
        return {
            'speaker': named(kit.get('characters', []), '(narration)'),
            'character': named(kit.get('characters', []), '(empty)'),
            'scene': [(s['id'], s['id']) for s in kit.get('scenes', [])],
            'give': named(kit.get('items', []), '(nothing)'),
            'requires': named(kit.get('items', []), '(no requirement)'),
            'next': [('', '(ends the conversation)')] +
                    [(l['id'], l['id']) for l in kit.get('dialogue', [])],
            'slot': [('', '(empty)')] + [(s['name'], s['name']) for s in self.slots()],
        }

    def conversation(self):
        if not self.doc or not self.vn:
            return
        kit = self.doc['kit']
        lines = kit.setdefault('dialogue', [])
        if not lines:
            messagebox.showinfo('Conversation', 'This VN has no dialogue yet.', parent=self)
            return

        win = dialog(self, 'NC Conversation', '860x660')
        win.grab_set()
        current = [None]
        pickers = {}

        # ---- left: the conversation as a list, not a dropdown ----------
        body = tk.Frame(win, bg=BG)
        body.pack(fill='both', expand=True, padx=8, pady=6)
        side = tk.Frame(body, bg=BG, width=250)
        side.pack(side='left', fill='y', padx=(0, 8))
        side.pack_propagate(False)
        label(side, 'ENTRIES  (the graph, in file order)', CYAN, BG, UI_BOLD).pack(fill='x')
        listing = tk.Listbox(side, bg=SUNKEN, fg=FG, font=MONO_SM, bd=0,
                             highlightthickness=1, highlightbackground=BORDER,
                             selectbackground=AMBER, selectforeground=BG,
                             activestyle='none', exportselection=False)
        listing.pack(fill='both', expand=True, pady=4)

        form = tk.Frame(body, bg=BG)
        form.pack(side='left', fill='both', expand=True)
        tabs = ttk.Notebook(form)
        tabs.pack(fill='both', expand=True)
        page = tk.Frame(tabs, bg=PANEL)
        stage = tk.Frame(tabs, bg=PANEL)
        options = tk.Frame(tabs, bg=PANEL)
        tabs.add(page, text='LINE')
        tabs.add(stage, text='ON SCREEN')
        tabs.add(options, text='CHOICES')

        def row(parent, text):
            holder = tk.Frame(parent, bg=PANEL)
            holder.pack(fill='x', padx=10, pady=3)
            label(holder, text, DIM, PANEL).pack(side='left', anchor='w')
            return holder

        def picker(parent, key, width=30):
            box = IdPicker(parent, [], width=width)
            box.pack(side='right')
            pickers.setdefault(key, []).append(box)
            return box

        # ---- LINE ------------------------------------------------------
        ident = entry(row(page, 'id  (renaming updates every reference)'), width=24)
        ident.pack(side='right')
        speaker = picker(row(page, 'who is speaking'), 'speaker')
        scene = picker(row(page, 'location'), 'scene')
        label(page, '  text  —  wraps at 32 characters, four lines maximum',
              DIM, PANEL).pack(fill='x', padx=10, pady=(10, 2))
        text_box = tk.Text(page, height=6, bg=SUNKEN, fg=FG, font=MONO_SM,
                           insertbackground=AMBER, wrap='word', bd=0,
                           highlightthickness=1, highlightbackground=BORDER)
        text_box.pack(fill='x', padx=10)
        preview = label(page, '', DIM, PANEL, MONO_SM)
        preview.pack(fill='x', padx=10, pady=2)
        nxt = picker(row(page, 'then go to'), 'next')
        give = picker(row(page, 'give the player'), 'give')

        def repreview(*_):
            raw = text_box.get('1.0', 'end-1c').replace(chr(10), ' ')
            wrapped = textwrap.wrap(raw, 32) or ['']
            colour = RED if len(wrapped) > 4 else DIM
            preview.configure(fg=colour, text='%d characters  ->  %d of 4 lines: %s'
                              % (len(raw), len(wrapped), ' / '.join(wrapped[:4])))
        text_box.bind('<KeyRelease>', repreview)

        # ---- ON SCREEN -------------------------------------------------
        label(stage, '  Who stands where, this line. Slots are the portrait\n'
                     '  rectangles in ROOM; their order there is the layer order.',
              DIM, PANEL, MONO_SM, justify='left').pack(fill='x', padx=10, pady=8)
        cast_rows = []
        for i in range(4):
            holder = tk.Frame(stage, bg=PANEL)
            holder.pack(fill='x', padx=10, pady=3)
            label(holder, 'slot %d' % (i + 1), DIM, PANEL, width=8).pack(side='left')
            slot = IdPicker(holder, [], width=14)
            slot.pack(side='left', padx=4)
            who = IdPicker(holder, [], width=26)
            who.pack(side='left', padx=4)
            pickers.setdefault('slot', []).append(slot)
            pickers.setdefault('character', []).append(who)
            cast_rows.append((slot, who))
        label(stage, '  Leave a slot empty to take that character off screen.\n'
                     '  With no cast at all the speaker appears in the first slot.',
              DIM, PANEL, MONO_SM, justify='left').pack(fill='x', padx=10, pady=8)

        # ---- CHOICES ---------------------------------------------------
        choice_rows = []
        for i in range(2):
            box = tk.LabelFrame(options, text=' CHOICE %d ' % (i + 1), bg=PANEL,
                                fg=CYAN, font=UI_BOLD, bd=1,
                                highlightbackground=BORDER)
            box.pack(fill='x', padx=10, pady=8)
            group_fields = {}
            holder = tk.Frame(box, bg=PANEL)
            holder.pack(fill='x', padx=8, pady=3)
            label(holder, 'label  (blank disables)', DIM, PANEL).pack(side='left')
            group_fields['text'] = entry(holder, width=26)
            group_fields['text'].pack(side='right')
            for key, caption in (('next', 'goes to'), ('requires', 'needs item'),
                                 ('give', 'gives item')):
                group_fields[key] = picker(row(box, caption), key, width=28)
            choice_rows.append(group_fields)
        label(options, '  A choice whose required item is missing shows "!" and\n'
                       '  cannot be taken. Two choices is the runtime maximum.',
              DIM, PANEL, MONO_SM, justify='left').pack(fill='x', padx=10)

        status = label(win, '', GREEN, BG, MONO_SM)

        # ---- state -----------------------------------------------------
        def refresh_pickers():
            table = self._pickers()
            for key, boxes in pickers.items():
                for box in boxes:
                    keep = box.get_id()
                    box.set_pairs(table[key])
                    box.set_id(keep)

        def relist(select):
            listing.delete(0, 'end')
            for line in lines:
                who = line.get('speaker') or '--'
                listing.insert('end', '%-12s %-8s %s'
                               % (line['id'][:12], who[:8],
                                  line.get('text', '')[:22]))
            current[0] = None
            index = max(0, min(select, len(lines) - 1))
            listing.selection_clear(0, 'end')
            listing.selection_set(index)
            listing.see(index)
            show()

        def commit():
            """Fold the form back into the selected entry."""
            index = current[0]
            if index is None or not 0 <= index < len(lines):
                return
            line = lines[index]
            edited = dict(line)
            new_id = ident.get().strip()
            if new_id and new_id != line['id']:
                if any(o is not line and o['id'] == new_id for o in lines):
                    messagebox.showerror('Conversation',
                                         'Another entry is already called %s.' % new_id,
                                         parent=win)
                else:
                    self._rename_line(line['id'], new_id)
                    edited['id'] = new_id
            edited['speaker'] = speaker.get_id()
            edited['scene'] = scene.get_id()
            edited['next'] = nxt.get_id()
            edited['give'] = give.get_id()
            edited['text'] = text_box.get('1.0', 'end-1c').replace(chr(10), ' ')
            cast = []
            for slot, who in cast_rows:
                if slot.get_id() and who.get_id():
                    cast.append({'slot': slot.get_id(), 'character': who.get_id()})
            edited['cast'] = cast
            picked = []
            for group_fields in choice_rows:
                if group_fields['text'].get().strip():
                    picked.append({'text': group_fields['text'].get().strip(),
                                   'next': group_fields['next'].get_id(),
                                   'requires': group_fields['requires'].get_id(),
                                   'give': group_fields['give'].get_id()})
            edited['choices'] = picked
            if edited != line:
                self.checkpoint()
                line.clear()
                line.update(edited)

        def show(*_):
            commit()
            selection = listing.curselection()
            index = selection[0] if selection else 0
            current[0] = index
            refresh_pickers()
            line = lines[index]
            ident.delete(0, 'end')
            ident.insert(0, line['id'])
            speaker.set_id(line.get('speaker', ''))
            scene.set_id(line.get('scene', ''))
            nxt.set_id(line.get('next', ''))
            give.set_id(line.get('give', ''))
            text_box.delete('1.0', 'end')
            text_box.insert('1.0', line.get('text', ''))
            repreview()
            cast = line.get('cast', [])
            for i, (slot, who) in enumerate(cast_rows):
                member = cast[i] if i < len(cast) else {}
                slot.set_id(member.get('slot', ''))
                who.set_id(member.get('character', ''))
            for i, group_fields in enumerate(choice_rows):
                opts = line.get('choices', [])
                opt = opts[i] if i < len(opts) else {}
                group_fields['text'].delete(0, 'end')
                group_fields['text'].insert(0, opt.get('text', ''))
                for key in ('next', 'requires', 'give'):
                    group_fields[key].set_id(opt.get(key, ''))
            entered = 'start' if kit.get('start') == line['id'] else ''
            status.configure(fg=CYAN, text='Entry %d of %d   %s'
                             % (index + 1, len(lines),
                                'This is where the conversation begins.' if entered else ''))

        listing.bind('<<ListboxSelect>>', show)

        # ---- actions ---------------------------------------------------
        def unique(stem):
            name, n = stem, 2
            while any(l['id'] == name for l in lines):
                name, n = '%s_%d' % (stem, n), n + 1
            return name

        def add():
            commit()
            self.checkpoint()
            source = lines[current[0]] if current[0] is not None else {}
            lines.append({'id': unique('line'),
                          'scene': source.get('scene')
                          or kit['scenes'][max(0, self.scene.current())]['id'],
                          'speaker': source.get('speaker', ''), 'text': '',
                          'next': '', 'give': '', 'cast': [], 'choices': []})
            relist(len(lines) - 1)

        def duplicate():
            commit()
            if current[0] is None:
                return
            self.checkpoint()
            copied = copy.deepcopy(lines[current[0]])
            copied['id'] = unique(copied['id'])
            lines.insert(current[0] + 1, copied)
            relist(current[0] + 1)

        def chain():
            """Add a line and point the current one at it -- the common case."""
            index = current[0]
            add()
            if index is not None:
                lines[index]['next'] = lines[-1]['id']
                relist(len(lines) - 1)

        def remove():
            if len(lines) < 2:
                messagebox.showinfo('Conversation',
                                    'A conversation needs at least one entry.', parent=win)
                return
            index = current[0]
            line = lines[index]
            users = [l['id'] for l in lines if l is not line
                     and (l.get('next') == line['id']
                          or any(c.get('next') == line['id'] for c in l.get('choices', [])))]
            if users and not messagebox.askyesno(
                    'Conversation',
                    '%s is still the destination of: %s.\nDelete it anyway?'
                    % (line['id'], ', '.join(users)), parent=win):
                return
            self.checkpoint()
            current[0] = None
            lines.pop(index)
            relist(index)

        def make_start():
            commit()
            kit['start'] = lines[current[0]]['id']
            status.configure(fg=GREEN, text='%s is now the opening line.' % kit['start'])

        def store():
            commit()
            self.save()
            relist(current[0] if current[0] is not None else 0)
            status.configure(fg=GREEN,
                             text='Saved %d entries. Build (F7) to put them on the console.'
                             % len(lines))

        bar = tk.Frame(win, bg=BG)
        bar.pack(fill='x', padx=8, pady=(0, 4))
        for text, command, accent in (('ADD', add, CYAN), ('ADD + LINK', chain, CYAN),
                                      ('DUPLICATE', duplicate, CYAN),
                                      ('DELETE', remove, RED),
                                      ('SET AS START', make_start, DIM),
                                      ('SAVE', store, AMBER)):
            Button(bar, text, command, accent).pack(side='left', padx=(0, 4))
        Button(bar, 'CLOSE', lambda: (store(), win.destroy()), DIM).pack(side='right')
        status.pack(fill='x', padx=10, pady=(0, 6))
        win.protocol('WM_DELETE_WINDOW', lambda: (store(), win.destroy()))
        relist(0)

    def _rename_line(self, old, new):
        """Point every reference at a renamed entry, including the start line."""
        kit = self.doc['kit']
        if kit.get('start') == old:
            kit['start'] = new
        for line in kit.get('dialogue', []):
            if line.get('next') == old:
                line['next'] = new
            for choice in line.get('choices', []):
                if choice.get('next') == old:
                    choice['next'] = new

    def new_room(self):
        if not self.doc:return
        name=simpledialog.askstring('New room','Unique room name:',parent=self)
        if not name:return
        scenes=self.doc['kit']['scenes'] if self.vn else self.doc.setdefault('scenes',[copy.deepcopy(self.doc)])
        if any(s.get('id')==name for s in scenes):return
        self.checkpoint()
        scenes.append({'id':name,'background':'','color':[20,24,26]} if self.vn else {'id':name,'clear':[20,24,26],'sprites':[],'instances':[]})
        self.scene['values']=[s.get('id','Scene '+str(i)) for i,s in enumerate(scenes)]
        self.scene.current(len(scenes)-1);self.draw()

    def add_object(self):
        if not self.doc:return
        if self.vn:
            name=simpledialog.askstring('New character','Unique character id:',parent=self)
            if not name or any(c['id']==name for c in self.doc['kit']['characters']):return
            self.checkpoint();self.doc['kit']['characters'].append({'id':name,'name':name.upper(),'portrait':''})
            self.actor['values']=[c.get('name',c['id']) for c in self.doc['kit']['characters']]
            self.actor.current(len(self.doc['kit']['characters'])-1);self.selected=1;self.draw();self.replace_image()
        else:
            textures=self.doc.get('textures',[])
            if not textures:
                messagebox.showinfo('Add sprite','Import a texture through Studio +TEX first.',parent=self);return
            name=simpledialog.askstring('New sprite','Name for this sprite:',
                                        initialvalue='sprite',parent=self)
            if not name:return
            sprites=self._sprites()
            # Index 0 is the front of the screen on PS1, so a sprite you just
            # added is visible rather than buried under the whole playfield --
            # which is what a HUD element almost always wants.
            self.checkpoint()
            sprites.insert(0,{'name':name,'texture':textures[0]['name'],
                              'x':0,'y':0,'w':16,'h':16,'u':0,'v':0})
            self.selected=0;self.draw()
