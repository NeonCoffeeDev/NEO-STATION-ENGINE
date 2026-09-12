"""What actually fits in the PlayStation 2's 4 MB of graphics memory.

Every other budget in this toolchain is local: the VN kit knows about VN
textures, the material compiler knows about material textures, and neither
knows the frame buffers exist. That is how a project passes three separate
checks and still runs out of graphics memory on the console, where the only
symptom is a texture that uploads as garbage or a buffer that lands on top of
another one.

This is the single ledger. Everything that occupies graphics memory reports
into it, and the report is ordered by what it costs, because the question
after "does it fit" is always "what do I cut".

The arithmetic is the GS's own. Graphics memory is 512 pages of 8 KB, and a
page holds a different number of pixels depending on the format, so a buffer
does not cost width * height * bytes-per-pixel -- it costs however many whole
pages its rectangle lands on.

Textures pay twice, because the GS can only address power-of-two sizes: a
260x260 image is stored as 512x512 and costs exactly what a 512x512 image
costs. That is invisible from a file listing and is the most common way to
waste a megabyte here, so every texture is reported with the share of it that
is padding rather than picture.
"""

import json
import os
import re

VRAM_BYTES = 4 * 1024 * 1024
PAGE_BYTES = 8192
PAGE_COUNT = VRAM_BYTES // PAGE_BYTES

# Pixels per 8 KB page, by format. Fewer bits per pixel means more pixels fit
# in the same page, which is why a 16-bit buffer is exactly half the cost of a
# 32-bit one at the same size rather than some awkward fraction of it.
PAGE_SHAPE = {
    "PSMCT32": (64, 32), "PSMCT24": (64, 32),
    "PSMCT16": (64, 64), "PSMCT16S": (64, 64),
    "PSMT8": (128, 64), "PSMT4": (128, 128),
    "PSMZ32": (64, 32), "PSMZ24": (64, 32),
    "PSMZ16": (64, 64), "PSMZ16S": (64, 64),
}


def pow2(value):
    return 1 << max(0, int(value) - 1).bit_length()


def pages(width, height, psm="PSMCT32"):
    """Whole 8 KB pages a width x height rectangle occupies in this format."""
    page_w, page_h = PAGE_SHAPE[psm]
    wide = -(-max(1, width) // page_w)
    tall = -(-max(1, height) // page_h)
    return wide * tall


def cost(width, height, psm="PSMCT32"):
    return pages(width, height, psm) * PAGE_BYTES


class Entry:
    def __init__(self, kind, name, width, height, psm, used=None, source=None):
        self.kind = kind            # BUFFER or TEXTURE
        self.name = name
        self.width = width          # what is allocated, after padding
        self.height = height
        self.psm = psm
        self.used = used or (width, height)     # the picture inside it
        self.source = source
        self.bytes = cost(width, height, psm)

    @property
    def waste(self):
        """Share of this entry paid for padding rather than picture, 0..100."""
        held = self.width * self.height
        if not held:
            return 0
        return max(0, 100 - (self.used[0] * self.used[1] * 100) // held)


class Ledger:
    def __init__(self):
        self.entries = []
        self.notes = []

    def add(self, kind, name, width, height, psm="PSMCT32", used=None, source=None):
        self.entries.append(Entry(kind, name, width, height, psm, used, source))
        return self.entries[-1]

    def note(self, text):
        self.notes.append(text)

    @property
    def total(self):
        return sum(e.bytes for e in self.entries)

    @property
    def free(self):
        return VRAM_BYTES - self.total

    def ranked(self):
        return sorted(self.entries, key=lambda e: (-e.bytes, e.name))

    # ---- the part that is actually a tool ---------------------------------

    def _shrink(self, entry):
        """The largest picture that still lands in a cheaper padded box.

        Cheapest is not the useful answer -- the point is to lose as little of
        the artwork as possible while getting under budget.
        """
        best = None
        used_w, used_h = entry.used
        boxes = ((entry.width // 2, entry.height),
                 (entry.width, entry.height // 2),
                 (entry.width // 2, entry.height // 2))
        for box_w, box_h in boxes:
            if box_w < 1 or box_h < 1:
                continue
            scale = min(box_w / float(used_w), box_h / float(used_h))
            new_w = max(1, int(used_w * scale))
            new_h = max(1, int(used_h * scale))
            if cost(pow2(new_w), pow2(new_h), entry.psm) >= entry.bytes:
                continue
            if best is None or new_w * new_h > best[0] * best[1]:
                best = (new_w, new_h)
        return best

    def savings(self):
        """Per asset, what each change would actually cost instead.

        Options for one asset are alternatives that also stack, so they are
        reported together with the combined figure rather than as a list of
        numbers that look addable across the whole project and are not.
        """
        out = []
        for entry in self.ranked():
            if entry.kind == "BUFFER":
                continue
            options = []
            half = "PSMCT16" if entry.psm == "PSMCT32" else None
            if half and cost(entry.width, entry.height, half) < entry.bytes:
                options.append(("16-bit instead of 32-bit, 5 bits a channel",
                                cost(entry.width, entry.height, half)))
            smaller = self._shrink(entry) if entry.waste >= 25 else None
            if smaller:
                options.append(("resize to %dx%d (%dx%d of picture is sitting in "
                                "a %dx%d texture, %d%% padding)"
                                % (smaller[0], smaller[1], entry.used[0],
                                   entry.used[1], entry.width, entry.height,
                                   entry.waste),
                                cost(pow2(smaller[0]), pow2(smaller[1]), entry.psm)))
            if half and smaller:
                options.append(("both together",
                                cost(pow2(smaller[0]), pow2(smaller[1]), half)))
            if options:
                out.append((entry.bytes - min(price for _, price in options),
                            entry, options))
        out.sort(key=lambda row: -row[0])
        return out

    def affordable(self):
        """What the headroom is good for, in this project's own terms."""
        wanted = (("a 16-bit depth buffer at 640x448 (objects occluding each other)",
                   (640, 448, "PSMZ16")),
                  ("another 640x448 16-bit frame buffer", (640, 448, "PSMCT16")),
                  ("a 256x256 32-bit texture", (256, 256, "PSMCT32")))
        return [(label, cost(*shape), cost(*shape) <= self.free)
                for label, shape in wanted]

    def render(self):
        rows = ["", "  GRAPHICS MEMORY   %d KB of %d KB  %s"
                % (self.total // 1024, VRAM_BYTES // 1024,
                   _bar(self.total, VRAM_BYTES)), ""]
        for entry in self.ranked():
            padding = ("" if entry.waste < 10
                       else "  (%dx%d used, %d%% padding)"
                       % (entry.used[0], entry.used[1], entry.waste))
            rows.append("    %-7s %-26s %4dx%-4d %-8s %5d KB%s"
                        % (entry.kind, entry.name[:26], entry.width, entry.height,
                           entry.psm, entry.bytes // 1024, padding))
        rows.append("")
        if self.total > VRAM_BYTES:
            rows.append("    OVER BUDGET by %d KB -- buffers will land on top of "
                        "each other" % ((self.total - VRAM_BYTES) // 1024))
        else:
            rows.append("    %d KB free (%d of %d pages)"
                        % (self.free // 1024, self.free // PAGE_BYTES, PAGE_COUNT))
            for label, price, fits in self.affordable():
                rows.append("      %s %s (%d KB)"
                            % ("[ok]" if fits else "[no]", label, price // 1024))
        savings = self.savings()
        if savings:
            rows.append("")
            rows.append("    WAYS TO GET MEMORY BACK")
            rows.append("    (options under one asset are alternatives, not a sum)")
            for best, entry, options in savings[:5]:
                rows.append("      %-26s %5d KB now, up to %d KB back"
                            % (entry.name[:26], entry.bytes // 1024, best // 1024))
                for advice, price in options:
                    rows.append("          %5d KB  %s" % (price // 1024, advice))
        for text in self.notes:
            rows.append("")
            rows.append("    note: %s" % text)
        return "\n".join(rows)


def _bar(used, total, width=22):
    filled = min(width, int(round(width * used / float(total))))
    return "[%s%s] %d%%" % ("#" * filled, "." * (width - filled),
                            int(round(100.0 * used / total)))


# ---- gathering a project's real contents --------------------------------

def _image_size(path):
    from PIL import Image
    with Image.open(path) as img:
        return img.size


def _declared_ints(source, names):
    """Pull `const int nc_font_width = 256;` out of a generated C file.

    Reading what the build produced, rather than guessing from the template,
    means the ledger cannot disagree with the executable.
    """
    found = {}
    try:
        with open(source, encoding="utf-8") as handle:
            text = handle.read(4096)
    except OSError:
        return found
    for name in names:
        match = re.search(r"\b%s\s*=\s*(\d+)" % re.escape(name), text)
        if match:
            found[name] = int(match.group(1))
    return found


# How the runtime spells these in C, and what this module calls them.
_PSM_NAMES = {"GS_PSM_32": "PSMCT32", "GS_PSM_24": "PSMCT24",
              "GS_PSM_16": "PSMCT16", "GS_PSM_16S": "PSMCT16S"}


def frame_setup(project):
    """How many frame buffers this project has, and in what format.

    Read out of its own main.c rather than assumed, because projects own their
    copy of the runtime -- one that has not been brought forward is still
    single-buffered at 32-bit, and reporting the newer arrangement for it would
    be a ledger that quietly lies about the older half of the examples.
    """
    try:
        with open(os.path.join(project, "src", "main.c"), encoding="utf-8") as handle:
            text = handle.read()
    except OSError:
        return "PSMCT32", 1
    match = re.search(r"#define\s+FRAME_PSM\s+(GS_PSM_\w+)", text)
    psm = _PSM_NAMES.get(match.group(1), "PSMCT32") if match else "PSMCT32"
    count = 2 if re.search(r"framebuffer_t\s+frame\s*\[\s*2\s*\]", text) else 1
    if not match and count == 1:
        psm = "PSMCT32"
    width = re.search(r"#define\s+SCREEN_W\s+(\d+)", text)
    height = re.search(r"#define\s+SCREEN_H\s+(\d+)", text)
    return psm, count, (int(width.group(1)) if width else 640,
                        int(height.group(1)) if height else 448)


def collect(project, frame_psm=None, frame_count=None, screen=None, z_psm=None):
    """Everything this project will put in graphics memory."""
    ledger = Ledger()
    root = os.path.abspath(project)
    src = os.path.join(root, "src")

    detected_psm, detected_count, detected_screen = frame_setup(root)
    frame_psm = frame_psm or detected_psm
    frame_count = frame_count or detected_count
    screen = screen or detected_screen
    if frame_count == 1:
        ledger.note("single frame buffer: the picture is redrawn in the buffer "
                    "the television is scanning out, which shows as a flickering "
                    "band across the top of heavy scenes")

    for index in range(frame_count):
        ledger.add("BUFFER", "frame buffer %d" % index, screen[0], screen[1], frame_psm)
    if z_psm:
        ledger.add("BUFFER", "depth buffer", screen[0], screen[1], z_psm)

    # Engine textures, measured from what the build generated rather than
    # assumed, so a project that changed its font or skin reports the truth.
    engine = (("font_data.c", "nc_font", "font sheet"),
              ("logo_data.c", "nc_logo", "brand logo"),
              ("ui_skin_data.c", "nc_ui_skin", "UI skin"))
    for filename, prefix, label in engine:
        sizes = _declared_ints(os.path.join(src, filename),
                               [prefix + "_width", prefix + "_height"])
        if len(sizes) == 2:
            width = sizes[prefix + "_width"]
            height = sizes[prefix + "_height"]
            # The runtime rounds a texture's height up to a multiple of 32 when
            # it allocates, so a 16-pixel-tall font still occupies 32.
            ledger.add("TEXTURE", label, width, (height + 31) & ~31, "PSMCT32",
                       used=(width, height))
        else:
            ledger.note("%s not measured -- build the project first" % label)

    # VN artwork. Sizes come from the images, padding from the same
    # power-of-two rule vnkit applies when it emits them.
    vn_path = os.path.join(root, "vn.json")
    if os.path.isfile(vn_path):
        try:
            with open(vn_path, encoding="utf-8") as handle:
                kit = json.load(handle).get("kit", {})
        except (OSError, ValueError):
            kit = {}
        art = [(c.get("name") or c.get("id", "?"), c.get("portrait"))
               for c in kit.get("characters", [])]
        art += [(s.get("id", "scene"), s.get("background"))
                for s in kit.get("scenes", [])]
        seen = set()
        for name, relative in art:
            if not relative or relative in seen:
                continue
            seen.add(relative)
            full = os.path.join(root, relative)
            if not os.path.isfile(full):
                continue
            width, height = _image_size(full)
            ledger.add("TEXTURE", "VN %s" % name, max(64, pow2(width)),
                       max(32, pow2(height)), "PSMCT32", used=(width, height),
                       source=relative)

    # 3D material textures, from the same assignments the material compiler reads.
    materials = []
    for filename, key in (("world3d.json", "objects"),
                          ("room-layout.json", "materials")):
        full = os.path.join(root, filename)
        if not os.path.isfile(full):
            continue
        try:
            with open(full, encoding="utf-8") as handle:
                doc = json.load(handle)
        except (OSError, ValueError):
            continue
        for entry in doc.get(key, {}).values():
            texture = entry.get("material") or entry.get("texture")
            if texture and texture not in materials:
                materials.append(texture)
    for relative in materials:
        full = os.path.join(root, relative)
        if not os.path.isfile(full):
            continue
        width, height = _image_size(full)
        ledger.add("TEXTURE", "material %s" % os.path.basename(relative),
                   pow2(width), pow2(height), "PSMCT32", used=(width, height),
                   source=relative)
    return ledger


# ---- main memory ---------------------------------------------------------

EE_RAM_BYTES = 32 * 1024 * 1024


def main_memory(project):
    """What the executable is made of, against the console's 32 MB.

    Nothing streams yet: every texture and every second of audio is linked
    into the executable, so the executable *is* the game's memory footprint
    plus whatever it allocates at runtime. Naming the big embedded blobs is
    the difference between "10 MB, seems fine" and "half of that is two music
    tracks that could be read from the disc instead".
    """
    root = os.path.abspath(project)
    elf = os.path.join(root, "game.elf")
    rows = ["", "  MAIN MEMORY"]
    if not os.path.isfile(elf):
        rows.append("    executable not built yet")
        return "\n".join(rows)
    size = os.path.getsize(elf)
    rows.append("    EXECUTABLE %d KB of %d KB  %s"
                % (size // 1024, EE_RAM_BYTES // 1024, _bar(size, EE_RAM_BYTES)))
    audio_dir = os.path.join(root, "src", "audio")
    if os.path.isdir(audio_dir):
        blobs = []
        for name in sorted(os.listdir(audio_dir)):
            if name.endswith(".bin"):
                blobs.append((name, os.path.getsize(os.path.join(audio_dir, name))))
        embedded = sum(n for _, n in blobs)
        if embedded:
            rows.append("      of which embedded audio  %d KB (%d%% of the "
                        "executable)" % (embedded // 1024, embedded * 100 // size))
            for name, blob in sorted(blobs, key=lambda row: -row[1])[:4]:
                rows.append("        %-20s %6d KB" % (name, blob // 1024))
    rows.append("    Runtime allocations (draw packets, stack, audio voices) are")
    rows.append("    on top of this and are not measured here.")
    return "\n".join(rows)
