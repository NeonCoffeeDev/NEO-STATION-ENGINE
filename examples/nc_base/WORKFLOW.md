# NC Base authoring walkthrough

1. Open **GAMEFLOW**, then open Level Select, 3D Lab, Visual Novel Lab, or the
   UI / Inventory Lab. Each state lists the Scenes and Events it owns.
2. Open **3D Lab > 3D WORLD / Main World**. SCENE is the free-camera workspace;
   GAME is the authored Main Camera output.
3. In the left **HIERARCHY**, select **Main Camera** or **Main Camera Target**.
   Choose X, Y, or Z and drag with MOVE. The inset in SCENE and the GAME tab
   update from those values. Use the right Inspector for exact position,
   target, and FOV values, then press SAVE.
4. Select Ground or Demo Cube to move, rotate, scale, or replace its material.
   Material images are project-local PNGs and compile into native GS textures.
5. On hardware, the MATERIAL tile in the upper-right samples the same upload as
   the cubes. A correct tile with a bad cube points to UV/face projection; a bad
   tile and bad cube point to texture conversion/upload.
6. The Base menu is generated from the active Button2D GameObjects in
   `screens.json`. Its 3D HUD, VN HUD, and 4x3 inventory are editable screens.
7. EVENTS and `scripts/*.nc` share the same native actions. The included
   NC-Code examples open inventory, load either gameplay level, and play sound.

The deeper anchor, responsive-container, and theme system for Canvas2D is a
later milestone. Current Canvas, Container, Texture Rect, Button, Label,
Progress Bar, and Grid Inventory objects establish the project format.
