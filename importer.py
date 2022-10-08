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
    parts = [*filter(None, name.split("."))]
    if level == 0 and parts[0] != "root":
        # normal import: "import os.path"
        return __import__(name, globals, locals, fromlist, level)

    if level > 0:
        # relative import: "from ..there import that"
        # globals['__name__'] tells us what it's relative to
        pparts = [*filter(None, globals["__name__"].split("."))]
        if len(pparts) < level:
            raise ModuleNotFoundError
        parts = pparts[-level:] + parts

    if parts[0] != "root":
        raise ImportError("imported build files must start with 'root': {name}")

    for i in range(1, len(parts) + 1):
        name = ".".join(parts[:i])
        if name in sys.modules:
            m = sys.modules[name]
        else:
            m = do_import(name)

    if fromlist:
        # import x,y,z from a.b -- populate and return b
        for tail in fromlist:
            if not hasattr(m, tail):
                setattr(m, tail, do_import(name + "." + tail))
        return m
    else:
        # import a.b [as c] -- return a
        # import .b.c [as d] -- return b?
        return sys.modules[parts[0]]

def do_import(name):
    assert name=="root" or name.startswith("root.")
    bdir = fs.src_root / name[5:].replace(".", "/")
    srcpath = bdir / "BUILD.py"
    print(f"importing {name} from {srcpath}")
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
        del sys.modules[name]
        raise
    return m


_buildfile_builtins = {**__builtins__, "__import__": importer}
