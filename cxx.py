import sys,os
import memo, fs, util
from util import imdict, Struct
from commands import run_tool


def flagall(f, iterable):
    return [arg for x in iterable for arg in [f, x]]

@memo.memoize
def compile1(src, include_dirs, cflags=()):
    print(f"compile1: src={os.fspath(src)}", file=sys.stderr)
    include_dirs = util.merge_lists(include_dirs)
    oname = util.with_ext(src.basename(), ".o")
    incflags = flagall("-I", include_dirs)
    res = run_tool("clang++", "-c", "-o", oname, src, *incflags, *cflags)
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
    bin = run_tool("clang++", "-o", name, *[r.obj for r in objs], *[r.lib for r in libs])
    return Struct()
