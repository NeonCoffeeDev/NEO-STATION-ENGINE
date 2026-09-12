"""ncc -- the Neon Coffee orchestrator."""

import argparse
import os
import subprocess
import sys

from . import __version__, assets, build as build_mod, check as check_mod, doctor
from .targets import TARGETS


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="ncc",
        description="Neon Coffee build orchestrator for PS1/PS2 homebrew.",
    )
    p.add_argument("--version", action="version", version=f"ncc {__version__}")
    sub = p.add_subparsers(dest="cmd")

    d = sub.add_parser("doctor", help="check the toolchain environment")
    d.add_argument("--target", choices=["ps1", "ps2", "all"], default="all")
    d.set_defaults(func=doctor.run)

    n = sub.add_parser("new", help="create a new project from a template")
    n.add_argument("name")
    n.add_argument("path", nargs="?", help="where to create it (default: ./<name>)")
    n.add_argument("-t", "--template", default=build_mod.DEFAULT_TEMPLATE,
                   help="which template to use (see: ncc templates)")
    n.set_defaults(func=build_mod.new)

    sy = sub.add_parser("sync", help="update a project's engine files to this ncc")
    sy.add_argument("path", nargs="?", default=".")
    sy.set_defaults(func=build_mod.sync)

    tl = sub.add_parser("templates", help="list available project templates")
    tl.set_defaults(func=build_mod.templates)

    b = sub.add_parser("build", help="build a project to .bin/.cue")
    b.add_argument("path", nargs="?", default=".")
    b.add_argument("-r", "--release", action="store_true",
                   help="optimise (-O2) instead of the default debug build (-Og)")
    b.set_defaults(func=build_mod.build)

    r = sub.add_parser("run", help="build, then launch it in DuckStation")
    r.add_argument("path", nargs="?", default=".")
    r.add_argument("-r", "--release", action="store_true",
                   help="optimise (-O2) instead of the default debug build (-Og)")
    r.set_defaults(func=build_mod.run)

    c = sub.add_parser("clean", help="delete a project's build directory")
    c.add_argument("path", nargs="?", default=".")
    c.set_defaults(func=build_mod.clean)

    ck = sub.add_parser("check", help="report what fits and what does not")
    ck.add_argument("path", nargs="?", default=".")
    ck.set_defaults(func=check_mod.run)

    ad = sub.add_parser("add", help="add a texture, sound or music file to a project")
    ad.add_argument("kind", choices=["texture", "sound", "music"])
    ad.add_argument("file", help="the file to add; it is copied into the project")
    ad.add_argument("path", nargs="?", default=".", help="the project")
    ad.add_argument("-n", "--name", help="what scripts and scene.json call it")
    ad.set_defaults(func=assets.run)

    fo = sub.add_parser("font", help="write the built-in font sheet to a PNG")
    fo.add_argument("out", nargs="?", default="font.png")
    fo.set_defaults(func=_font)

    pv = sub.add_parser("preview",
                        help="render what the console will draw, to a PNG")
    pv.add_argument("path", nargs="?", default=".", help="the project")
    pv.add_argument("-o", "--out", help="where to write the PNG")
    pv.add_argument("--material", help="draw every object with this texture "
                    "instead, to judge lighting on a neutral surface")
    pv.set_defaults(func=_preview)

    ms = sub.add_parser("mesh",
                        help="inspect a model and draw it the way the console would")
    ms.add_argument("file", help="a .obj or binary .fbx (Blender, Crocotile, Maya)")
    ms.add_argument("-o", "--out", help="where to write the preview PNG")
    ms.add_argument("--rotate", type=float, default=210.0,
                    help="turn the model on its Y axis before drawing")
    ms.add_argument("--height", type=float, default=1.8,
                    help="world height to scale it to; a cube here is 2 units")
    ms.add_argument("--turnaround", action="store_true",
                    help="draw it from four sides instead of one")
    ms.set_defaults(func=_mesh)

    st = sub.add_parser("studio", help="open the NC Studio GUI")
    st.set_defaults(func=_studio)

    t = sub.add_parser("targets", help="list hardware profiles")
    t.set_defaults(func=_targets)

    args = p.parse_args(argv)
    if not getattr(args, "func", None):
        p.print_help()
        return 0
    return args.func(args)


def _font(args):
    """Dump the default font sheet, as a starting point for your own.

    Edit the pixels, keep the 256x16 shape and the 32x2 cell grid, then point
    scene.json at it with "font": {"file": "textures/myfont.png"}.
    """
    from . import fontgen
    w, h = fontgen.write_png(args.out)
    print(f"Wrote {args.out}  ({w}x{h}, {fontgen.COLUMNS} cells per row, "
          f"ASCII {fontgen.FIRST_CHAR}..{fontgen.LAST_CHAR})")
    print("  Keep the size and grid; the runtime indexes glyphs by cell.")
    return 0


def _studio(args):
    from . import toolchain as tc
    script = os.path.join(tc.project_root(), "tools", "ncstudio", "studio.py")
    if not os.path.isfile(script):
        raise SystemExit(f"ncc: NC Studio not found at {script}")
    return subprocess.call([sys.executable, script])


def _preview(args):
    """Draw the frame on the desk, so a change does not cost a walk to the TV."""
    import os
    from . import ps2preview
    path = os.path.abspath(args.path)
    if not os.path.isfile(os.path.join(path, "world3d.json")):
        raise SystemExit("ncc: %s has no world3d.json to draw" % path)
    out = args.out or os.path.join(path, "preview.png")
    image = ps2preview.render(path, override_material=args.material)
    image.save(out)
    print()
    print("  %s  (%dx%d, as the console would draw it)" % (out, *image.size))
    print(ps2preview.describe(path))
    print()
    print("  Compare this against the television. Same shapes but different")
    print("  colours is the frame buffer or the lighting; a texture right here")
    print("  and flat on the console is the upload.")
    print()
    return 0


def _mesh(args):
    """Read a model, say what it will cost, and draw it without a console."""
    import os
    from . import meshimport, ps2preview
    try:
        if os.path.splitext(args.file)[1].lower() == ".fbx":
            from . import fbximport
            mesh = fbximport.load_fbx(args.file)
        else:
            mesh = meshimport.load_obj(args.file)
    except (OSError, meshimport.MeshError) as exc:
        raise SystemExit("ncc: %s" % exc)
    print(meshimport.describe(mesh))

    factor = mesh.scale_to_height(args.height)
    mesh.centre_on_floor()
    print()
    print("  SCALE      x%.5f to stand %.1f units tall" % (factor, args.height))

    out = args.out or os.path.splitext(args.file)[0] + "_preview.png"
    if args.turnaround:
        from PIL import Image
        sheet = Image.new("RGB", (640, 448), (10, 12, 14))
        for index, angle in enumerate((0, 90, 180, 270)):
            image, _ = ps2preview.render_mesh(
                mesh, [0, args.height * 0.72, -args.height * 1.7],
                [0, args.height * 0.5, 0], fov=45, quantise=8, rotation=angle)
            sheet.paste(image.resize((320, 224), Image.LANCZOS),
                        ((index % 2) * 320, (index // 2) * 224))
        sheet.save(out)
        stats = {"drawn": "4 views", "culled": "-", "skipped": "-"}
    else:
        image, stats = ps2preview.render_mesh(
            mesh, [args.height * 0.9, args.height * 0.78, -args.height * 1.45],
            [0, args.height * 0.5, 0], fov=50, quantise=8, rotation=args.rotate)
        image.save(out)
    print("  DRAWN      %s triangles, %s backfacing, %s off screen"
          % (stats["drawn"], stats["culled"], stats["skipped"]))
    print("  %s" % out)
    print()
    return 0


def _targets(args):
    for t in TARGETS.values():
        print(f"\n  {t.name}  ({t.key})")
        print(f"    resolution   {t.width}x{t.height}")
        print(f"    ram          {t.ram_bytes // 1024} KB")
        print(f"    vram         {t.vram_bytes // 1024} KB")
        print(f"    max texture  {t.max_texture}px")
        print(f"    color depths {', '.join(str(d) + '-bit' for d in t.color_depths)}")
        print(f"    fpu          {'yes' if t.has_fpu else 'no (fixed point 20.12)'}")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
