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
## Positions are exported RELATIVE TO THE CAMERA, so what you frame in the Godot
## viewport is roughly what appears on the console. Without a camera the scene is
## exported in world space, which usually means everything sits behind you.

const SCALE := 100.0          ## PS1 units per Godot metre
const OUT_PATH := "res://../scene.json"

## The PS1 has no depth buffer and a small polygon budget. These are the points
## where a scene stops being plausible on the hardware, not hard limits.
const WARN_VERTS_PER_MESH := 256
const WARN_TOTAL_QUADS := 900

## Rotation on the PS1 is a 16-bit angle where 4096 is one full turn.
const TURN := 4096.0


static func export_scene(root: Node) -> Dictionary:
	var warnings: Array[String] = []
	var meshes: Array = []
	var mesh_index := {}          ## cache key -> index into `meshes`
	var instances: Array = []

	var cam := _find_camera(root)
	if cam == null:
		warnings.append("No Camera3D in the scene. Exported in world space, so "
			+ "objects may be behind the PS1 camera. Add a Camera3D and frame "
			+ "the scene through it.")
	var to_view := Transform3D.IDENTITY
	if cam != null:
		to_view = cam.global_transform.affine_inverse()

	var nodes: Array[MeshInstance3D] = []
	_collect(root, nodes)
	if nodes.is_empty():
		return {"ok": false, "error": "No MeshInstance3D nodes found. Add a "
			+ "MeshInstance3D with a BoxMesh and try again."}

	for node in nodes:
		if not node.visible:
			continue
		if node.mesh == null:
			continue

		var local := to_view * node.global_transform
		var scale_v := node.global_transform.basis.get_scale()

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
			meshes.append({
				"name": "m%d" % idx,
				"verts": built["verts"],
				"quads": built["quads"],
			})
			mesh_index[key] = idx

		instances.append({
			"mesh": idx,
			"pos": _to_ps1_pos(local.origin),
			"rot": _to_ps1_rot(local.basis),
			"spin": _read_spin(node),
		})

	if meshes.is_empty():
		return {"ok": false, "error": "Nothing exportable. Every mesh failed to "
			+ "convert -- see the warnings in the Output panel."}

	var total_quads := 0
	for m in meshes:
		total_quads += m["quads"].size()
	if total_quads > WARN_TOTAL_QUADS:
		warnings.append("%d quads total. The PS1 will struggle past roughly %d."
			% [total_quads, WARN_TOTAL_QUADS])

	var scene := {
		"name": root.name,
		"clear": _find_clear_color(root),
		"meshes": meshes,
		"instances": instances,
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
		"instance_count": instances.size(),
		"warnings": warnings,
	}


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
	return [] if node.get_parent() != null else [18, 14, 34]


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
