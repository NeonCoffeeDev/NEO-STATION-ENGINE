# PS2 VN authoring in Studio

Restart Studio, select ps2_vn, then open DESIGN.
Edit title/subtitle, story, about text and logo width percentage.
F7 saves and validates the selected VN design, then builds its ELF.
The fields are backed by vn.json; ncc generates src/vn_content.h before Make.
Do not edit the generated header. Story/about accept 1–200 lines, each at most
32 printable ASCII characters. The current font draws 16-pixel-wide glyphs.
The dialogue panel displays the latest 11 revealed lines instead of overflowing.
Menu routes remain fixed: Title -> Menu -> Story/About. This is a form editor,
not a freeform scene graph or a PS2 GDScript runtime.

Unsaved drafts survive project switching within this Studio session. Save before
closing Studio. Embedded asset filenames are displayed below the design fields;
the current PNG import pipeline still uses tools/png2ps2.py.
Logo width defaults to 110 percent as approximate 4:3 display compensation.
Use the original, unsquashed PNG to repair source-art distortion; width adjustment
cannot recover detail lost in a previously stretched texture.

Hardware results reported by user on 2026-09-07: pad sized/moved correctly,
pulse cycled with centred square, texture diagnostic rendered, VN title/menu worked.
The subsequent design/text changes compile successfully but await hardware testing.
