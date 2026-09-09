"""PS2 flow compiler for explicitly integrated runtime adapters."""
import json
import math
import re
from pathlib import Path
from .eventflow import BUTTONS
from .flowstate import validate as validate_state

def compile_project(project):
    root=Path(project); path=root/'event-flow.json'
    if not path.exists():
        if (root/'src/nc_events.h').exists():
            (root/'src/nc_events.h').write_text('static void nc_events(int start, unsigned int pressed, int zone) {(void)start;(void)pressed;(void)zone;}\n', encoding='utf-8')
        return
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
    scoped=validate_state(doc,root)
    actions={'Set camera':(0,2),'Interact':(1,0),'Reset game':(2,0),'Stop movement':(3,0)}
    nodes=doc['nodes'];lookup={n['id']:n for n in nodes}
    if len(nodes)>128 or len(lookup)!=len(nodes):raise ValueError('Too many nodes or duplicate IDs.')
    if any(type(i) is not int or i < 1 for i in lookup):raise ValueError('Node IDs must be positive integers.')
    links={i:[] for i in lookup};incoming={i:0 for i in lookup}
    for a,b in doc['edges']:
        if a not in lookup or b not in lookup or b in links[a]:raise ValueError('Invalid or duplicate edge.')
        links[a].append(b);incoming[b]+=1
    output=['/* Generated PS2 fixed-room events. Do not edit. */','static void nc_events(int start, unsigned int pressed, int zone) {','    (void)start; (void)pressed; (void)zone;', '    static unsigned int tick;', '    if (start) tick = 0; else if (tick < 0xffffffffu) tick++;']
    if scoped:
        output = output[:3] + [
            '    static int active, pending, initialized;',
            '    static unsigned int tick;',
            '    int entering = 0;',
            '    if (start || !initialized) { active = %d; pending = 0; initialized = 1; entering = 1; }' % doc['entry'],
            '    else if (pending) { active = pending; pending = 0; entering = 1; }',
            '    if (entering) { tick = 0; pressed = 0; zone = -1; } else if (tick < 0xffffffffu) tick++;']
    for n in nodes:
        if n['kind']=='Once':
            output += ['    static int used_%d;'%n['id'], '    if (start) used_%d = 0;'%n['id']]
        elif n['kind']=='Cooldown':
            output += ['    static unsigned int next_%d;'%n['id'], '    if (start) next_%d = 0;'%n['id']]
    if scoped:
        output=[line.replace('if (start) used_', 'if (entering) used_').replace('if (start) next_', 'if (entering) next_') for line in output]
    variable_kinds=('Set variable','Add variable','If equal','If at least')
    variables={}
    for n in nodes:
        if n['kind'] in variable_kinds:
            parts=str(n.get('value','')).split(',')
            if len(parts)!=2 or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,23}',parts[0].strip()):
                raise ValueError('Variable nodes need a name and integer, e.g. coins, 1.')
            name=parts[0].strip();value=int(parts[1])
            if not -32767<=value<=32767:raise ValueError('Variable values must be -32767..32767.')
            variables[n['id']]=(name,value)
    names=sorted({name for name,value in variables.values()})
    if len(names)>16:raise ValueError('This adapter supports up to 16 named variables.')
    for name in names:
        output += ['    static int var_%s;'%name,'    if(start) var_%s=0;'%name]
    reached=set()
    expanded=0
    def walk(i,stack):
        nonlocal expanded, output
        expanded+=1
        if expanded>2048:raise ValueError("Flow expands beyond 2048 steps; reduce repeats or shared branches.")
        if i in stack:raise ValueError('Event cycles are not supported.')
        reached.add(i)
        for j in links[i]:
            n=lookup[j]
            if n['kind']=='Go to Flow Box' and scoped:
                output.append('        if (!pending) pending = %d;' % int(n['value']))
                reached.add(j)
                continue
            if n['kind'] in variable_kinds:
                name,value=variables[j];symbol='var_'+name
                if n['kind']=='Set variable':output.append('        %s = %d;'%(symbol,value))
                elif n['kind']=='Add variable':
                    output += ['        %s += %d;'%(symbol,value),
                               '        if(%s>32767) %s=32767;'%(symbol,symbol),
                               '        if(%s< -32767) %s=-32767;'%(symbol,symbol)]
                else:
                    op='==' if n['kind']=='If equal' else '>='
                    output.append('        if(%s %s %d) {'%(symbol,op,value))
                walk(j,stack|{i})
                if n['kind'].startswith('If '):output.append('        }')
                continue
            if n['kind']=='Repeat':
                count=int(n.get('value',''))
                if not 1<=count<=16:raise ValueError('Repeat count must be 1..16.')
                for iteration in range(count):walk(j,stack|{i})
                continue
            if n['kind']=='Move to':
                if 'static void nc_move_to(' not in (root/'src/main.c').read_text():
                    raise ValueError('Move to requires the updated fixed-room runtime. Create a new Fixed Camera Room project.')
                parts=str(n.get('value','')).split(',')
                if len(parts)!=3:raise ValueError('Move to needs X, Z, frames (example: 2, 0, 120).')
                x,z=float(parts[0]),float(parts[1]);frames=int(parts[2])
                if not math.isfinite(x) or not math.isfinite(z) or not (-3<=x<=3 and -2<=z<=2 and 1<=frames<=36000):
                    raise ValueError('Move to: X -3..3, Z -2..2, frames 1..36000.')
                output.append('        nc_move_to(%.8ff, %.8ff, %d);'%(x,z,frames))
                walk(j,stack|{i});continue
            if n['kind'] in ('Once','Cooldown'):
                if n['kind']=='Once':
                    output.append('        if (!used_%d) { used_%d = 1;'%(j,j))
                else:
                    frames=int(n.get('value') or 0)
                    if not 1<=frames<=36000:raise ValueError('Cooldown must be 1..36000 frames.')
                    output.append('        if (tick >= next_%d) { next_%d = tick + %d;'%(j,j,frames))
                walk(j,stack|{i});output.append('        }');continue
            if n['kind'] not in actions:raise ValueError('Unsupported action: '+n['kind'])
            if n['kind']=='Stop movement' and 'if(action==3)' not in (root/'src/main.c').read_text():
                raise ValueError('Stop movement requires the updated fixed-room runtime.')
            opcode,limit=actions[n['kind']]
            value=int(n.get('value') or 0)
            if not 0<=value<=limit:raise ValueError('Invalid parameter for '+n['kind'])
            output.append('        nc_action(%d, %d);'%(opcode,value))
            walk(j,stack|{i})
    for n in nodes:
        kind=n['kind']; value=n.get('value','')
        if scoped and kind=='On exit':continue
        if kind=='On start':condition='entering' if scoped else 'start'
        elif kind=='On arrival':
            if 'static int nc_move_arrived;' not in (root/'src/main.c').read_text():
                raise ValueError('On arrival requires the updated fixed-room runtime.')
            condition='!start && nc_move_arrived'
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
        elif kind in actions or (scoped and kind=='Go to Flow Box') or kind in ('Once','Cooldown','Move to','Repeat') or kind in variable_kinds:continue
        else:raise ValueError('Unsupported PS2 node: '+kind)
        if incoming[n['id']]:raise ValueError('Events cannot have incoming links.')
        if scoped:
            if kind!='On start':condition='!entering && ('+condition+')'
            condition='active == %d && !pending && (%s)' % (n['section_id'],condition)
        output.append('    if (%s) {'%condition);walk(n['id'],set());output.append('    }')
    if scoped:
        for n in nodes:
            if n['kind']=='On exit':
                if incoming[n['id']]:raise ValueError('Events cannot have incoming links.')
                output.append('    if (pending && active == %d) {' % n['section_id'])
                walk(n['id'],set());output.append('    }')
    if reached!=set(lookup):raise ValueError('Every action must connect to an event.')
    output.append('}')
    (root/'src/nc_events.h').write_text('\n'.join(output)+'\n')
