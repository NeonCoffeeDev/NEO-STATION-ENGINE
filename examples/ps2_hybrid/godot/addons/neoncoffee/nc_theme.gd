@tool
extends RefCounted

## Dress the Godot editor to match NC Studio.
##
## Godot is not forked. Everything here goes through EditorSettings, which is
## the same set of knobs the Editor Settings dialog writes -- so nothing is
## patched, nothing breaks on upgrade, and the user can undo all of it from that
## dialog even if this plugin vanishes.
##
## Two things worth being honest about:
##
##   1. Editor settings are per USER, not per project. Theming the editor from
##      one Neon Coffee project themes it for every Godot project on the
##      machine. That is Godot's design, not a choice made here.
##   2. So the previous values are saved before anything is changed, and
##      "Restore Godot theme" puts them back exactly.

const BACKUP_PATH := "user://neoncoffee_theme_backup.cfg"

# The NC Studio palette, from tools/ncstudio/theme.py. Keeping the two in step
# by hand is a small cost for the two tools looking like one product.
const BASE      := Color("#14181a")   # panel body
const ACCENT    := Color("#ffb03a")   # amber, the primary accent
const CYAN      := Color("#5fd4d0")
const GREEN     := Color("#7fd98c")
const RED       := Color("#ff6b5e")
const FG        := Color("#c3d0cc")
const DIM       := Color("#6d7d79")
const SUNKEN    := Color("#050708")

const FONT      := "C:/Windows/Fonts/consola.ttf"
const FONT_BOLD := "C:/Windows/Fonts/consolab.ttf"

## The settings this plugin touches. Anything not listed is left alone.
##
## Keys are given as a list of candidates and the first one this Godot actually
## has is used. Godot has renamed several of these across 4.x -- the theme
## preset split into colour and spacing, the font settings moved under fonts/ --
## and a plugin that hard-codes one spelling silently does nothing on the
## versions that use the other.
static func _values() -> Array:
	return [
		# --- chrome ---
		# "Custom" is what makes base_color and accent_color take effect at all;
		# with a named preset selected Godot ignores both.
		[["interface/theme/color_preset", "interface/theme/preset"], "Custom"],
		[["interface/theme/spacing_preset"], "Custom"],
		[["interface/theme/base_color"], BASE],
		[["interface/theme/accent_color"], ACCENT],
		[["interface/theme/use_system_accent_color"], false],
		[["interface/theme/follow_system_theme"], false],
		[["interface/theme/contrast"], 0.35],
		[["interface/theme/draw_extra_borders"], true],
		# Square corners and a visible border is the mid-2000s tool look --
		# beveled panels rather than floating cards.
		[["interface/theme/corner_radius"], 0],
		[["interface/theme/border_size"], 1],
		[["interface/theme/base_spacing"], 3],
		[["interface/theme/additional_spacing"], 0.0],
		[["interface/theme/relationship_line_opacity"], 0.4],
		[["interface/theme/icon_saturation"], 0.85],

		# --- text ---
		# Consolas is what NC Studio uses, and a monospace UI font is half of why
		# a tool reads as a tool rather than as an application.
		[["interface/editor/fonts/main_font", "interface/editor/main_font"], FONT],
		[["interface/editor/fonts/main_font_bold", "interface/editor/main_font_bold"], FONT_BOLD],
		[["interface/editor/fonts/code_font", "interface/editor/code_font"], FONT],
		[["interface/editor/fonts/font_antialiasing", "interface/editor/font_antialiasing"], 1],
		[["interface/editor/fonts/font_hinting", "interface/editor/font_hinting"], 1],

		# --- script editor ---
		[["text_editor/theme/color_theme"], "Custom"],
		[["text_editor/theme/highlighting/background_color"], SUNKEN],
		[["text_editor/theme/highlighting/text_color"], FG],
		[["text_editor/theme/highlighting/comment_color"], DIM],
		[["text_editor/theme/highlighting/string_color"], GREEN],
		[["text_editor/theme/highlighting/number_color"], CYAN],
		[["text_editor/theme/highlighting/keyword_color"], ACCENT],
		[["text_editor/theme/highlighting/control_flow_keyword_color"], RED],
		[["text_editor/theme/highlighting/function_color"], CYAN],
		[["text_editor/theme/highlighting/member_variable_color"], FG],
		[["text_editor/theme/highlighting/current_line_color"], Color(0.12, 0.15, 0.16, 0.6)],
		[["text_editor/theme/highlighting/caret_color"], ACCENT],

		# --- viewport ---
		[["editors/2d/grid_color"], Color(0.25, 0.30, 0.32, 0.28)],
		[["editors/2d/guides_color"], CYAN],
		[["editors/3d/primary_grid_color"], Color(0.22, 0.28, 0.30)],
		[["editors/3d/secondary_grid_color"], Color(0.14, 0.18, 0.20)],
	]


static func _settings() -> EditorSettings:
	return EditorInterface.get_editor_settings()


## True when the current settings already look like ours. Used to avoid
## re-applying, and to label the menu item honestly.
static func is_applied() -> bool:
	var s := _settings()
	if s == null:
		return false
	if not s.has_setting("interface/theme/accent_color"):
		return false
	return s.get_setting("interface/theme/accent_color").is_equal_approx(ACCENT)


static func apply() -> Array:
	## Returns a list of settings that could not be applied, for reporting.
	var s := _settings()
	if s == null:
		return ["no editor settings available"]

	if not FileAccess.file_exists(BACKUP_PATH):
		_backup(s)

	var failed: Array = []
	for entry in _values():
		var candidates: Array = entry[0]
		var value = entry[1]

		# A font path that does not exist would leave the editor with no font at
		# all, which is a much worse outcome than an unthemed editor.
		if value is String and str(value).ends_with(".ttf"):
			if not FileAccess.file_exists(value):
				failed.append("%s: no font at %s" % [candidates[0], value])
				continue

		var key := _resolve(s, candidates)
		if key == "":
			# A Godot version that renamed a setting should not stop the rest of
			# the theme from applying.
			failed.append("%s: not a setting in this Godot" % candidates[0])
			continue
		s.set_setting(key, value)

	return failed


static func _resolve(s: EditorSettings, candidates: Array) -> String:
	for key in candidates:
		if s.has_setting(key):
			return key
	return ""


static func restore() -> bool:
	## Put back exactly what was there before apply() first ran.
	var s := _settings()
	if s == null:
		return false

	var cfg := ConfigFile.new()
	if cfg.load(BACKUP_PATH) != OK:
		return false

	for key in cfg.get_section_keys("editor_settings"):
		var real_key: String = key.replace("|", "/")
		if s.has_setting(real_key):
			s.set_setting(real_key, cfg.get_value("editor_settings", key))
	return true


static func _backup(s: EditorSettings) -> void:
	var cfg := ConfigFile.new()
	for entry in _values():
		var key := _resolve(s, entry[0])
		if key == "":
			continue
		# ConfigFile treats "/" as a section separator, so the key is flattened
		# on the way in and unflattened on the way out.
		cfg.set_value("editor_settings", key.replace("/", "|"), s.get_setting(key))
	cfg.save(BACKUP_PATH)
