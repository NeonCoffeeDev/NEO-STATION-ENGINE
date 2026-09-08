"""Project-scoped asset inventory, excluding generated build output."""
import os
import wave
from pathlib import Path
import tkinter as tk
from tkinter import ttk
from theme import BG, FG, CYAN, Button

class AssetPanel(tk.Frame):
    def __init__(self,parent):
        super().__init__(parent,bg=BG);self.group=self;self.project=None;self.paths={}
        bar=tk.Frame(self,bg=BG);bar.pack(fill='x')
        Button(bar,'REFRESH',self.refresh,CYAN).pack(side='left')
        Button(bar,'OPEN SELECTED',self.open,CYAN).pack(side='left')
        tk.Label(bar,text='Project assets — read-only inventory; reference-safe rename/replacement pending',bg=BG,fg=FG).pack(side='left',padx=8)
        self.tree=ttk.Treeview(self,columns=('type','size'),show='tree headings')
        self.tree.heading('#0',text='Project-relative path');self.tree.heading('type',text='Type');self.tree.heading('size',text='KiB')
        self.tree.pack(fill='both',expand=True)
        self.tree.bind('<Double-1>',lambda e:self.open())
        self.tree.bind('<<TreeviewSelect>>',lambda e:self.inspect())
        self.detail=tk.Label(self,bg=BG,fg=FG,anchor='w',justify='left')
        self.detail.pack(fill='x')
        self.preview=None
        self.search=tk.StringVar()
        tk.Label(bar,text='Filter:',bg=BG,fg=FG).pack(side='left')
        ttk.Entry(bar,textvariable=self.search,width=20).pack(side='left')
        self.search.trace_add('write',lambda *args:self.refresh())
    def load(self,project):
        if self.project!=project:self.search.set('')
        self.project=project;self.refresh()
    def refresh(self):
        self.tree.delete(*self.tree.get_children());self.paths={}
        self.preview=None;self.detail.configure(text='',image='')
        if not self.project:return
        root=Path(self.project)
        for folder,dirs,files in os.walk(root):
            dirs[:]=[d for d in dirs if d not in ('.git','.godot','.ncc-cache','build','src')]
            for name in sorted(files):
                p=Path(folder)/name
                if self.search.get().lower() not in p.relative_to(root).as_posix().lower():continue
                if p.suffix.lower() not in ('.png','.jpg','.jpeg','.wav','.ogg','.mp3','.tim','.obj','.gltf','.glb','.ncs','.tscn'):continue
                try: size=p.stat().st_size
                except OSError:continue
                item=self.tree.insert('', 'end',text=p.relative_to(root).as_posix(),values=(p.suffix,round(size/1024,1)))
                self.paths[item]=p
    def open(self):
        selected=self.tree.selection()
        if selected and selected[0] in self.paths:os.startfile(self.paths[selected[0]])

    def inspect(self):
        selected=self.tree.selection();self.preview=None
        self.detail.configure(text='',image='')
        if not selected:return
        p=self.paths.get(selected[0])
        if not p:return
        text=p.relative_to(Path(self.project)).as_posix()
        try:
            if p.suffix.lower() in ('.png','.jpg','.jpeg'):
                from PIL import Image,ImageTk
                with Image.open(p) as im:
                    text+='  |  %d × %d  %s'%(im.width,im.height,im.mode)
                    im.thumbnail((160,90));self.preview=ImageTk.PhotoImage(im.copy())
            elif p.suffix.lower()=='.wav':
                with wave.open(str(p)) as wav:
                    text+='  |  %.2fs  %d Hz  %d channels'%(wav.getnframes()/wav.getframerate(),wav.getframerate(),wav.getnchannels())
        except (OSError,ValueError,ImportError,wave.Error) as exc:text+='  |  preview unavailable: '+str(exc)
        self.detail.configure(text=text,image=self.preview or '',compound='left')
