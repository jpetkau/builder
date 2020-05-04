def cxx_ar(name, objs):
    ofile = fs.gen_dir() / f"lib{name}.a"
    return run_tool("ar", *[relpath(x) for x in objs], "-o", ofile, output=ofile)


def cxx_link(name, objs):
    ofile = fs.gen_dir() / f"lib{name}.a"
    return run_tool("ld", *[relpath(x) for x in objs], "-o", ofile, output=ofile)


def cxx_obj(src, flags):
    out = fs.gen_dir() / util.with_ext(src, ".o")
    return run_tool("c++", src, "-c", out, *flags)


def cxx_binary(srcs, deps):
    objs = [cxx_obj(x) for x in srcs]
    bin = cxx_link(objs=objs, libs=cat(d.lib for d in deps))
    return Struct()
