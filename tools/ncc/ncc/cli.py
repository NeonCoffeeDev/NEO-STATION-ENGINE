"""ncc — the Neon Coffee orchestrator."""

import argparse
import sys

from . import __version__, doctor
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

    t = sub.add_parser("targets", help="list hardware profiles")
    t.set_defaults(func=_targets)

    args = p.parse_args(argv)
    if not getattr(args, "func", None):
        p.print_help()
        return 0
    return args.func(args)


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
