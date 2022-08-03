#!/usr/bin/env python3
"""
Implements custom importing of BUILD.py files

- they have a global object `loc` which is a tree at the build file location.

Uh, why do I need this at all, vs. just writing

    loc = tree_for(__FILE__) ?

"""
import os, sys, types
import fs


def importer(name, globals=None, locals=None, fromlist=(), level=0):
    print(f"importer {name!r} fromlist={fromlist!r} level={level!r}")
    parts = [*filter(None, name.split("."))]
    if level == 0 and parts[0] != "root":
        # normal import
        return __import__(name, globals, locals, fromlist, level)

    if level > 0:
        # relative import
        print(f"  __name__={globals['__name__']}")
        pparts = [*filter(None, globals["__name__"].split("."))]
        print(f"  pparts={pparts}")
        if len(pparts) < level:
            raise ModuleNotFoundError
        parts = pparts[-level:] + parts
    name = ".".join(parts)
    print(f"importing {name}")

    if name in sys.modules:
        return sys.modules[name]

    if parts[0] != "root":
        raise ImportError("imported build files must start with 'root': {name}")

    bdir = fs.src_root / name[5:].replace(".", "/")
    srcpath = bdir / "BUILD.py"
    try:
        with open(srcpath, "rb") as f:
            src = f.read()
    except FileNotFoundError:
        raise ModuleNotFoundError(f"no build file at {srcpath}")

    m = types.ModuleType(name)
    m.__builtins__ = _buildfile_builtins
    m.__file__ = os.fspath(srcpath)
    m.loc = bdir.contents()
    sys.modules[name] = m
    try:
        exec(src, m.__dict__, m.__dict__)
    except:
        del _buildfiles[name]
        raise
    return m


_buildfile_builtins = {**__builtins__, "__import__": importer}
