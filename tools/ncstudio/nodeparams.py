"""Plain-language node parameter editing."""
import math
import re
import tkinter as tk
from tkinter import simpledialog, messagebox, ttk
import json
from pathlib import Path

HELP = {
    'On arrival':'Fire once when the player completes a Move to. Cancellation does not fire it. No parameter.',
    'Stop movement':'Cancel automatic movement and return control to the player. No parameter.',
    'Set variable':'Store a number: coins, 0. Names are shared within this graph; variables start at zero.',
    'Add variable':'Change a number: coins, 1 (or coins, -1). Values clamp to -32767..32767.',
    'If equal':'Continue only when the value matches: coins, 3. A false condition stops this branch.',
    'If at least':'Continue only when the value reaches this amount: coins, 3.',
    'Repeat':'Run the connected actions 1..16 times immediately in this update. Not a timer.',

    'On button':'Button name: CROSS, CIRCLE, SQUARE, TRIANGLE, START, or a direction.',
    'After frames':'Run once this many updates after game startup (180 is about 3 seconds at 60 FPS).',
    'Every frames':'Repeat every N game updates. This is not a blocking wait.',
    'Cooldown':'Minimum updates between accepted triggers. Ignored triggers are not queued.',
    'Once':'Allow the first trigger through. Resets when the game boots.',
    'Set camera':'Camera preset: 0, 1 or 2.',
    'On zone':'Fire when entering zone 0 (left) or 1 (right).',
    'Interact':'Try a nearby pickup or door. No parameter needed.',
    'Reset game':'Reset room gameplay. Does not restart event timers.',
    'Move to':'Move the player to a destination over time. No pathfinding or collision avoidance.',
    'Change room':'Existing room index (0 is the first room).',
    'Play effect':'Existing sound index. Check that this project contains the sound.',
}

class MoveDialog(simpledialog.Dialog):
    def __init__(self,parent,value):
        self.initial=str(value).split(',') if value else ['0','0','120']
        if len(self.initial)!=3:self.initial=['0','0','120']
        super().__init__(parent,'Move player to')
    def body(self,master):
        self.fields=[]
        for i,label in enumerate(('Destination X (-3 to 3)','Destination Z (-2 to 2)','Duration in updates (1 to 36000)')):
            tk.Label(master,text=label).grid(row=i,column=0,sticky='w')
            entry=tk.Entry(master);entry.insert(0,self.initial[i]);entry.grid(row=i,column=1)
            self.fields.append(entry)
        tk.Label(master,text='Temporarily takes over D-pad movement.\nUse On arrival for actions that should wait for arrival.').grid(row=3,column=0,columnspan=2)
        return self.fields[0]
    def validate(self):
        try:
            x,z=(float(e.get()) for e in self.fields[:2]);n=int(self.fields[2].get())
            if not (math.isfinite(x) and math.isfinite(z) and -3<=x<=3 and -2<=z<=2 and 1<=n<=36000):raise ValueError()
            self.result='%g, %g, %d'%(x,z,n);return True
        except ValueError:
            messagebox.showerror('Invalid destination','Use the ranges shown beside each field.',parent=self);return False

class VariableDialog(simpledialog.Dialog):
    def __init__(self,parent,kind,value):
        self.kind=kind
        self.initial=str(value).split(',') if value else ['score','0']
        if len(self.initial)!=2:self.initial=['score','0']
        super().__init__(parent,kind)
    def body(self,master):
        self.fields=[]
        for i,label in enumerate(('Variable name','Number (-32767 to 32767)')):
            tk.Label(master,text=label).grid(row=i,column=0,sticky='w')
            entry=tk.Entry(master);entry.insert(0,self.initial[i].strip());entry.grid(row=i,column=1)
            self.fields.append(entry)
        tk.Label(master,text=HELP[self.kind],wraplength=420).grid(row=2,column=0,columnspan=2)
        return self.fields[0]
    def validate(self):
        name=self.fields[0].get().strip()
        try:
            number=int(self.fields[1].get())
            if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,23}',name) or not -32767<=number<=32767:raise ValueError()
            self.result='%s, %d'%(name,number);return True
        except ValueError:
            messagebox.showerror('Invalid variable','Start the name with a letter; use letters, digits or underscores (max 24). Enter a whole number in range.',parent=self);return False

HELP.update({'Go to Flow Box':'Destination GAME FLOW box ID. Ends this chain and enters that box next update.', 'On exit':'Runs once when leaving this flow box. Cannot request another transition.'})

HELP.update({"On trigger enter":"Trigger ID from VIEWPORT. Fires when the tracked object anchor enters its volume.","On trigger exit":"Trigger ID from VIEWPORT. Fires when the tracked object anchor leaves its volume.","Set sprite position":"PS1 sprite index, X, Y (integer pixels).", "Set object position":"PS1: mesh index, X,Y,Z. PS2 3D Lab: object name, X,Y,Z.","Set colour":"PS2 3D Lab palette index: 0..3.","Show main menu":"Return to the native VN main menu. Parameter: 0."})

class ReferenceDialog(simpledialog.Dialog):
    def __init__(self,parent,title,rows,value):
        self.rows=rows;self.initial=str(value);super().__init__(parent,title)
    def body(self,master):
        self.choice=ttk.Combobox(master,state='readonly',width=55,values=[label for ident,label in self.rows]);self.choice.pack(fill='x')
        found=next((i for i,(ident,label) in enumerate(self.rows) if str(ident)==self.initial),None)
        if found is not None:self.choice.current(found)
        elif self.initial:self.choice.set(self.initial+' (missing reference)')
        elif self.rows:self.choice.current(0)
        return self.choice
    def validate(self):
        if self.choice.current()<0:messagebox.showerror('Reference','Choose an existing entry.',parent=self);return False
        return True
    def apply(self):self.result=str(self.rows[self.choice.current()][0])

def choose_reference(parent,project,kind,value):
    try:
        root=Path(project)
        if kind.startswith('On trigger'):
            path=root/'triggers.json'
            if not path.exists():raise ValueError('Create and SAVE a trigger in VIEWPORT first.')
            rows=[(t['id'],'%s | %s | room %s | tracks %s'%(t['id'],t['name'],t['room'],t['subject'])) for t in json.loads(path.read_text(encoding='utf-8'))['triggers']]
        else:
            rows=[(t['id'],'%s | %s'%(t['id'],t.get('value',t['kind']))) for t in json.loads((root/'game-structure.json').read_text(encoding='utf-8'))['nodes']]
        if not rows:raise ValueError('No entries available yet.')
        return ReferenceDialog(parent,kind,rows,value).result
    except (OSError,ValueError,KeyError,TypeError) as exc:messagebox.showerror('Reference',str(exc),parent=parent);return None
