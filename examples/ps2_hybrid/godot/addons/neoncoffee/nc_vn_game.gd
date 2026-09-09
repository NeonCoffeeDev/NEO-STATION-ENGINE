@tool
class_name NCVNGame
extends Node2D
## Inspector authoring for the native PS2 conversation kit.
## Save this scene, then Tools > Neon Coffee: export VN essentials.
@export var preview_scene: int = 0
@export var preview_character: int = 0
@export var start: String = "welcome"
@export_range(1, 10) var frames_per_character: int = 2
@export var characters: Array[NCVNCharacter] = []
@export var scenes: Array[NCVNLocation] = []
@export var items: Array[NCVNItem] = []
@export var dialogue: Array[NCVNLine] = []

func asset_path(path: String) -> String:
	return "godot/" + path.trim_prefix("res://") if not path.is_empty() else ""

func to_kit() -> Dictionary:
	var kit: Dictionary = {"start": start, "frames_per_character": frames_per_character,
		"characters": [], "scenes": [], "items": [], "dialogue": []}
	for c in characters:
		if c != null:
			kit.characters.append({"id": c.id, "name": c.display_name, "portrait": asset_path(c.portrait)})
	for s in scenes:
		if s != null:
			kit.scenes.append({"id": s.id, "background": asset_path(s.background),
				"color": [s.color.r8, s.color.g8, s.color.b8]})
	for item in items:
		if item != null:
			kit.items.append({"id": item.id, "name": item.display_name})
	for line in dialogue:
		if line == null:
			continue
		var options: Array = []
		for choice in line.choices:
			if choice != null:
				options.append({"text": choice.text, "next": choice.next,
					"requires": choice.requires, "give": choice.give})
		kit.dialogue.append({"id": line.id, "speaker": line.speaker, "scene": line.scene,
			"text": line.text, "next": line.next, "give": line.give, "choices": options})
	kit["layout"] = {}
	for key in ["background", "portrait", "dialogue"]:
		var visual := get_node_or_null(NodePath(key.capitalize())) as Control
		if visual != null:
			kit.layout[key] = [roundi(visual.position.x), roundi(visual.position.y), roundi(visual.size.x * visual.scale.x), roundi(visual.size.y * visual.scale.y)]
	return kit


## Nodes the exporter does not read. Adding a TextureRect in the 2D view is the
## natural way to try to put a second character on screen, and it is silently
## ignored: portraits come from the characters array and the slots in Studio's
## ROOM tab, not from nodes. Saying so is the difference between a five-minute
## correction and an evening lost to an export that reported success.
func export_warnings() -> String:
	var known := ["Background", "Portrait", "Dialogue", "SafeArea"]
	var ignored: Array[String] = []
	for child in get_children():
		if child is CanvasItem and not known.has(child.name):
			ignored.append(str(child.name))
	if ignored.is_empty():
		return ""
	return ("\n\nIgnored: %s. Extra nodes in this scene are not exported. "
		+ "To put another character on screen, add them to the Characters array "
		+ "and cast them into a portrait slot (Studio: ROOM > ADD SPRITE / SLOT, "
		+ "then EDIT CONVERSATION > ON SCREEN).") % ", ".join(ignored)


func export_project() -> String:
	if position != Vector2.ZERO or not is_zero_approx(rotation) or scale != Vector2.ONE:
		return "Keep the VN root transform at default; move the Background/Portrait/Dialogue children."
	for name in ["Background", "Portrait", "Dialogue"]:
		var visual := get_node_or_null(NodePath(name)) as Control
		if visual != null and (not is_zero_approx(visual.rotation) or visual.scale.x <= 0 or visual.scale.y <= 0):
			return name + ": rotation/flipping are not supported by the VN layout exporter."
	var base := ProjectSettings.globalize_path("res://").trim_suffix("/").get_base_dir()
	var path := base.path_join("vn.json")
	var doc = JSON.parse_string(FileAccess.get_file_as_string(path))
	if not doc is Dictionary:
		return "Expected vn.json beside the godot folder."
	doc["kit"] = to_kit()
	var file := FileAccess.open(path + ".tmp", FileAccess.WRITE)
	if file == null:
		return "Cannot write vn.json.tmp"
	file.store_string(JSON.stringify(doc, "  "))
	file.close()
	return "" if DirAccess.rename_absolute(path + ".tmp", path) == OK else "Cannot replace vn.json"


var _last_preview: String = ""
func _process(_delta: float) -> void:
	if not Engine.is_editor_hint():
		return
	var bg: String = scenes[preview_scene].background if preview_scene >= 0 and preview_scene < scenes.size() and scenes[preview_scene] != null else ""
	var portrait: String = characters[preview_character].portrait if preview_character >= 0 and preview_character < characters.size() and characters[preview_character] != null else ""
	var stamp := bg + "|" + portrait
	if stamp == _last_preview:
		return
	_last_preview = stamp
	for pair in [["Background", bg], ["Portrait", portrait]]:
		var visual := get_node_or_null(NodePath(pair[0])) as TextureRect
		if visual != null:
			visual.texture = load(pair[1]) as Texture2D if not str(pair[1]).is_empty() else null


func reload_project() -> String:
	var base := ProjectSettings.globalize_path("res://").trim_suffix("/").get_base_dir()
	var doc = JSON.parse_string(FileAccess.get_file_as_string(base.path_join("vn.json")))
	if not doc is Dictionary or not doc.has("kit"):
		return "No VN kit found."
	var kit: Dictionary = doc.kit
	start = kit.get("start", start)
	frames_per_character = int(kit.get("frames_per_character", 2))
	characters.clear()
	for c in kit.get("characters", []):
		var item := NCVNCharacter.new()
		item.id = c.id
		item.display_name = c.get("name", c.id)
		item.portrait = "res://" + str(c.portrait).trim_prefix("godot/") if not str(c.get("portrait", "")).is_empty() else ""
		characters.append(item)
	scenes.clear()
	for c in kit.get("scenes", []):
		var item := NCVNLocation.new()
		item.id = c.id
		item.background = "res://" + str(c.background).trim_prefix("godot/") if not str(c.get("background", "")).is_empty() else ""
		var col: Array = c.get("color", [20,24,26])
		item.color = Color8(int(col[0]), int(col[1]), int(col[2]))
		scenes.append(item)
	items.clear()
	for c in kit.get("items", []):
		var item := NCVNItem.new()
		item.id = c.id
		item.display_name = c.get("name", c.id)
		items.append(item)
	dialogue.clear()
	for c in kit.get("dialogue", []):
		var item := NCVNLine.new()
		for key in ["id", "speaker", "scene", "text", "next", "give"]:
			item.set(key, c.get(key, ""))
		for opt in c.get("choices", []):
			var choice := NCVNChoice.new()
			for key in ["text", "next", "requires", "give"]:
				choice.set(key, opt.get(key, ""))
			item.choices.append(choice)
		dialogue.append(item)
	for key in kit.get("layout", {}):
		var visual := get_node_or_null(NodePath(str(key).capitalize())) as Control
		var rect: Array = kit.layout[key]
		if visual != null and rect.size() == 4:
			visual.position = Vector2(rect[0],rect[1])
			visual.size = Vector2(rect[2],rect[3])
	_last_preview = ""
	return ""


func _ready() -> void:
	if Engine.is_editor_hint():
		EditorInterface.set_main_screen_editor("2D")
