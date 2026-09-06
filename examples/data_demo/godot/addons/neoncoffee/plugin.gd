@tool
extends EditorPlugin

## Adds an "Export to NC" button to the editor toolbar.
##
## Godot is not forked and not modified -- this is a plain editor plugin, which
## is why it survives Godot upgrades. See docs/ARCHITECTURE.md.

const Exporter := preload("res://addons/neoncoffee/nc_export.gd")

var _button: Button


func _enter_tree() -> void:
	_button = Button.new()
	_button.text = "  Export to NC  "
	_button.tooltip_text = "Write this scene to ../scene.json for the PS1 build"
	_button.pressed.connect(_on_export)
	add_control_to_container(CONTAINER_TOOLBAR, _button)


func _exit_tree() -> void:
	if _button:
		remove_control_from_container(CONTAINER_TOOLBAR, _button)
		_button.queue_free()
		_button = null


func _on_export() -> void:
	var root := get_editor_interface().get_edited_scene_root()
	if root == null:
		_report("Nothing to export", "Open a scene first.", false)
		return

	var result: Dictionary = Exporter.export_scene(root)
	if not result.get("ok", false):
		_report("Export failed", str(result.get("error", "unknown")), false)
		return

	var body := "%d mesh(es), %d instance(s)\nwritten to %s" % [
		result["mesh_count"], result["instance_count"], result["path"]]
	if not result["warnings"].is_empty():
		body += "\n\nWarnings:\n- " + "\n- ".join(result["warnings"])
	body += "\n\nNow press F5 in NC Studio, or run:  ncc run <project>"
	_report("Exported", body, true)


func _report(title: String, body: String, ok: bool) -> void:
	print("[NC] %s: %s" % [title, body.replace("\n", " ")])
	var dlg := AcceptDialog.new()
	dlg.title = title
	dlg.dialog_text = body
	dlg.ok_button_text = "OK" if ok else "Close"
	get_editor_interface().get_base_control().add_child(dlg)
	dlg.popup_centered()
	dlg.confirmed.connect(dlg.queue_free)
	dlg.canceled.connect(dlg.queue_free)
