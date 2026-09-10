"""Compile the small, target-aware NC-Code surface used by visual events.

NC-Code deliberately starts as a narrow language.  It gives authors named
functions and readable calls while keeping every operation inside the runtime
API that the selected console can actually provide.  Visual event nodes call
the same generated functions, so code and boxed actions remain two views of
one execution model.
"""
from pathlib import Path
import re

NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,47}")
FUNC = re.compile(r"func\s+([A-Za-z_][A-Za-z0-9_]{0,47})\s*\(\s*\)\s*:\s*$")
CALL = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\s*\(([^()]*)\)\s*$")

# C functions are available at the point nc_code_generated.h is included by
# the PS2 runtime.  Bounds are checked here, before the console sees the ELF.
PS2_CALLS = {
    "play_sound": ("nc_sfx_play(%d);", 0, 4095, 1, ('vn_v1',)),
    "play_music": ("nc_music_play(%d);", 0, 255, 1, ('vn_v1',)),
    "change_scene": ("nc_action(4, %d);", 0, 255, 1, ('vn_v1',)),
    "show_main_menu": ("nc_action(6, 0);", 0, 0, 0, ('vn_v1',)),
    "reset_game": ("nc_action(2, 0);", 0, 0, 0, ('fixed_room_v1','lab3d_v1','pad2d_v1')),
    "set_camera": ("nc_action(0, %d);", 0, 31, 1, ('fixed_room_v1',)),
    "interact": ("nc_action(1, 0);", 0, 0, 0, ('fixed_room_v1',)),
    "set_colour": ("nc_action(5, %d);", 0, 3, 1, ('lab3d_v1','pad2d_v1')),
}

STARTER = """# NC-Code is compiled into native console code during Build.
# Events can call this function with a Call NC-Code block.
func on_activate():
    play_sound(0)
"""


def _parse(path, adapter=None):
    functions = {}
    current = None
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if not line.startswith((" ", "\t")):
            match = FUNC.fullmatch(line)
            if not match:
                raise ValueError(f"{path.name} line {number}: expected func name():")
            current = match.group(1)
            if current in functions:
                raise ValueError(f"{path.name} line {number}: duplicate function {current}")
            functions[current] = []
            continue
        if "\t" in raw or not raw.startswith("    ") or current is None:
            raise ValueError(f"{path.name} line {number}: use four spaces inside a function")
        statement = line.strip()
        if statement == "pass":
            continue
        match = CALL.fullmatch(statement)
        if not match or match.group(1) not in PS2_CALLS:
            names = ", ".join(sorted(PS2_CALLS))
            raise ValueError(f"{path.name} line {number}: unsupported call; use {names}")
        name, text = match.groups()
        template, low, high, argc, adapters = PS2_CALLS[name]
        if adapter is not None and adapter not in adapters:
            raise ValueError(f"{path.name} line {number}: {name} is not available in the {adapter or 'unadapted'} PS2 runtime")
        args = [] if not text.strip() else [part.strip() for part in text.split(",")]
        if len(args) != argc:
            raise ValueError(f"{path.name} line {number}: {name} needs {argc} parameter(s)")
        value = None
        if argc:
            try:
                value = int(args[0], 0)
            except ValueError:
                raise ValueError(f"{path.name} line {number}: parameters are integers") from None
            if not low <= value <= high:
                raise ValueError(f"{path.name} line {number}: value must be {low}..{high}")
        functions[current].append(template % value if argc else template)
    return functions


def compile_project(project):
    """Validate project scripts and emit one safe C header. Returns names."""
    root = Path(project)
    try:
        import json
        adapter=json.loads((root/'nc.json').read_text(encoding='utf-8')).get('event_adapter','')
    except (OSError,ValueError):adapter=''
    scripts = root / "scripts"
    functions = {}
    for path in sorted(scripts.glob("*.nc")) if scripts.exists() else []:
        for name, body in _parse(path,adapter).items():
            if name in functions:
                raise ValueError(f"NC-Code function {name} exists in more than one script")
            functions[name] = (path.name, body)
    output = ["/* Generated from scripts/*.nc. Do not edit. */"]
    for name, (_source, body) in functions.items():
        output.append(f"static void nc_code_{name}(void) {{")
        output.extend("    " + line for line in body)
        output.append("}")
    (root / "src").mkdir(parents=True, exist_ok=True)
    (root / "src/nc_code_generated.h").write_text("\n".join(output) + "\n", encoding="utf-8")
    return set(functions)


def create(project, name):
    if not NAME.fullmatch(name):
        raise ValueError("Script names use letters, numbers, and underscores.")
    path = Path(project) / "scripts" / (name + ".nc")
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(STARTER, encoding="utf-8")
    return path
