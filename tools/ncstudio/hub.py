"""Single-project startup hub for NC Studio."""
from pathlib import Path
import tkinter as tk
from theme import BG,PANEL,PANEL_HI,SUNKEN,BORDER,FG,DIM,CYAN,GREEN,AMBER,MONO,MONO_SM,UI_BOLD,Button
from ncc.build import project_meta

PURPLE='#c000ff'

class ProjectHub(tk.Frame):
    def __init__(self,parent,repo,on_open,on_browse,on_new):
        super().__init__(parent,bg=BG,highlightbackground=BORDER,highlightthickness=1)
        self.repo=Path(repo);self.on_open=on_open;self.on_browse=on_browse;self.on_new=on_new
        hero=tk.Frame(self,bg=SUNKEN,height=150);hero.pack(fill='x');hero.pack_propagate(False)
        tk.Label(hero,text='NEO-STATION',bg=SUNKEN,fg=PURPLE,font=('Consolas',30,'bold')).pack(anchor='w',padx=34,pady=(24,0))
        tk.Label(hero,text='// NATIVE PLAYSTATION DEVELOPMENT SYSTEM',bg=SUNKEN,fg=GREEN,font=MONO).pack(anchor='w',padx=37)
        tk.Label(hero,text='PS1  R3000  ONLINE     PS2  EE/GS  ONLINE     EDITOR  READY',bg=SUNKEN,fg=CYAN,font=MONO_SM).pack(anchor='w',padx=37,pady=(14,0))
        body=tk.Frame(self,bg=BG);body.pack(fill='both',expand=True,padx=34,pady=24)
        left=tk.Frame(body,bg=BG);left.pack(side='left',fill='both',expand=True)
        right=tk.Frame(body,bg=PANEL,width=390,highlightbackground=BORDER,highlightthickness=1);right.pack(side='right',fill='y',padx=(24,0));right.pack_propagate(False)
        tk.Label(left,text='RECENT PROJECTS',bg=BG,fg=GREEN,font=UI_BOLD,anchor='w').pack(fill='x')
        self.projects=tk.Listbox(left,bg=SUNKEN,fg=FG,selectbackground=PURPLE,selectforeground='#ffffff',font=MONO,height=12,bd=0,highlightthickness=1,highlightbackground=BORDER,exportselection=False)
        self.projects.pack(fill='both',expand=True,pady=(6,10));self.projects.bind('<Double-Button-1>',lambda _e:self.open_selected())
        buttons=tk.Frame(left,bg=BG);buttons.pack(fill='x')
        Button(buttons,'OPEN SELECTED',self.open_selected,GREEN).pack(side='left')
        Button(buttons,'OPEN FOLDER...',self.on_browse,CYAN).pack(side='left',padx=6)
        Button(buttons,'+ NEW PROJECT',self.on_new,AMBER).pack(side='left')
        tk.Label(right,text=' TRANSMISSION / NEWS ',bg=PANEL_HI,fg=PURPLE,font=UI_BOLD,anchor='w').pack(fill='x')
        self.skin_images=[]
        for filename in ('Skin04-Cropped_Text-Block.png','Skin07-Cropped_Text-Block.png'):
            try:self.skin_images.append(tk.PhotoImage(file=str(self.repo/'assets/editor/hub'/filename)))
            except tk.TclError:pass
        if self.skin_images:tk.Label(right,image=self.skin_images[0],bg=PANEL,bd=0).pack(fill='x',pady=(8,0))
        news=('NEO-STATION AUTHORING MILESTONE\n\n'
              '> Single-project workspace enabled\n'
              '> GameFlow -> Scene -> GameObject\n'
              '> Mixed visual events + NC-Code\n'
              '> Native PS2 3D path active\n\n'
              'News feeds and project icons can be added here without changing the editor workspace.')
        tk.Label(right,text=news,bg=PANEL,fg=GREEN,font=MONO_SM,justify='left',anchor='nw',wraplength=345).pack(fill='both',expand=True,padx=16,pady=16)
        if len(self.skin_images)>1:tk.Label(right,image=self.skin_images[1],bg=PANEL,bd=0).pack(fill='x',pady=(0,8))
        self.paths=[]

    def refresh(self,paths):
        self.paths=[];self.projects.delete(0,'end')
        for path in paths:
            p=Path(path)
            try:meta=project_meta(str(p))
            except (OSError,ValueError,KeyError):continue
            self.paths.append(str(p));self.projects.insert('end','[%s]  %-24s  %s'%(meta['target'].upper(),meta.get('name',p.name),p))
        if self.paths:self.projects.selection_set(0)

    def open_selected(self):
        selected=self.projects.curselection()
        if selected:self.on_open(self.paths[selected[0]])
