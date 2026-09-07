# Limits, rules and guidelines

Everything here comes from the hardware. The PlayStation was built in 1994 around
budgets that are small by modern standards but not arbitrary, and most of the
"rules" below are just those budgets restated.

Run this at any time and it will tell you where you stand:

```bash
./ncc check mygame
```

or press **F8** in NC Studio. A failed build runs it for you automatically, so
you get told what was too big rather than reading a linker error.

## The machine

| | |
|---|---|
| CPU | 33 MHz MIPS R3000, **no floating point unit** |
| Main RAM | **2 MB** — your executable, your data, everything |
| VRAM | **1 MB**, and the two framebuffers already use a third |
| Sound RAM | **512 KB**, separate from main RAM |
| Display | 320x240 |
| GPU | No depth buffer. No transparency except one reserved colour. |

## Textures

| Rule | Why |
|---|---|
| **8 textures maximum** | Each needs its own page in VRAM. |
| **256 x 240 maximum** | Larger will not fit a texture page. |
| **Width must be even** | Two 8-bit texels share one 16-bit VRAM cell. |
| **256 colours** | 8-bit palette. `ncc` quantises for you. |
| Transparency is **one colour**, not alpha | The GPU skips texels whose value is exactly `0x0000`. Give a PNG an alpha channel and entry 0 is reserved automatically, leaving 255 for the image. |

**Guidance.** 128x128 is a comfortable size. Put many small images on one sheet
and select them with `uvs` (3D) or `u`/`v` (sprites) — one sheet costs one slot,
eight separate images cost all eight.

Oversized textures are **refused, not rescaled**. Silently resampling your art
into mush would be worse than telling you.

## Text

Text is drawn from a font sheet the package carries, not from a system font.

| Rule | Why |
|---|---|
| **Uppercase only**, ASCII 32–95 | An 8x8 cell has room for one case. Lowercase is folded up for you. |
| **8x8 cells**, 8 pixels per character | 40 characters across a 320-wide screen. |
| Sheet is **256x16**, 32 cells x 2 rows | It fits the VRAM strip above the texture slots, which is what makes it free. |
| Costs **no texture slot** | See the VRAM map in `tools/ncc/ncc/textures.py`. |
| One quad per character | A long HUD string every frame is real fill rate. |

To use your own, put a 256x16 PNG in the project and name it in `scene.json`:

```json
"font": { "file": "textures/myfont.png", "cell": [8, 8], "first": 32 }
```

The built-in font is drawn in `tools/ncc/ncc/fontgen.py` as editable pixel
art — change a glyph there rather than tracing it back out of a PNG.

## Sound

| Rule | Why |
|---|---|
| **16 sounds maximum** | Fixed sample table in the runtime. |
| **512 KB total** | The SPU has its own RAM, separate from the 2 MB. |
| **44100 Hz maximum** | Hardware ceiling. |
| **Mono, 16- or 8-bit PCM WAV** | mp3 and ogg are not decoded. Stereo is mixed down. |
| **24 voices** | 24 sounds can overlap; the 25th steals the oldest. |

**Guidance.** 22050 Hz is the sweet spot for effects and costs half of 44100.
11025 is fine for thuds and clicks. Keep effects under a second — the SPU is for
sound effects, and long music will exhaust it. `ncc check` warns past 4 seconds.

WAV is compressed to SPU-ADPCM at about 3.5:1 during the build, so the file on
disk is not what it costs.

## Music

Music is a **CD audio track**, not an SPU sample. Songs do not fit in 512 KB, so
they go on the disc as Red Book audio and the drive streams them into the mixer:
no main RAM, no SPU RAM, no CPU.

| Rule | Why |
|---|---|
| **44100 Hz, 16-bit stereo WAV** | Red Book is a fixed format. |
| **Track 1 is the game** | Music starts at track 2. |
| Costs disc space, not memory | A 14-second loop adds about 2.5 MB to the image. |
| The drive is busy while it plays | Nothing here streams data during play, but a game that did would have to share. |

List them under `"music"` in `scene.json`; `ncc build` rewrites the marked region
of `iso.xml` so the disc layout stays in step.

## Saving

| Rule | Why |
|---|---|
| **16 int slots**, nothing else | No allocator, and no serialisation format worth writing for 2 MB. |
| One **8 KB block** | The smallest unit a PlayStation save can occupy. |
| Card 1 only | `bu00:`. Card 2 (`bu10:`) is not wired up. |
| Writing **blocks** for several frames | The driver talks to the card over the controller port, a little each vertical blank. |

**Guidance.** Save at a pause the player already expects — game over, a
checkpoint, a menu — never every frame. `save_read()` returning `0` is the
ordinary first-run answer, not a failure; leave the defaults and let them in.

The file carries a proper BIOS header, so it shows up in the console's own
memory card screen with your project's name and an icon rather than as
"corrupted data".

## Geometry (3D)

| Rule | Why |
|---|---|
| **64 meshes**, **16 scenes** | Fixed tables in the runtime. |
| **128 objects per scene** | Copied into a fixed array on load. |
| **65535 vertices per mesh** | Format limit — you will hit performance first. |
| Faces are **quads** | Native to the hardware and cheaper than two triangles. Triangles are exported as a quad with a repeated corner. |

**Guidance.** PS1 characters were typically 150–300 vertices, whole scenes under
about 900 quads a frame. `ncc check` warns at both. There is **no depth buffer**:
faces are sorted by average depth, so large intersecting surfaces will visibly
flicker or sort wrongly. Break big flat things into smaller pieces.

## Sprites (2D)

| Rule | Why |
|---|---|
| **64 sprites per scene** | Fixed array. |
| Screen space, 320x240 | No camera applies. |
| Drawn **over** 3D, **under** text | Fixed ordering-table depth. |

**Guidance.** Everything that will ever appear must exist in `scene.json` from
the start — there is no way to create a sprite at run time. Allocate a pool
(say 8 bullets), hide them, and show them as needed. The `shooter` template does
exactly this.

## Script

| Rule | Why |
|---|---|
| **No `float`** | No FPU. Use ints; for fractions use fixed point where `4096` = `1.0`. |
| **Arrays are fixed size**, top-level only | No allocator. `var bullets: array[16]` |
| **No classes, dictionaries, or strings** beyond literals | No object model, no allocator. |
| One script per project | Branch on `scene()` and object index. |

Out-of-range array indices read as `0` and write nowhere, rather than crashing.
There is no MMU here: a stray write would not fault, it would quietly corrupt
memory and lock up somewhere unrelated minutes later.

## Performance

The frame budget at 30 fps is about 33 ms. What costs:

- **Transforms.** Every vertex goes through the GTE one at a time.
- **Fill rate.** Large textured polygons cost more than small ones. Full-screen
  overdraw is expensive.
- **Ordering table depth.** 1024 buckets; primitives outside the range are dropped.
- **`draw_text`.** One sprite per character. A long HUD string every frame adds up.

Cheap: moving sprites, playing sounds, arithmetic in script.

## When something does not build

`ncc check` names the item, the reason, and the fix. The common ones:

| Message | What it means |
|---|---|
| `texture is 512x512; the limit is 256x240` | Resize, or split into several textures. |
| `width must be even` | Two texels share a VRAM cell. Pad by a pixel. |
| `more than 8 textures` | Combine images into a sheet. |
| `audio needs N KB but the SPU has 507 KB` | Shorten sounds or lower the sample rate. |
| `not a readable WAV` | Export uncompressed PCM. mp3/ogg are not decoded. |
| `93 sprites, over the 64 limit` | Split the scene, or raise `NC_MAX_SPRITES`. |
| `version N, expected M` on the console | The package is stale. Rebuild. |
| A **red screen** on the console | The package failed to load; the reason is on TTY — check the **PS1 TTY** pane. |

## Raising a limit

The runtime caps live in `include/nc.h` in your project (`NC_MAX_SPRITES`,
`NC_MAX_OBJECTS`, `NC_MAX_SOUNDS`, …). They are yours to raise — they are fixed
arrays, so the cost is RAM, and you have 2 MB. The mirrored values in
`tools/ncc/ncc/check.py` need the same change or the checker will disagree with
the runtime.

The **texture and audio limits are not adjustable** that way: those are VRAM and
SPU RAM, and the hardware has what it has.
