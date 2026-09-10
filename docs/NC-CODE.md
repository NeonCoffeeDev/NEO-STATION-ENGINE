# NC-Code

NC-Code is NEO-STATION's project-owned scripting layer. It is compiled into
native console code during **Build** and shares its functions with the visual
Events graph. It is not GDScript and it is not interpreted on the console.

For the current PS2 authoring milestone, attach **NC-Code Script** from the
Components / Inspector dock. Studio creates a file under `scripts/`, attaches
it to the selected GameObject, and opens it in the SCRIPT panel.

```text
func on_activate():
    play_sound(0)
```

In EVENTS, add **Call NC-Code**, choose `on_activate`, and connect it after an
event such as **On button**. The visual node and the script compile into the
same native event function.

Currently supported PS2 calls are validated against the selected runtime:

- Hybrid/VN: `play_sound(index)`, `play_music(index)`,
  `change_scene(index)`, `show_main_menu()`
- Fixed camera: `reset_game()`, `set_camera(index)`, `interact()`
- 3D Lab and pad demo: `reset_game()`, `set_colour(index)`

The compiler rejects missing functions, unsupported calls, invalid indentation,
and out-of-range numeric parameters before creating the ELF. PS1 NC-Code is
scaffolded as a later target-specific backend; the existing PS1 NCScript path
continues to build PS1 projects.
