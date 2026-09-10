"""Compile authored PS2 UI GameObjects into the small native menu contract."""
from pathlib import Path
import json
import re

ACTION_IDS = {
    "load:world3d": 1,
    "load:vn": 2,
    "load:ui_lab": 3,
    "open:options": 4,
    "open:title": 5,
}


def compile_project(project):
    root = Path(project)
    doc = json.loads((root / "screens.json").read_text(encoding="utf-8"))
    if doc.get("target") != "ps2":
        raise ValueError("screens.json must target ps2")
    screen = doc.get("screens", {}).get("main_menu")
    if not screen:
        raise ValueError("screens.json needs a main_menu screen")
    buttons = [o for o in screen.get("objects", [])
               if o.get("type") == "button" and o.get("visible", True)
               and o.get("isActive", True)]
    buttons.sort(key=lambda o: (int(o.get("layer", 0)), o.get("id", "")))
    if not 1 <= len(buttons) <= 8:
        raise ValueError("main_menu needs 1..8 active Button2D GameObjects")
    rows = []
    seen = set()
    for button in buttons:
        label = str(button.get("text", "")).strip().upper()
        action = str(button.get("action", "")).strip()
        if not label or len(label) > 28 or not re.fullmatch(r"[ A-Z0-9/&+_.:-]+", label):
            raise ValueError("menu button text uses 1..28 console-safe characters")
        if action not in ACTION_IDS:
            raise ValueError("%s needs an action: %s" %
                             (button.get("name", "Button"), ", ".join(ACTION_IDS)))
        if action in seen:
            raise ValueError("main_menu action is duplicated: " + action)
        seen.add(action)
        rows.append((label, ACTION_IDS[action]))
    out = ["/* Generated from screens.json. Do not edit. */",
           "#define NC_UI_MENU_COUNT %d" % len(rows),
           "enum { NC_UI_LOAD_WORLD3D=1, NC_UI_LOAD_VN, NC_UI_LOAD_LAB, NC_UI_OPTIONS, NC_UI_TITLE };",
           "static const char *const NC_UI_MENU_LABELS[NC_UI_MENU_COUNT] = {"]
    out += ['    "%s",' % label.replace('\\', '\\\\').replace('"', '\\"') for label, _ in rows]
    out += ["};", "static const unsigned char NC_UI_MENU_ACTIONS[NC_UI_MENU_COUNT] = {"]
    out += ["    %d," % action for _, action in rows]
    out += ["};", ""]
    target = root / "src" / "nc_ui_generated.h"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(out), encoding="utf-8")
    return rows
