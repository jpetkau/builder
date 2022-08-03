#!/usr/bin/env python3

import json, subprocess

"""
multi arch support:

config gets more interesting now fer sure.

- We have some set of installed toolchains that we found, and some additional
set that may be checked in.

Want to support:
- no-options build does something reasonable
- minimal spec (e.g. just target=x86 vs. target=x64) also does something reasonable
- either case first expands to complete spec, which has proper memoization
- targets can implement arbitrary logic to decide what to build.

Mechanism: command line sets some top-level options, which can be interpreted arbitrarily by scripts.
Default set of scripts does something reasonable with them.

There should also be options which can be set from the command line in ways that scripts can't easily mess with (e.g. "--dry-run" or something shouldn't be overridable!)

Start with minimum I need right now:

- Use installed MSVC or install clang
- Cross-compile MSVC to 32-bit

Config has:
    host_arch
    target_arch

def cxx_toolchain(host_arch, target_arch):
    return ...

"""

# should redistribute this I suppose but ick.
VSWHERE_EXE = r"C:\Program Files (x86)\Microsoft Visual Studio\Installer\vswhere.exe"

def run_vswhere():
    return data

class VCToolInstall(NamedTuple):
    ver: str
    host_arch: str
    target_arch: str
    bin: str
    include: str
    lib: str
    cxx_bin: str
    link_bin: str
    ar_bin: str

def find_toolchain(js):
    install_dir = os.path.join(js.installationPath, r"VC/Tools/MSVC/*")


def find_vs_installs():
    p = subprocess.run([VSWHERE_EXE, "-format", "json"], stdout=subprocess.PIPE)
    vswhere = json.loads(p.stdout)
    installs = []
    for w in vswhere:
        for bin in glob.glob(os.path.join(w.installationPath, "VC/Tools/MSVC/*/bin/Host*/*")):
            bin = os.path.abspath(bin)
            vcdir, ver, _, host, target = bin.rsplit(os.path.sep, 4)
            installs.append(VCToolInstall(
                ver = ver,
                host_arch = host[4:],
                target_arch = target,
                bin = bin,
                include = os.path.join(vcdir, ver, "include"),
                lib = os.path.join(vcdir, ver, "lib", target),
                cxx_bin = os.path.join(bin, "cl.exe"),
                link_bin = os.path.join(bin, "lib.exe"),
                link_bin = os.path.join(bin, "link.exe")))


installs = find_vs_installs()


# @memo.memoize_with_deps
@memo.memoize
def compile1(src, include_dirs, cflags=()):
    include_dirs = util.merge_lists(include_dirs)
    oname = util.with_ext(src.basename(), ".o")
    dname = util.with_ext(src.basename(), ".d")
    incflags = repflag("-I", include_dirs)
    res = run_tool(
        "clang++", "-c", "-o", oname, "-MMD", "-MF", dname, src, *incflags, *cflags
    )
    # memo.fs_deps(src, *include_dirs)
    # - but for blobs (or anything we had to call stat on), should make dep when
    #   path is first constructed, unless you're careful not to.
    # - so wrapping something like 'stat' would work pretty well
    return Struct(**res, obj=res.tree / oname)


def compile(srcs, include_dirs, cflags=()):
    return [compile1(src, include_dirs, cflags) for src in srcs]


@memo.memoize
def lib(name, srcs, include_dirs, cflags=()):
    objs = [r.obj for r in compile(srcs, include_dirs, cflags)]
    libname = name + ".a"
    res = run_tool("ar", "rc", libname, *objs)
    return Struct(**res, lib=res.tree / libname, include_dirs=include_dirs)


# useful: have output type be a struct or whatever, but with __fspath__
# defined for the 'primary' output file.
@memo.memoize
def binary(name, *, srcs, include_dirs=[], libs=[]):
    include_dirs = util.merge_lists(include_dirs, *[lib.include_dirs for lib in libs])
    objs = compile(srcs, include_dirs=include_dirs)
    bin = run_tool(
        "clang++", "-o", name, *[r.obj for r in objs], *[r.lib for r in libs]
    )
    return bin
