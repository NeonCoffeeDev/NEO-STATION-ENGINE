"""Project-scoped asset inventory, excluding generated build output."""
import os
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
    def load(self,project):
        self.project=project;self.refresh()
    def refresh(self):
        self.tree.delete(*self.tree.get_children());self.paths={}
        if not self.project:return
        root=Path(self.project)
        for folder,dirs,files in os.walk(root):
            dirs[:]=[d for d in dirs if d not in ('.git','.godot','.ncc-cache','build','src')]
            for name in sorted(files):
                p=Path(folder)/name
                if p.suffix.lower() not in ('.png','.jpg','.jpeg','.wav','.ogg','.mp3','.tim','.obj','.gltf','.glb','.ncs','.tscn'):continue
                try: size=p.stat().st_size
                except OSError:continue
                item=self.tree.insert('', 'end',text=p.relative_to(root).as_posix(),values=(p.suffix,round(size/1024,1)))
                self.paths[item]=p
    def open(self):
        selected=self.tree.selection()
        if selected and selected[0] in self.paths:os.startfile(self.paths[selected[0]])
