"""Compile the initial PS1 event subset without modifying authored scripts."""
import json
import re
from pathlib import Path
from .flowstate import validate as validate_state
from .triggercode import predicates

CALLS = {'Change room':'goto_scene', 'Show pooled object':'sprite_show',
         'Hide object':'sprite_hide', 'Play effect':'play_sound', 'Show mesh':'show', 'Hide mesh':'hide'}
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
    trigger_conditions=predicates(project,'ps1')
    extra_events=('On trigger enter','On trigger exit','After frames','Every frames')
    extra_actions=('Set sprite position','Set object position')
    nodes=d['nodes']; byid={n['id']:n for n in nodes}
    if len(byid)!=len(nodes): raise ValueError('Duplicate event node IDs.')
    links={i:[] for i in byid}; incoming={i:0 for i in byid}
    for a,b in d['edges']:
        if a not in byid or b not in byid: raise ValueError('Dangling event connection.')
        if b in links[a]: raise ValueError('Duplicate event connection.')
        links[a].append(b);incoming[b]+=1
    for n in nodes:
        if n['kind'] not in (*CALLS,*extra_events,*extra_actions,'On start','On button', *(['Go to Flow Box','On exit'] if scoped else [])): raise ValueError('Unsupported event node: '+n['kind'])
        if (n['kind'].startswith('On ') or n['kind'] in extra_events) and incoming[n['id']]: raise ValueError('Events must be root nodes.')
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
            if n['kind'] in extra_actions:
                values=[int(v.strip()) for v in n.get('value','').split(',')]
                count=3 if n['kind']=='Set sprite position' else 4
                if len(values)!=count or values[0]<0 or any(abs(v)>32767 for v in values):raise ValueError('Position action needs object index, then integer coordinates.')
                result.append('    %s(%s)' % ('sprite_set_pos' if count==3 else 'set_pos', ', '.join(map(str,values))))
                result.extend(actions(j));continue
            try: value=int(n.get('value',''))
            except ValueError: raise ValueError('Node %s needs a non-negative numeric index.' % j)
            if value<0:raise ValueError('Negative action index.')
            if scoped and n['kind']=='Go to Flow Box':
                result += ['    if __ncflow_pending == 0:', '        __ncflow_pending = %d' % value]
            else:result.append('    %s(%d)' % (CALLS[n['kind']],value))
            result.extend(actions(j))
        return result
    dispatch=[];exits=[];poll=[];trigger_globals=[]
    for tid,condition in trigger_conditions.items():
        trigger_globals += [f'var __ncflow_inside_{tid} = 0',f'var __ncflow_hit_{tid} = 0',f'var __ncflow_enter_{tid} = 0',f'var __ncflow_leave_{tid} = 0']
        poll += [f'    __ncflow_hit_{tid} = {condition}',f'    __ncflow_enter_{tid} = __ncflow_hit_{tid} and not __ncflow_inside_{tid}',f'    __ncflow_leave_{tid} = not __ncflow_hit_{tid} and __ncflow_inside_{tid}',f'    __ncflow_inside_{tid} = __ncflow_hit_{tid}']
    source='\n'.join(trigger_globals)+'\n'+source
    for n in nodes:
        if n['kind'] not in ('On start','On button', *extra_events, *(['On exit'] if scoped else [])):continue
        reached.add(n['id']);name='__ncflow_'+str(n['id'])
        helpers+=['func '+name+'():']+(actions(n['id']) or ['    pass'])+['']
        event_condition=None
        if n['kind'] in ('On trigger enter','On trigger exit'):
            tid=int(n.get('value',''))
            if tid not in trigger_conditions:raise ValueError('Trigger ID does not exist; create it in VIEWPORT.')
            event_condition=('__ncflow_enter_' if n['kind']=='On trigger enter' else '__ncflow_leave_')+str(tid)
        elif n['kind'] in ('After frames','Every frames'):
            frames=int(n.get('value',''))
            if not 1<=frames<=36000:raise ValueError('Timer must be 1..36000 frames.')
            event_condition=('__ncflow_tick == %d' if n['kind']=='After frames' else '__ncflow_tick > 0 and __ncflow_tick %% %d == 0') % frames
        if scoped and n['kind']=='On exit':
            exits += ['    if __ncflow_active == %d and __ncflow_pending != 0:' % n['section_id'], '        '+name+'()']
        elif scoped:
            condition='__ncflow_entering == 1'
            if n['kind']=='On button':
                button=n.get('value','').upper().removeprefix('BTN_')
                if button not in BUTTONS:raise ValueError('Unsupported button.')
                condition='__ncflow_entering == 0 and btn_pressed(BTN_'+button+')'
            if event_condition:condition='__ncflow_entering == 0 and '+event_condition
            dispatch += ['    if __ncflow_active == %d and __ncflow_pending == 0 and %s:' % (n['section_id'],condition), '        '+name+'()']
        elif n['kind']=='On start': hooks['_ready'].append('    '+name+'()')
        elif event_condition:hooks['_update'] += ['    if '+event_condition+':','        '+name+'()']
        else:
            button=n.get('value','').upper().removeprefix('BTN_')
            if button not in BUTTONS:raise ValueError('On button needs a supported button name, e.g. CROSS.')
            hooks['_update']+=['    if btn_pressed(BTN_'+button+'):', '        '+name+'()']
    if reached != set(byid):raise ValueError('Every action must be connected to an event.')
    source='var __ncflow_tick = 0\n'+source
    if scoped:
        source = ('var __ncflow_active = 0\nvar __ncflow_pending = 0\nvar __ncflow_entering = 0\n' + source)
        helpers += ['func __ncflow_step():', '    __ncflow_entering = 0',
                    '    if __ncflow_active == 0:', '        __ncflow_active = %d' % d['entry'],
                    '        __ncflow_entering = 1',
                    '    elif __ncflow_pending != 0:', '        __ncflow_active = __ncflow_pending',
                    '        __ncflow_pending = 0', '        __ncflow_entering = 1'] + ['    if __ncflow_entering:', '        __ncflow_tick = 0', '    elif __ncflow_tick < 2147483647:', '        __ncflow_tick = __ncflow_tick + 1'] + poll + dispatch + exits + ['']
        hooks['_update'] = ['    __ncflow_step()']
    else:
        hooks['_ready'].insert(0,'    __ncflow_tick = 0')
        hooks['_update'] = ['    if __ncflow_tick < 2147483647:', '        __ncflow_tick = __ncflow_tick + 1'] + poll + hooks['_update']
    for hook,lines in hooks.items():
        if not lines:continue
        pattern=r'(?m)^func '+hook+r'\(\):[^\n]*\n'
        if re.search(pattern,source):source=re.sub(pattern,lambda m:m[0]+'\n'.join(lines)+'\n',source,count=1)
        else:source+='\nfunc '+hook+'():\n'+'\n'.join(lines)+'\n'
    return source+'\n'+'\n'.join(helpers)+'\n'
