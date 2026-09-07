# VN essentials: Godot authoring, native PS2 playback

Open examples/ps2_vn/godot/project.godot in Godot (or select ps2_vn in Studio
and choose GODOT / DESIGN > EDIT VN IN GODOT). Open vn_authoring.tscn and
select VN_Essentials. Expand its resource arrays in the Inspector.

- Characters: id, display name, portrait PNG.
- Scenes: unique id, background PNG, fallback color.
- Items: unique id and display name.
- Dialogue: unique id, speaker id (blank for narration), scene id, text,
  next dialogue id (blank ends the conversation), give item id, and choices.
- Choices: label, destination dialogue id, optional required item and reward item.
- Start: first dialogue id. Frames Per Character: 1–10; lower is faster.

Expand an array and use New NCVNCharacter / NCVNLocation / NCVNItem / NCVNLine
or NCVNChoice for new entries. Give each entry a unique id. When duplicating a
resource, use Make Unique before editing if you want an independent copy.
Copy PNG files into godot/assets, then choose them in portrait/background fields.
The supplied geometric artwork is original developer placeholder art; replace it
with your Aseprite exports. Portraits preserve source proportions within 280x224;
backgrounds fill the screen. 320x224 backgrounds are a useful starting size.

Save the scene. Use the NC dock EXPORT, CHECK, BUILD buttons; these export
resources to ../vn.json and compile the native PS2 game. The toolbar Export to NC
and Tools > Neon Coffee: export VN essentials also recognize this authoring scene.
The scene is an authoring document, not a playable Godot preview. Existing PS1
Godot editing and NCScript remain intact; this kit uses structured data/actions,
not full GDScript or a new NCScript-to-PS2 execution bridge.

The sample gives you the CAFE KEY. One choice requires it and changes the scene
from cafe to street; another stays in the cafe. Change those resources without C.

Hardware controls:
START -> menu; X -> Begin. Text reveals progressively. X finishes revealing a
page, then advances or chooses. D-pad selects a choice. An exclamation mark means
its required item is missing. SQUARE toggles inventory; TRIANGLE closes it or
returns to the menu. BEGIN resets the playthrough. Inventory is session-only:
no memory-card save/load in this kit yet. Named scene changes are immediate cuts.

Limits checked at build/check:
16 characters, 32 scenes, 16 item types, 128 dialogue entries, 2 choices per entry.
Dialogue wraps to 32 characters, at most four lines per entry; split longer text.
Printable ASCII font only. Maximum 16 unique PNGs, each at most 512x512, with
2 MiB total after power-of-two RGBA padding. All kit textures stay resident.
This reserves room for framebuffer/font/logo; it is not a total RAM profiler.
Hard transparency: source alpha <128 becomes transparent; other pixels opaque.
Invalid scene/speaker/item/dialogue references stop the build with their names.

Validation performed: Godot headless import and resource export roundtrip,
eight compiler tests, existing and freshly created PS2 VN builds. The new
conversation/portrait/inventory runtime still needs console testing.
