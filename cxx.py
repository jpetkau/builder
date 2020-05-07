import sys, os
import memo, fs, util
from util import imdict, Struct
from commands import run_tool


def parse_dep_file(stream):
    lines = iter(stream)
    for line in lines:
        line = line.rstrip("\n")
        while line.endswith("\\"):
            line = line[:-1] + iter.next().rstrip("\n")
        files = line.replace("\\ ", "\0").split()
        files = [f.replace("\0", " ") for f in files]
    main = files[0]
    assert main.endswith(":")
    return main[:-1], files


def check_deps():
    # note: not memoized
    deps = memo.get(cas.sig(("deps", context.current_call_hash)))
    if not deps:
        return False
    # deps is a bunch of files
    for (path, hash) in deps:
        if cas.sig(path) != hash:
            return False
    return True


# return [f, it[0], f, it[1], ...]
# e.g. ["-I", dir1, "-I", dir2]
def repflag(f, iterable):
    return [arg for x in iterable for arg in [f, x]]


# @memo.memoize_with_deps
@memo.memoize
def compile1(src, include_dirs, cflags=()):
    print(f"compile1: src={os.fspath(src)}", file=sys.stderr)
    include_dirs = util.merge_lists(include_dirs)
    oname = util.with_ext(src.basename(), ".o")
    dname = util.with_ext(src.basename(), ".d")
    incflags = repflag("-I", include_dirs)
    res = run_tool(
        "clang++", "-c", "-o", oname, "-MM", "-MF", dname, src, *incflags, *cflags
    )
    # record_cxx_deps(res.tree / dname)
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
    print(f"binary: srcs={srcs}", file=sys.stderr)
    include_dirs = util.merge_lists(include_dirs, *[lib.include_dirs for lib in libs])
    objs = compile(srcs, include_dirs=include_dirs)
    bin = run_tool(
        "clang++", "-o", name, *[r.obj for r in objs], *[r.lib for r in libs]
    )
    return bin
