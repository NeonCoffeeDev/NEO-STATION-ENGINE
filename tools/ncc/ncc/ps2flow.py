"""PS2 flow compiler for explicitly integrated runtime adapters."""
import json
from pathlib import Path
from .eventflow import BUTTONS

def compile_project(project):
    root=Path(project); path=root/'event-flow.json'
    if not path.exists(): return
    doc=json.loads(path.read_text())
    if doc.get('target')!='ps2': raise ValueError('PS2 build refuses a graph from another console.')
    if doc.get('status')=='draft':
        if (root/'src/nc_events.h').exists():
            (root/'src/nc_events.h').write_text('static void nc_events(int start, unsigned int pressed, int zone) {(void)start;(void)pressed;(void)zone;}\n')
        return
    if doc.get('status')!='enabled':raise ValueError('Invalid event status.')
    meta=json.loads((root/'nc.json').read_text())
    if meta.get('event_adapter')!='fixed_room_v1':
        raise ValueError('This PS2 project has no supported event adapter. Keep its graph as a draft.')
    actions={'Set camera':(0,2),'Interact':(1,0),'Reset game':(2,0)}
    nodes=doc['nodes'];lookup={n['id']:n for n in nodes}
    if len(nodes)>128 or len(lookup)!=len(nodes):raise ValueError('Too many nodes or duplicate IDs.')
    if any(type(i) is not int or i < 1 for i in lookup):raise ValueError('Node IDs must be positive integers.')
    links={i:[] for i in lookup};incoming={i:0 for i in lookup}
    for a,b in doc['edges']:
        if a not in lookup or b not in lookup or b in links[a]:raise ValueError('Invalid or duplicate edge.')
        links[a].append(b);incoming[b]+=1
    output=['/* Generated PS2 fixed-room events. Do not edit. */','static void nc_events(int start, unsigned int pressed, int zone) {','    (void)start; (void)pressed; (void)zone;', '    static unsigned int tick;', '    if (start) tick = 0; else if (tick < 0xffffffffu) tick++;']
    for n in nodes:
        if n['kind']=='Once':
            output += ['    static int used_%d;'%n['id'], '    if (start) used_%d = 0;'%n['id']]
        elif n['kind']=='Cooldown':
            output += ['    static unsigned int next_%d;'%n['id'], '    if (start) next_%d = 0;'%n['id']]
    reached=set()
    def walk(i,stack):
        if i in stack:raise ValueError('Event cycles are not supported.')
        reached.add(i)
        for j in links[i]:
            n=lookup[j]
            if n['kind'] in ('Once','Cooldown'):
                if n['kind']=='Once':
                    output.append('        if (!used_%d) { used_%d = 1;'%(j,j))
                else:
                    frames=int(n.get('value') or 0)
                    if not 1<=frames<=36000:raise ValueError('Cooldown must be 1..36000 frames.')
                    output.append('        if (tick >= next_%d) { next_%d = tick + %d;'%(j,j,frames))
                walk(j,stack|{i});output.append('        }');continue
            if n['kind'] not in actions:raise ValueError('Unsupported action: '+n['kind'])
            opcode,limit=actions[n['kind']]
            value=int(n.get('value') or 0)
            if not 0<=value<=limit:raise ValueError('Invalid parameter for '+n['kind'])
            output.append('        nc_action(%d, %d);'%(opcode,value))
            walk(j,stack|{i})
    for n in nodes:
        kind=n['kind']; value=n.get('value','')
        if kind=='On start':condition='start'
        elif kind=='On button':
            button=value.upper().removeprefix('BTN_')
            if button not in BUTTONS:raise ValueError('Unsupported PS2 button.')
            condition='pressed & PAD_'+button
        elif kind in ('After frames','Every frames'):
            frames=int(value)
            if not 1<=frames<=36000:raise ValueError('Timer must be 1..36000 frames.')
            condition=('!start && tick == %d' if kind=='After frames' else '!start && tick > 0 && tick %% %d == 0')%frames
        elif kind=='On zone':
            v=int(value)
            if v not in (0,1):raise ValueError('Zone must be 0 or 1.')
            condition='zone == %d'%v
        elif kind in actions or kind in ('Once','Cooldown'):continue
        else:raise ValueError('Unsupported PS2 node: '+kind)
        if incoming[n['id']]:raise ValueError('Events cannot have incoming links.')
        output.append('    if (%s) {'%condition);walk(n['id'],set());output.append('    }')
    if reached!=set(lookup):raise ValueError('Every action must connect to an event.')
    output.append('}')
    (root/'src/nc_events.h').write_text('\n'.join(output)+'\n')
