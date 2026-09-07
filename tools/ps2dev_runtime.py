"""Give every ps2dev executable the 32-bit MinGW runtime it needs.

The prebuilt Windows toolchain is 32-bit and dynamically linked against the
MinGW runtime, which it does not ship. The failure this causes is unusually
nasty: the gcc driver starts, spawns cc1, and cc1 dies before printing anything,
so make reports `Error 1` with no diagnostic and the compiler works fine when
you run it by hand with a different PATH.

So rather than depending on the machine having a 32-bit MinGW installed, this
reads what the binaries actually import, fetches those DLLs from the MSYS2
i686 repository, and drops a copy next to every executable in the toolchain.

Usage:  python tools/ps2dev_runtime.py <ps2dev root>
"""

import io
import os
import re
import struct
import sys
import tarfile
import urllib.request

REPO = "https://repo.msys2.org/mingw/i686/"

# DLLs Windows itself provides. Anything else has to come from somewhere.
SYSTEM = {
    "kernel32.dll", "msvcrt.dll", "user32.dll", "advapi32.dll", "shell32.dll",
    "ws2_32.dll", "ole32.dll", "gdi32.dll", "wsock32.dll", "crypt32.dll",
    "iphlpapi.dll", "setupapi.dll", "version.dll", "winmm.dll", "psapi.dll",
    "oleaut32.dll", "dbghelp.dll", "bcrypt.dll", "shlwapi.dll", "userenv.dll",
    "ntdll.dll", "imm32.dll", "comdlg32.dll", "comctl32.dll", "secur32.dll",
}

# Which MSYS2 package provides which DLL. Only the ones this toolchain wants.
PACKAGES = {
    "libwinpthread-1.dll": "mingw-w64-i686-libwinpthread-git-",
    "libiconv-2.dll":      "mingw-w64-i686-libiconv-",
    "libcharset-1.dll":    "mingw-w64-i686-libiconv-",
    "libintl-8.dll":       "mingw-w64-i686-gettext-runtime-",
    "libexpat-1.dll":      "mingw-w64-i686-expat-",
    "libgcc_s_dw2-1.dll":  "mingw-w64-i686-gcc-libs-",
    "libstdc++-6.dll":     "mingw-w64-i686-gcc-libs-",
    "libgmp-10.dll":       "mingw-w64-i686-gmp-",
    "libisl-23.dll":       "mingw-w64-i686-isl-",
    "liblzma-5.dll":       "mingw-w64-i686-xz-",
    "libmpc-3.dll":        "mingw-w64-i686-mpc-",
    "libmpfr-6.dll":       "mingw-w64-i686-mpfr-",
    "libtermcap-0.dll":    "mingw-w64-i686-termcap-",
    "libzstd.dll":         "mingw-w64-i686-zstd-",
    "zlib1.dll":           "mingw-w64-i686-zlib-",
}


def pe_imports(path):
    """The DLL names a PE binary imports, or [] if it is not one."""
    with open(path, "rb") as fh:
        data = fh.read()
    try:
        off = struct.unpack_from("<I", data, 0x3C)[0]
        if data[off:off + 4] != b"PE\0\0":
            return []
        nsec = struct.unpack_from("<H", data, off + 6)[0]
        optsz = struct.unpack_from("<H", data, off + 20)[0]
        opt = off + 24
        magic = struct.unpack_from("<H", data, opt)[0]
        dd = opt + (96 if magic == 0x10B else 112)
        rva = struct.unpack_from("<I", data, dd + 8)[0]
        if not rva:
            return []

        secs = []
        base = opt + optsz
        for i in range(nsec):
            b = base + i * 40
            secs.append((struct.unpack_from("<I", data, b + 12)[0],
                         struct.unpack_from("<I", data, b + 8)[0],
                         struct.unpack_from("<I", data, b + 20)[0]))

        def to_offset(r):
            for va, vsize, raw in secs:
                if va <= r < va + max(vsize, 1):
                    return raw + (r - va)
            return None

        names = []
        cursor = to_offset(rva)
        while cursor:
            entry = data[cursor:cursor + 20]
            if len(entry) < 20 or entry == b"\0" * 20:
                break
            name_rva = struct.unpack_from("<I", entry, 12)[0]
            if not name_rva:
                break
            at = to_offset(name_rva)
            names.append(data[at:data.index(b"\0", at)].decode())
            cursor += 20
        return names
    except (struct.error, ValueError, IndexError):
        return []


def scan(root):
    """(directories holding executables, DLL names that are missing)."""
    dirs, have, need = set(), set(), set()
    for base, _, files in os.walk(root):
        for f in files:
            low = f.lower()
            if low.endswith(".dll"):
                have.add(low)
            elif low.endswith(".exe"):
                dirs.add(base)
                need.update(n.lower() for n in pe_imports(os.path.join(base, f)))
    return sorted(dirs), sorted(n for n in need if n not in SYSTEM and n not in have)


def fetch(package_prefix, index):
    hits = sorted(set(re.findall(re.escape(package_prefix) + r"\d[^\"<>]*?\.pkg\.tar\.zst",
                                 index)))
    if not hits:
        return {}
    from compression.zstd import ZstdFile          # Python 3.14+
    raw = urllib.request.urlopen(REPO + hits[-1], timeout=180).read()
    out = {}
    with ZstdFile(io.BytesIO(raw)) as z:
        with tarfile.open(fileobj=io.BytesIO(z.read())) as tf:
            for m in tf.getmembers():
                if m.name.endswith(".dll") and "/bin/" in m.name:
                    out[os.path.basename(m.name)] = tf.extractfile(m).read()
    return out


def main(root):
    dirs, missing = scan(root)
    if not missing:
        print("Runtime is complete; nothing to fetch.")
        return 0

    unknown = [d for d in missing if d not in PACKAGES]
    wanted = sorted({PACKAGES[d] for d in missing if d in PACKAGES})
    print("Missing:", ", ".join(missing))

    index = urllib.request.urlopen(REPO, timeout=60).read().decode("utf-8", "replace")
    files = {}
    for prefix in wanted:
        got = fetch(prefix, index)
        if not got:
            print("  could not find a package for", prefix)
        files.update(got)

    for name, data in files.items():
        for d in dirs:
            with open(os.path.join(d, name), "wb") as fh:
                fh.write(data)
    print("Installed %d DLL(s) beside %d executable director%s."
          % (len(files), len(dirs), "y" if len(dirs) == 1 else "ies"))

    if unknown:
        print("Still unaccounted for:", ", ".join(unknown))
        print("Add them to PACKAGES in this file.")
        return 1
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(main(sys.argv[1]))
