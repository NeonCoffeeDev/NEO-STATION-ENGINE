@tool
extends EditorPlugin

## Turns the Godot editor into the Neon Coffee scene editor.
##
## Godot is not forked and not modified -- this is a plain editor plugin, which
## is why it survives Godot upgrades. See docs/ARCHITECTURE.md.
##
## What it adds:
##   - a toolbar button and a dock: export, build, run, check budgets
##   - buttons for the sprite flags the physics and the shake care about
##   - an editor theme that matches NC Studio, applied on request and reversible

const Exporter := preload("res://addons/neoncoffee/nc_export.gd")
const NCTheme := preload("res://addons/neoncoffee/nc_theme.gd")
const Dock := preload("res://addons/neoncoffee/nc_dock.gd")

var _button: Button
var _dock: Control


func _enter_tree() -> void:
	add_tool_menu_item("Neon Coffee: reload VN from Studio", _on_reload_vn)
	add_tool_menu_item("Neon Coffee: export VN essentials", _on_export_vn)
	_button = Button.new()
	_button.text = "  Export to NC  "
	_button.tooltip_text = "Write this scene to ../scene.json for the PS1 build"
	_button.pressed.connect(_on_export)
	add_control_to_container(CONTAINER_TOOLBAR, _button)

	_dock = Dock.new()
	add_control_to_dock(DOCK_SLOT_RIGHT_BL, _dock)

	# The theme is not applied on its own. Editor settings are per user, not per
	# project, so enabling a plugin in one project would silently restyle every
	# Godot project on the machine. Offer it; do not impose it.
	add_tool_menu_item("Neon Coffee: apply editor theme", _on_apply_theme)
	add_tool_menu_item("Neon Coffee: restore Godot theme", _on_restore_theme)


func _exit_tree() -> void:
	remove_tool_menu_item("Neon Coffee: reload VN from Studio")
	remove_tool_menu_item("Neon Coffee: export VN essentials")
	remove_tool_menu_item("Neon Coffee: apply editor theme")
	remove_tool_menu_item("Neon Coffee: restore Godot theme")

	if _dock:
		remove_control_from_docks(_dock)
		_dock.queue_free()
		_dock = null

	if _button:
		remove_control_from_container(CONTAINER_TOOLBAR, _button)
		_button.queue_free()
		_button = null


func _on_apply_theme() -> void:
	var failed: Array = NCTheme.apply()
	var body := "The editor now matches NC Studio.\n\n" \
		+ "This is an editor setting, so it applies to every Godot project on " \
		+ "this machine. Tools > Neon Coffee: restore Godot theme puts back " \
		+ "exactly what was there before."
	if not failed.is_empty():
		body += "\n\nNot applied:\n- " + "\n- ".join(failed)
	_report("Theme applied", body, true)


func _on_restore_theme() -> void:
	if NCTheme.restore():
		_report("Theme restored", "The editor is back to how it was.", true)
	else:
		_report("Nothing to restore",
			"No saved settings were found -- the NC theme was never applied "
			+ "from this machine. Editor Settings > Interface > Theme has the "
			+ "presets if you want to pick one by hand.", false)


func _on_export() -> void:
	var root := EditorInterface.get_edited_scene_root()
	if root == null:
		_report("Nothing to export", "Open a scene first.", false)
		return

	if root.has_method("to_kit"):
		_on_export_vn()
		return
	var result: Dictionary = Exporter.export_scene(root)
	if not result.get("ok", false):
		_report("Export failed", str(result.get("error", "unknown")), false)
		return

	var body := "%d mesh(es), %d instance(s)\nwritten to %s" % [
		result["mesh_count"], result["instance_count"], result["path"]]
	if not result["warnings"].is_empty():
		body += "\n\nWarnings:\n- " + "\n- ".join(result["warnings"])
	body += "\n\nBuild it from the Neon Coffee dock, or run:  ncc run <project>"
	_report("Exported", body, true)


func _report(title: String, body: String, ok: bool) -> void:
	print("[NC] %s: %s" % [title, body.replace("\n", " ")])
	var dlg := AcceptDialog.new()
	dlg.title = title
	dlg.dialog_text = body
	dlg.ok_button_text = "OK" if ok else "Close"
	EditorInterface.get_base_control().add_child(dlg)
	dlg.popup_centered()
	dlg.confirmed.connect(dlg.queue_free)
	dlg.canceled.connect(dlg.queue_free)


func _on_export_vn() -> void:
	var root := EditorInterface.get_edited_scene_root()
	if root == null or not root.has_method("export_project"):
		_report("VN export", "Open vn_authoring.tscn first.", false)
		return
	var problem: String = root.export_project()
	var note: String = root.export_warnings() if root.has_method("export_warnings") else ""
	_report("VN export", ("Saved layout and conversations. Use CHECK / BUILD to validate budgets." + note) if problem.is_empty() else problem, problem.is_empty())


func _on_reload_vn() -> void:
	var root := EditorInterface.get_edited_scene_root()
	if root == null or not root.has_method("reload_project"):
		return
	var problem: String = root.reload_project()
	if problem.is_empty():
		EditorInterface.mark_scene_as_unsaved()
	_report("VN reload", "Imported the saved Studio room and conversation. Save this scene to keep it." if problem.is_empty() else problem, problem.is_empty())
