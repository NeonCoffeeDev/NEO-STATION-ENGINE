@tool
extends RefCounted

## Turns a Godot 3D scene into the scene.json that `ncc build` compiles to .ncpkg.
##
## Coordinate systems
## ------------------
## Godot is Y-up and looks down -Z. The PS1 runtime is Y-down (screen space) and
## looks down +Z. So a point converts as (x, -y, -z), scaled from metres to PS1
## units. Flipping two axes is a rotation, not a mirror, so winding order -- and
## therefore which faces survive backface culling -- is preserved.
##
## Positions are exported in WORLD SPACE, and the Camera3D is exported alongside
## them. The runtime has a real camera, so it applies the inverse transform
## itself -- the viewpoint can move at run time instead of being baked in.
##
## Multiple game scenes
## --------------------
## One Godot scene can hold several NC scenes (a menu, level 1, ...). Any direct
## child of the root named "Scene..." -- or carrying metadata "nc_scene" -- is
## exported as its own NC scene, in order. Give each one its own Camera3D to
## frame it. Hiding a group in the editor still exports it; only individual
## MeshInstance3D visibility is honoured.
##
## With no such groups the whole scene is exported as scene 0.
##
## Each group is exported RELATIVE TO ITSELF, so moving a group around the editor
## to keep scenes from overlapping does not leak into the game -- every scene
## starts at its own origin.
##
## Meshes are shared across every scene, so a prop used in two levels ships once.
##
## Textures and sprites
## --------------------
## A MeshInstance3D whose material has an albedo texture gets that texture
## exported to ../textures/ as a PNG and referenced from scene.json. Sprite2D
## nodes are exported as 2D sprites in screen space.
##
## The PS1 has eight texture slots of at most 256x240, so oversized images are
## rejected with a warning rather than silently rescaled into mush.

const SCALE := 100.0          ## PS1 units per Godot metre
const OUT_PATH := "res://../scene.json"

## The PS1 has no depth buffer and a small polygon budget. These are the points
## where a scene stops being plausible on the hardware, not hard limits.
const WARN_VERTS_PER_MESH := 256
const WARN_TOTAL_QUADS := 900

## Hardware limits, mirrored from tools/ncc/ncc/textures.py.
const MAX_TEXTURES := 8
const MAX_TEX_W := 256
const MAX_TEX_H := 240
const TEXTURE_DIR := "res://../textures"

## Rotation on the PS1 is a 16-bit angle where 4096 is one full turn.
const TURN := 4096.0


static func export_scene(root: Node) -> Dictionary:
	var warnings: Array[String] = []
	var meshes: Array = []
	var mesh_index := {}          ## cache key -> index into `meshes`
	var instances: Array = []

	var textures: Array = []
	var texture_cache := {}

	var groups := _find_scene_groups(root)
	var grouped := not groups.is_empty()
	if not grouped:
		groups = [root]

	var scenes: Array = []

	for group in groups:
		# Positions are relative to the group, so the offset you give a group to
		# keep it clear of the others in the viewport stays an editor concern.
		var origin := Transform3D.IDENTITY
		if grouped and group is Node3D and not (group is Node2D):
			origin = group.global_transform.affine_inverse()

		var cam := _find_camera(group)
		if cam == null:
			cam = _find_camera(root)

		var nodes: Array[MeshInstance3D] = []
		_collect(group, nodes)

		instances = []
		for node in nodes:
			if not node.visible:
				continue
			if node.mesh == null:
				continue

			var world := origin * node.global_transform
			var scale_v := node.global_transform.basis.get_scale()

			# Meshes are keyed by resource and scale, so the same prop at the
			# same size is stored once no matter how many scenes use it.
			var key := "%s|%.4f,%.4f,%.4f" % [node.mesh.get_rid(),
				scale_v.x, scale_v.y, scale_v.z]
			var idx: int = mesh_index.get(key, -1)
			if idx == -1:
				var built := _build_mesh(node.mesh, scale_v, node.name)
				if built.has("error"):
					warnings.append("%s: %s" % [node.name, built["error"]])
					continue
				for w in built.get("warnings", []):
					warnings.append("%s: %s" % [node.name, w])
				idx = meshes.size()
				var entry := {
					"name": "m%d" % idx,
					"verts": built["verts"],
					"quads": built["quads"],
				}
				var tex_name := _texture_for(node, textures, texture_cache,
					warnings)
				if tex_name != "":
					entry["texture"] = tex_name
				meshes.append(entry)
				mesh_index[key] = idx

			instances.append({
				"mesh": idx,
				"pos": _to_ps1_pos(world.origin),
				"rot": _to_ps1_rot(world.basis),
				"spin": _read_spin(node),
			})

		var sprites := _collect_sprites(group, origin, textures, texture_cache,
			warnings)

		# A purely 2D scene has no use for a camera, so only mention it when
		# there is 3D geometry that would actually be framed by one.
		if cam == null and not instances.is_empty():
			warnings.append("%s: no Camera3D, so the PS1 camera starts at the "
				% group.name + "world origin looking down +Z.")

		if instances.is_empty() and sprites.is_empty():
			warnings.append("%s: exported no objects" % group.name)

		var g_cam_pos := [0, 0, 0]
		var g_cam_rot := [0, 0, 0]
		if cam != null:
			var cam_local := origin * cam.global_transform
			g_cam_pos = _to_ps1_pos(cam_local.origin)
			g_cam_rot = _to_ps1_rot(cam_local.basis)

		scenes.append({
			"name": group.name,
			"clear": _resolve_clear(group, root),
			"camera": {"pos": g_cam_pos, "rot": g_cam_rot},
			"instances": instances,
			"sprites": sprites,
		})

	# A purely 2D game has sprites and no meshes at all, which is valid.
	var any_sprites := false
	for sc in scenes:
		if not sc["sprites"].is_empty():
			any_sprites = true
			break

	if meshes.is_empty() and not any_sprites:
		return {"ok": false, "error": "Nothing exportable. Add a MeshInstance3D "
			+ "with a BoxMesh for 3D, or a Sprite2D for 2D -- and check the "
			+ "warnings in the Output panel."}

	var total_quads := 0
	for m in meshes:
		total_quads += m["quads"].size()
	if total_quads > WARN_TOTAL_QUADS:
		warnings.append("%d quads total. The PS1 will struggle past roughly %d."
			% [total_quads, WARN_TOTAL_QUADS])

	var scene := {
		"name": root.name,
		"textures": textures,
		"meshes": meshes,
		"scenes": scenes,
	}

	var path := ProjectSettings.globalize_path(OUT_PATH)
	var f := FileAccess.open(OUT_PATH, FileAccess.WRITE)
	if f == null:
		return {"ok": false,
			"error": "Could not write %s (error %d)" % [path, FileAccess.get_open_error()]}
	f.store_string(JSON.stringify(scene, "  "))
	f.close()

	return {
		"ok": true,
		"path": path,
		"mesh_count": meshes.size(),
		"texture_count": textures.size(),
		"scene_count": scenes.size(),
		"instance_count": _total_instances(scenes),
		"warnings": warnings,
	}


static func _total_instances(scenes: Array) -> int:
	## Sprites count as objects too -- a 2D scene reporting "0 objects" would
	## look like the export had failed.
	var n := 0
	for s in scenes:
		n += s["instances"].size()
		n += s["sprites"].size()
	return n


static func _find_scene_groups(root: Node) -> Array:
	## Direct children marked as their own NC scene, either by metadata or by
	## being named "Scene...". Metadata wins; the naming rule is there so this
	## works without opening the metadata panel.
	var groups: Array = []
	for child in root.get_children():
		if not (child is Node3D or child is Node2D):
			continue
		if child.has_meta("nc_scene") or child.name.to_lower().begins_with("scene"):
			groups.append(child)
	return groups


static func _collect(node: Node, out: Array[MeshInstance3D]) -> void:
	if node is MeshInstance3D:
		out.append(node)
	for child in node.get_children():
		_collect(child, out)


static func _find_camera(node: Node) -> Camera3D:
	if node is Camera3D:
		return node
	for child in node.get_children():
		var found := _find_camera(child)
		if found != null:
			return found
	return null


static func _find_clear_color(node: Node) -> Array:
	if node is WorldEnvironment and node.environment != null:
		var env: Environment = node.environment
		if env.background_mode == Environment.BG_COLOR:
			var c: Color = env.background_color
			return [int(c.r * 255.0), int(c.g * 255.0), int(c.b * 255.0)]
	for child in node.get_children():
		var found := _find_clear_color(child)
		if not found.is_empty():
			return found
	return []


static func _resolve_clear(group: Node, root: Node) -> Array:
	## A group can carry its own background as metadata "nc_clear" (a Color),
	## which is how each scene gets a different colour without needing its own
	## WorldEnvironment -- Godot only applies one of those anyway.
	if group.has_meta("nc_clear"):
		var m = group.get_meta("nc_clear")
		if m is Color:
			return [int(m.r * 255.0), int(m.g * 255.0), int(m.b * 255.0)]

	var c := _find_clear_color(group)
	if c.is_empty():
		c = _find_clear_color(root)
	return c if not c.is_empty() else [18, 14, 34]


static func _to_ps1_pos(v: Vector3) -> Array:
	return [int(round(v.x * SCALE)), int(round(-v.y * SCALE)),
		int(round(-v.z * SCALE))]


static func _to_ps1_rot(basis: Basis) -> Array:
	## Flipping Y and Z is a half turn about X, so a rotation about X keeps its
	## sign while rotations about Y and Z reverse. Euler order differs from the
	## PS1's RotMatrix, so compound rotations are approximate; single-axis ones
	## are exact.
	var e := basis.get_euler()
	return [
		int(round(e.x / TAU * TURN)),
		int(round(-e.y / TAU * TURN)),
		int(round(-e.z / TAU * TURN)),
	]


static func _read_spin(node: Node) -> Array:
	## Optional per-frame rotation. Add a Vector3 named "nc_spin" under the
	## node's Metadata in the inspector to make an object turn on its own.
	var s = node.get_meta("nc_spin", Vector3.ZERO)
	if not (s is Vector3):
		return [0, 0, 0]
	return [int(s.x), int(s.y), int(s.z)]


static func _build_mesh(mesh: Mesh, scale_v: Vector3, node_name: String) -> Dictionary:
	if mesh is BoxMesh:
		return _build_box(mesh.size * scale_v)
	return _build_from_surface(mesh, scale_v, node_name)


static func _build_box(size: Vector3) -> Dictionary:
	## Emitted in the exact vertex order and winding the runtime expects, so the
	## computed face normals point outward.
	var hx := int(round(size.x * 0.5 * SCALE))
	var hy := int(round(size.y * 0.5 * SCALE))
	var hz := int(round(size.z * 0.5 * SCALE))
	if hx <= 0 or hy <= 0 or hz <= 0:
		return {"error": "box has a zero or negative dimension"}

	var verts := [
		[-hx, -hy, -hz], [hx, -hy, -hz],
		[-hx, hy, -hz], [hx, hy, -hz],
		[hx, -hy, hz], [-hx, -hy, hz],
		[hx, hy, hz], [-hx, hy, hz],
	]
	var quads := [
		[0, 1, 2, 3], [4, 5, 6, 7], [5, 4, 0, 1],
		[6, 7, 3, 2], [0, 2, 5, 7], [3, 1, 6, 4],
	]
	return {"verts": verts, "quads": quads, "warnings": []}


static func _build_from_surface(mesh: Mesh, scale_v: Vector3,
		node_name: String) -> Dictionary:
	## Anything that is not a BoxMesh arrives as triangles. The runtime draws
	## quads, so each triangle becomes a quad with its last index repeated. That
	## works, but it wastes GPU time -- boxes are the cheap path for now.
	if mesh.get_surface_count() == 0:
		return {"error": "mesh has no surfaces"}

	var arrays := mesh.surface_get_arrays(0)
	var raw_verts: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
	var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]

	if raw_verts.is_empty():
		return {"error": "mesh surface has no vertices"}
	if indices.is_empty():
		indices = PackedInt32Array(range(raw_verts.size()))
	if raw_verts.size() > 65535:
		return {"error": "mesh has more than 65535 vertices"}

	var warnings: Array[String] = []
	if raw_verts.size() > WARN_VERTS_PER_MESH:
		warnings.append("%d vertices; past roughly %d the PS1 will struggle"
			% [raw_verts.size(), WARN_VERTS_PER_MESH])
	warnings.append("not a BoxMesh, so its triangles become degenerate quads")

	var verts := []
	for v in raw_verts:
		var s := Vector3(v.x * scale_v.x, v.y * scale_v.y, v.z * scale_v.z)
		verts.append([
			int(round(s.x * SCALE)),
			int(round(-s.y * SCALE)),
			int(round(-s.z * SCALE)),
		])

	var quads := []
	var i := 0
	while i + 2 < indices.size():
		quads.append([indices[i], indices[i + 1], indices[i + 2], indices[i + 2]])
		i += 3

	if quads.is_empty():
		return {"error": "mesh produced no faces"}
	if mesh.get_surface_count() > 1:
		warnings.append("only the first of %d surfaces was exported"
			% mesh.get_surface_count())

	return {"verts": verts, "quads": quads, "warnings": warnings}


# ---- textures ---------------------------------------------------------------

static func _texture_for(node: MeshInstance3D, textures: Array, cache: Dictionary,
		warnings: Array) -> String:
	## The albedo texture of the node's material, exported as a PNG. Returns the
	## name to reference from scene.json, or "" if there is none.
	var mat := node.get_active_material(0)
	if mat == null or not (mat is BaseMaterial3D):
		return ""
	var tex: Texture2D = mat.albedo_texture
	if tex == null:
		return ""
	return _export_texture(tex, textures, cache, warnings, node.name)


static func _export_texture(tex: Texture2D, textures: Array, cache: Dictionary,
		warnings: Array, owner: String) -> String:
	var key := str(tex.get_rid())
	if cache.has(key):
		return cache[key]

	if textures.size() >= MAX_TEXTURES:
		warnings.append("%s: more than %d textures; this one was skipped"
			% [owner, MAX_TEXTURES])
		return ""

	var img := tex.get_image()
	if img == null:
		warnings.append("%s: texture has no readable image" % owner)
		return ""
	if img.is_compressed():
		# Imported textures are usually compressed; the packer needs raw pixels.
		if img.decompress() != OK:
			warnings.append("%s: could not decompress texture" % owner)
			return ""

	var w := img.get_width()
	var h := img.get_height()
	if w > MAX_TEX_W or h > MAX_TEX_H:
		warnings.append("%s: texture is %dx%d, over the %dx%d limit. Resize it "
			% [owner, w, h, MAX_TEX_W, MAX_TEX_H]
			+ "-- rescaling automatically would just turn it to mush.")
		return ""
	if w % 2 == 1:
		warnings.append("%s: texture width %d is odd; two 8-bit texels share a "
			% [owner, w] + "VRAM cell, so it must be even.")
		return ""

	var name := "tex%d" % textures.size()
	DirAccess.make_dir_recursive_absolute(
		ProjectSettings.globalize_path(TEXTURE_DIR))
	var path := "%s/%s.png" % [TEXTURE_DIR, name]
	if img.save_png(path) != OK:
		warnings.append("%s: could not write %s" % [owner, path])
		return ""

	textures.append({"name": name, "file": "textures/%s.png" % name})
	cache[key] = name
	return name


# ---- 2D sprites -------------------------------------------------------------

static func _collect_sprite_nodes(node: Node, out: Array) -> void:
	if node is Sprite2D:
		out.append(node)
	for child in node.get_children():
		_collect_sprite_nodes(child, out)


static func _collect_sprites(group: Node, _origin: Transform3D, textures: Array,
		cache: Dictionary, warnings: Array) -> Array:
	## Sprite2D nodes become screen-space sprites.
	##
	## Godot's 2D origin is the top-left with +Y down, which is exactly how the
	## PS1 addresses the screen -- so positions map across 1:1 with no flip. Set
	## the project's viewport to 320x240 and what you lay out is what you get.
	var nodes: Array = []
	_collect_sprite_nodes(group, nodes)

	var sprites: Array = []
	for node in nodes:
		if not node.visible or node.texture == null:
			continue

		var tex_name := _export_texture(node.texture, textures, cache, warnings,
			node.name)
		if tex_name == "":
			continue

		var u := 0
		var v := 0
		var w: int = node.texture.get_width()
		var h: int = node.texture.get_height()
		if node.region_enabled:
			u = int(node.region_rect.position.x)
			v = int(node.region_rect.position.y)
			w = int(node.region_rect.size.x)
			h = int(node.region_rect.size.y)

		# Sprite2D draws centred on its position by default.
		var pos: Vector2 = node.global_position
		var x := int(round(pos.x))
		var y := int(round(pos.y))
		if node.centered:
			x -= w / 2
			y -= h / 2

		sprites.append({
			"texture": tex_name, "x": x, "y": y,
			"w": w, "h": h, "u": u, "v": v,
		})

	return sprites
