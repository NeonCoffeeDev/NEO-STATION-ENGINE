"""Validated VN content shared by Studio and the PS2 build."""
import json
from pathlib import Path


def validate(doc):
    for key in ('title', 'subtitle'):
        value = doc.get(key)
        if not isinstance(value, str) or len(value) > 36:
            raise ValueError(f'{key}: use at most 36 characters')
    for key in ('story', 'about'):
        lines = doc.get(key)
        if not isinstance(lines, list) or not 1 <= len(lines) <= 200:
            raise ValueError(f'{key}: supply 1 to 200 lines')
        for i, line in enumerate(lines, 1):
            if not isinstance(line, str) or len(line) > 32:
                raise ValueError(f'{key} line {i}: maximum 32 characters; split this line')
    for value in [doc['title'], doc['subtitle'], *doc['story'], *doc['about']]:
        if any(ord(c) < 32 or ord(c) > 126 for c in value):
            raise ValueError('The current font supports printable ASCII only')
    scale = doc.get('logo_scale_x', 110)
    if type(scale) is not int or not 50 <= scale <= 200:
        raise ValueError('Logo width must be between 50 and 200 percent')
    return doc


def compile_content(project):
    root = Path(project)
    path = root / 'vn.json'
    if not path.exists():
        return
    doc = validate(json.loads(path.read_text(encoding='utf-8'), parse_float=lambda value: int(float(value)) if float(value).is_integer() else float(value)))
    if "kit" in doc:
        from .vnkit import compile_kit
        compile_kit(root, doc)
    lines = ['/* Generated from vn.json. Edit through Studio DESIGN. */',
             '#define NC_VN_TITLE ' + json.dumps(doc['title']),
             '#define NC_VN_SUBTITLE ' + json.dumps(doc['subtitle']),
             '#define NC_LOGO_SCALE_X ' + str(doc.get('logo_scale_x', 110))]
    for key in ('story', 'about'):
        name = key.upper()
        lines.append('static const char *' + name + '[] = {')
        lines.extend('    ' + json.dumps(s) + ',' for s in doc[key])
        lines.extend(['};', '#define ' + name + '_LINES ' + str(len(doc[key]))])
    dest = root / 'src' / 'vn_content.h'
    content = '\n'.join(lines) + '\n'
    if not dest.exists() or dest.read_text() != content:
        dest.write_text(content)
