"""Small, target-specific learning recipes; inserted as editable draft nodes."""
KITS = {
    'ps1': {
        'Button to room': [('On button','START'),('Change room','0')],
        'Reveal pooled sprite': [('On button','CROSS'),('Show pooled object','0')],
        'Hide pooled sprite': [('On button','CIRCLE'),('Hide object','0')],
        'UI sound': [('On button','TRIANGLE'),('Play effect','0')],
    },
    'fixed_room_v1': {
        'Interact on arrival': [('On arrival',''),('Interact','0')],
        'Cancel automatic movement': [('On button','CIRCLE'),('Stop movement','0')],
        'Count three presses': [('On button','TRIANGLE'),('Add variable','presses, 1'),('If equal','presses, 3'),('Set camera','2')],
        'Initialize a score': [('On start',''),('Set variable','score, 0')],
        'Spend a token': [('On button','CIRCLE'),('If at least','tokens, 1'),('Add variable','tokens, -1'),('Interact','0')],
        'Grant three tokens': [('On button','SELECT'),('Repeat','3'),('Add variable','tokens, 1')],

        'Walk to the key': [('On button','SQUARE'),('Move to','-2, 1.5, 90')],
        'Interaction with cooldown': [('On button','CROSS'),('Cooldown','20'),('Interact','0')],
        'One-time camera reveal': [('On zone','1'),('Once',''),('Set camera','1')],
        'Delayed establishing shot': [('After frames','180'),('Set camera','2')],
        'Timed camera demonstration': [('Every frames','300'),('Set camera','0')],
        'Restart button': [('On button','START'),('Reset game','0')],
    },
}

def available(meta):
    key='ps1' if meta['target']=='ps1' else meta.get('event_adapter')
    return KITS.get(key,{})

def insert(nodes,edges,recipe):
    """Return newly appended IDs; never alter or connect existing nodes."""
    first=max([n['id'] for n in nodes],default=0)+1
    y=max([n.get('y',0) for n in nodes],default=-100)+120
    ids=[]
    for offset,(kind,value) in enumerate(recipe):
        ident=first+offset
        nodes.append(dict(id=ident,kind=kind,value=value,x=20+offset*190,y=y))
        if ids:edges.append([ids[-1],ident])
        ids.append(ident)
    return ids
