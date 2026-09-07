@tool
extends VBoxContainer

## The Neon Coffee dock: export, build, run, and the budgets, without leaving
## Godot.
##
## The point is to close the loop. Laying out a scene and then alt-tabbing to a
## terminal to find out it does not fit is the slow way to learn a 2 MB machine;
## a button that says "3 of 8 texture slots" while you work is the fast one.

const Exporter := preload("res://addons/neoncoffee/nc_export.gd")

const BG        := Color("#0a0c0d")
const PANEL     := Color("#14181a")
const PANEL_HI  := Color("#1d2427")
const SUNKEN    := Color("#050708")
const BORDER    := Color("#2e3639")
const FG        := Color("#c3d0cc")
const DIM       := Color("#6d7d79")
const AMBER     := Color("#ffb03a")
const GREEN     := Color("#7fd98c")
const RED       := Color("#ff6b5e")
const CYAN      := Color("#5fd4d0")

var _log: RichTextLabel
var _status: Label
var _project_dir: String = ""
var _ncc: String = ""
var _busy := false


func _ready() -> void:
	name = "Neon Coffee"
	_project_dir = _find_project_dir()
	_ncc = _find_ncc()
	_build_ui()
	_refresh_status()


# ---- layout ---------------------------------------------------------------

func _panel(colour: Color) -> StyleBoxFlat:
	var sb := StyleBoxFlat.new()
	sb.bg_color = colour
	sb.border_color = BORDER
	sb.set_border_width_all(1)
	sb.set_corner_radius_all(0)
	sb.content_margin_left = 6
	sb.content_margin_right = 6
	sb.content_margin_top = 4
	sb.content_margin_bottom = 4
	return sb


func _heading(text: String) -> Label:
	var l := Label.new()
	l.text = text
	l.add_theme_color_override("font_color", CYAN)
	l.add_theme_font_size_override("font_size", 11)
	return l


func _button(text: String, colour: Color, action: Callable) -> Button:
	var b := Button.new()
	b.text = text
	b.add_theme_color_override("font_color", colour)
	b.add_theme_color_override("font_hover_color", Color.WHITE)
	b.add_theme_stylebox_override("normal", _panel(PANEL_HI))
	b.add_theme_stylebox_override("hover", _panel(BORDER))
	b.add_theme_stylebox_override("pressed", _panel(SUNKEN))
	b.pressed.connect(action)
	return b


func _build_ui() -> void:
	add_theme_constant_override("separation", 4)

	var bg := _panel(BG)
	add_theme_stylebox_override("panel", bg)

	add_child(_heading("PROJECT"))

	_status = Label.new()
	_status.add_theme_color_override("font_color", DIM)
	_status.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	add_child(_status)

	add_child(HSeparator.new())
	add_child(_heading("BUILD"))

	add_child(_button("EXPORT TO NC", CYAN, _on_export))
	add_child(_button("EXPORT + BUILD", AMBER, _on_build))
	add_child(_button("EXPORT + BUILD + RUN", GREEN, _on_run))
	add_child(_button("CHECK BUDGETS", CYAN, _on_check))

	add_child(HSeparator.new())
	add_child(_heading("SELECTED SPRITES"))

	var hint := Label.new()
	hint.text = "Solid sprites are ground and walls. Fixed sprites ignore screen shake."
	hint.add_theme_color_override("font_color", DIM)
	hint.add_theme_font_size_override("font_size", 10)
	hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	add_child(hint)

	add_child(_button("MARK SOLID", AMBER, func(): _mark("solid", true)))
	add_child(_button("CLEAR SOLID", DIM, func(): _mark("solid", false)))
	add_child(_button("MARK FIXED", AMBER, func(): _mark("fixed", true)))
	add_child(_button("CLEAR FIXED", DIM, func(): _mark("fixed", false)))

	add_child(HSeparator.new())
	add_child(_heading("OUTPUT"))

	_log = RichTextLabel.new()
	_log.bbcode_enabled = true
	_log.scroll_following = true
	_log.custom_minimum_size = Vector2(0, 180)
	_log.size_flags_vertical = Control.SIZE_EXPAND_FILL
	_log.add_theme_stylebox_override("normal", _panel(SUNKEN))
	_log.add_theme_color_override("default_color", FG)
	add_child(_log)


# ---- where things are -----------------------------------------------------

func _find_project_dir() -> String:
	## The Neon Coffee project is the folder above the Godot one.
	var godot_dir := ProjectSettings.globalize_path("res://").rstrip("/\\")
	var parent := godot_dir.get_base_dir()
	if FileAccess.file_exists(parent.path_join("CMakeLists.txt")):
		return parent
	return ""


func _find_ncc() -> String:
	## Walk up from the project looking for the ncc launcher.
	##
	## A project created inside the Neon Coffee tree finds it; one created
	## elsewhere falls back to whatever `ncc` is on PATH, which is the right
	## answer for an installed toolchain.
	var dir := _project_dir
	var launcher := "ncc.cmd" if OS.get_name() == "Windows" else "ncc"
	for _i in range(8):
		if dir == "" :
			break
		var candidate := dir.path_join(launcher)
		if FileAccess.file_exists(candidate):
			return candidate
		var up := dir.get_base_dir()
		if up == dir:
			break
		dir = up
	return launcher


# ---- reporting ------------------------------------------------------------

func _say(text: String, colour: Color = FG) -> void:
	_log.append_text("[color=#%s]%s[/color]\n" % [colour.to_html(false), text])


func _refresh_status() -> void:
	if _project_dir == "":
		_status.text = "No Neon Coffee project above this Godot folder."
		_status.add_theme_color_override("font_color", RED)
		return
	_status.text = "%s\nncc: %s" % [_project_dir.get_file(), _ncc]
	_status.add_theme_color_override("font_color", DIM)


# ---- actions --------------------------------------------------------------

func _on_export() -> bool:
	var root := EditorInterface.get_edited_scene_root()
	if root == null:
		_say("Open a scene first.", RED)
		return false

	var result: Dictionary = Exporter.export_scene(root)
	if not result.get("ok", false):
		_say("Export failed: " + str(result.get("error", "unknown")), RED)
		return false

	_say("Exported %d mesh(es), %d instance(s) -> %s" % [
		result["mesh_count"], result["instance_count"],
		str(result["path"]).get_file()], GREEN)
	for w in result["warnings"]:
		_say("  warning: " + str(w), AMBER)
	return true


func _on_build() -> void:
	if _on_export():
		_run_ncc(["build", _project_dir])


func _on_run() -> void:
	if _on_export():
		_run_ncc(["run", _project_dir])


func _on_check() -> void:
	_run_ncc(["check", _project_dir])


func _run_ncc(args: Array) -> void:
	if _busy:
		_say("Still working.", AMBER)
		return
	if _project_dir == "":
		_say("No project to build.", RED)
		return

	_busy = true
	_say("> ncc " + " ".join(args.map(func(a): return str(a).get_file())), CYAN)

	# The editor blocks while this runs. That is deliberate: a build takes a
	# couple of seconds, and a progress-free background task that might still be
	# writing the disc image when you press Run is worse than a short pause.
	var output: Array = []
	var argv: Array = args.duplicate()
	var exe := _ncc
	if OS.get_name() == "Windows":
		# .cmd is a shell script, not an executable.
		argv = ["/c", _ncc] + argv
		exe = "cmd.exe"

	var code := OS.execute(exe, PackedStringArray(argv), output, true)
	_busy = false

	for line in output:
		for one in str(line).split("\n"):
			var trimmed := str(one).strip_edges()
			if trimmed == "":
				continue
			var colour := FG
			if trimmed.begins_with("ok") or trimmed.find("No problems") >= 0:
				colour = GREEN
			elif trimmed.find("error") >= 0 or trimmed.find("ERROR") >= 0:
				colour = RED
			elif trimmed.find("warning") >= 0 or trimmed.find("WILL NOT") >= 0:
				colour = AMBER
			_say("  " + trimmed, colour)

	if code != 0:
		_say("ncc exited %d" % code, RED)


func _mark(key: String, on: bool) -> void:
	## Sprite flags live in node metadata rather than in a custom node type, so
	## any Sprite2D works -- including ones from a scene you already had. Setting
	## metadata by hand in the inspector is fiddly enough that a button earns its
	## place here.
	var nodes := EditorInterface.get_selection().get_selected_nodes()
	var touched := 0
	for node in nodes:
		if not (node is Sprite2D):
			continue
		if on:
			node.set_meta(key, true)
		elif node.has_meta(key):
			node.remove_meta(key)
		touched += 1

	if touched == 0:
		_say("Select one or more Sprite2D nodes first.", AMBER)
		return

	_say("%s %s on %d sprite(s)." % ["Set" if on else "Cleared", key, touched],
		GREEN if on else DIM)
	# Mark the scene dirty so the change is actually saved.
	EditorInterface.mark_scene_as_unsaved()
