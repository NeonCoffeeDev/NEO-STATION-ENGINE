"""Plain-language node parameter editing."""
import math
import tkinter as tk
from tkinter import simpledialog, messagebox

HELP = {
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
        tk.Label(master,text='Temporarily takes over D-pad movement.\nNext connected action runs immediately, not on arrival.').grid(row=3,column=0,columnspan=2)
        return self.fields[0]
    def validate(self):
        try:
            x,z=(float(e.get()) for e in self.fields[:2]);n=int(self.fields[2].get())
            if not (math.isfinite(x) and math.isfinite(z) and -3<=x<=3 and -2<=z<=2 and 1<=n<=36000):raise ValueError()
            self.result='%g, %g, %d'%(x,z,n);return True
        except ValueError:
            messagebox.showerror('Invalid destination','Use the ranges shown beside each field.',parent=self);return False
