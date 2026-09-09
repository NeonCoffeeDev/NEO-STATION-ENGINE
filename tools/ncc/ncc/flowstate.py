"""Shared validation for console-specific, box-owned event graphs."""
import json
from pathlib import Path

def validate(doc, project=None):
    if doc.get('version', 1) != 2:
        return None
    stages = doc.get('stages', [])
    ids = {s['id'] for s in stages}
    if not ids or len(ids) != len(stages) or len(ids) > 64:
        raise ValueError('Flow requires 1..64 uniquely identified boxes.')
    if any(type(i) is not int or not 1 <= i <= 65535 for i in ids):
        raise ValueError('Flow box IDs must be positive integers.')
    if doc.get('entry') not in ids:
        raise ValueError('Choose an existing entry flow box.')
    if project is not None:
        path=Path(project)/'game-structure.json'
        if path.exists():
            structure=json.loads(path.read_text(encoding='utf-8'))
            if structure.get('target')!=doc.get('target'):raise ValueError('Game flow map belongs to another console.')
            if not ids.issubset({s['id'] for s in structure['nodes']}):
                raise ValueError('An event-owned box was deleted from GAME FLOW; repair its events before enabling.')
    nodes = {n['id']: n for n in doc['nodes']}
    if len(nodes)!=len(doc['nodes']) or len(nodes)>128:
        raise ValueError('Events require unique IDs and at most 128 nodes.')
    for n in nodes.values():
        if n.get('section_id') not in ids:
            raise ValueError('Every event/action must belong to a flow box.')
        if n['kind'] == 'Go to Flow Box':
            if int(n.get('value', '0')) not in ids:
                raise ValueError('Transition destination does not exist.')
    for a, b in doc['edges']:
        if a not in nodes or b not in nodes:
            raise ValueError('Dangling event connection.')
        if nodes[a]['section_id'] != nodes[b]['section_id']:
            raise ValueError('Use Go to Flow Box instead of cross-box event wires.')
        if nodes[a]['kind'] == 'Go to Flow Box':
            raise ValueError('Go to Flow Box ends its chain; remove outgoing wires.')
    links = {i: [] for i in nodes}
    for a, b in doc['edges']:links[a].append(b)
    for n in nodes.values():
        if n['kind'] != 'On exit':continue
        todo = list(links[n['id']]);seen = set()
        while todo:
            i = todo.pop()
            if i in seen:continue
            seen.add(i)
            if nodes[i]['kind'] == 'Go to Flow Box':
                raise ValueError('Exit handlers cannot request another transition.')
            todo.extend(links[i])
    return ids
