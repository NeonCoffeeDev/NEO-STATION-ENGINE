"""Hardware profiles. Single source of truth for every budget NC enforces.

These numbers are what the editor warns against and what `ncc` refuses to exceed.
They are deliberately conservative: they describe what NC will let you use, not the
absolute hardware maximum.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Target:
    key: str
    name: str
    width: int
    height: int
    ram_bytes: int
    vram_bytes: int
    max_texture: int          # per-side, pixels
    color_depths: tuple       # bits per pixel the GPU samples natively
    has_fpu: bool
    executable: str           # extension of the linked output
    # Tools that must be on PATH for this target to build.
    tools: tuple = field(default_factory=tuple)


PS1 = Target(
    key="ps1",
    name="PlayStation 1",
    width=320, height=240,
    ram_bytes=2 * 1024 * 1024,
    vram_bytes=1024 * 1024,
    max_texture=256,
    color_depths=(4, 8, 16),
    has_fpu=False,
    executable=".psexe",
    tools=("cmake", "ninja", "mipsel-none-elf-gcc", "mkpsxiso"),
)

PS2 = Target(
    key="ps2",
    name="PlayStation 2",
    width=640, height=448,
    ram_bytes=32 * 1024 * 1024,
    vram_bytes=4 * 1024 * 1024,
    max_texture=512,
    color_depths=(4, 8, 16, 32),
    has_fpu=True,
    executable=".elf",
    tools=("make", "ee-gcc"),
)

TARGETS = {t.key: t for t in (PS1, PS2)}
