"""Compile the initial PS1 event subset without modifying authored scripts."""
import json
import re
from pathlib import Path
from .flowstate import validate as validate_state

CALLS = {'Change room':'goto_scene', 'Show pooled object':'sprite_show',
         'Hide object':'sprite_hide', 'Play effect':'play_sound'}
BUTTONS = {'CROSS','CIRCLE','SQUARE','TRIANGLE','START','SELECT','UP','DOWN','LEFT','RIGHT','L1','R1','L2','R2'}

def compose(project, target, source):
    path=Path(project)/'event-flow.json'
    if not path.exists(): return source
    d=json.loads(path.read_text())
    if d.get('target') != target: raise ValueError('Event flow target differs from project target.')
    if d.get('status') == 'draft': return source
    if d.get('status') != 'enabled': raise ValueError('Unknown event flow status.')
    if target != 'ps1': raise ValueError('PS2 event execution is not implemented; keep this graph as a draft.')
    scoped=validate_state(d,project)
    nodes=d['nodes']; byid={n['id']:n for n in nodes}
    if len(byid)!=len(nodes): raise ValueError('Duplicate event node IDs.')
    links={i:[] for i in byid}; incoming={i:0 for i in byid}
    for a,b in d['edges']:
        if a not in byid or b not in byid: raise ValueError('Dangling event connection.')
        if b in links[a]: raise ValueError('Duplicate event connection.')
        links[a].append(b);incoming[b]+=1
    for n in nodes:
        if n['kind'] not in (*CALLS,'On start','On button', *(['Go to Flow Box','On exit'] if scoped else [])): raise ValueError('Unsupported event node: '+n['kind'])
        if n['kind'].startswith('On ') and incoming[n['id']]: raise ValueError('Events must be root nodes.')
    visiting=set();done=set()
    def check(i):
        if i in visiting: raise ValueError('Cycles are not supported in event flows.')
        if i in done:return
        visiting.add(i)
        for j in links[i]:check(j)
        visiting.remove(i);done.add(i)
    for i in byid:check(i)
    if '__ncflow_' in source: raise ValueError('__ncflow_ is reserved for visual events.')
    helpers=[];hooks={'_ready':[],'_update':[]};reached=set()
    def actions(i):
        result=[]
        for j in links[i]:
            reached.add(j);n=byid[j]
            try: value=int(n.get('value',''))
            except ValueError: raise ValueError('Node %s needs a non-negative numeric index.' % j)
            if value<0:raise ValueError('Negative action index.')
            if scoped and n['kind']=='Go to Flow Box':
                result += ['    if __ncflow_pending == 0:', '        __ncflow_pending = %d' % value]
            else:result.append('    %s(%d)' % (CALLS[n['kind']],value))
            result.extend(actions(j))
        return result
    dispatch=[];exits=[]
    for n in nodes:
        if n['kind'] not in ('On start','On button', *(['On exit'] if scoped else [])):continue
        reached.add(n['id']);name='__ncflow_'+str(n['id'])
        helpers+=['func '+name+'():']+(actions(n['id']) or ['    pass'])+['']
        if scoped and n['kind']=='On exit':
            exits += ['    if __ncflow_active == %d and __ncflow_pending != 0:' % n['section_id'], '        '+name+'()']
        elif scoped:
            condition='__ncflow_entering == 1'
            if n['kind']=='On button':
                button=n.get('value','').upper().removeprefix('BTN_')
                if button not in BUTTONS:raise ValueError('Unsupported button.')
                condition='__ncflow_entering == 0 and btn_pressed(BTN_'+button+')'
            dispatch += ['    if __ncflow_active == %d and __ncflow_pending == 0 and %s:' % (n['section_id'],condition), '        '+name+'()']
        elif n['kind']=='On start': hooks['_ready'].append('    '+name+'()')
        else:
            button=n.get('value','').upper().removeprefix('BTN_')
            if button not in BUTTONS:raise ValueError('On button needs a supported button name, e.g. CROSS.')
            hooks['_update']+=['    if btn_pressed(BTN_'+button+'):', '        '+name+'()']
    if reached != set(byid):raise ValueError('Every action must be connected to an event.')
    if scoped:
        source = ('var __ncflow_active = 0\nvar __ncflow_pending = 0\nvar __ncflow_entering = 0\n' + source)
        helpers += ['func __ncflow_step():', '    __ncflow_entering = 0',
                    '    if __ncflow_active == 0:', '        __ncflow_active = %d' % d['entry'],
                    '        __ncflow_entering = 1',
                    '    elif __ncflow_pending != 0:', '        __ncflow_active = __ncflow_pending',
                    '        __ncflow_pending = 0', '        __ncflow_entering = 1'] + dispatch + exits + ['']
        hooks['_update'] = ['    __ncflow_step()']
    for hook,lines in hooks.items():
        if not lines:continue
        pattern=r'(?m)^func '+hook+r'\(\):[^\n]*\n'
        if re.search(pattern,source):source=re.sub(pattern,lambda m:m[0]+'\n'.join(lines)+'\n',source,count=1)
        else:source+='\nfunc '+hook+'():\n'+'\n'.join(lines)+'\n'
    return source+'\n'+'\n'.join(helpers)+'\n'
