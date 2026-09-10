@tool
class_name NCVNLine
extends Resource
@export var id: String = "line"
@export var speaker: String = ""
@export var scene: String = "cafe"
@export_multiline var text: String = ""
@export var next: String = ""
@export var give: String = ""
@export var choices: Array[NCVNChoice] = []
