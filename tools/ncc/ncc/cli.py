"""ncc -- the Neon Coffee orchestrator."""

import argparse
import os
import subprocess
import sys

from . import __version__, build as build_mod, doctor
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

    st = sub.add_parser("studio", help="open the NC Studio GUI")
    st.set_defaults(func=_studio)

    t = sub.add_parser("targets", help="list hardware profiles")
    t.set_defaults(func=_targets)

    args = p.parse_args(argv)
    if not getattr(args, "func", None):
        p.print_help()
        return 0
    return args.func(args)


def _studio(args):
    from . import toolchain as tc
    script = os.path.join(tc.project_root(), "tools", "ncstudio", "studio.py")
    if not os.path.isfile(script):
        raise SystemExit(f"ncc: NC Studio not found at {script}")
    return subprocess.call([sys.executable, script])


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
