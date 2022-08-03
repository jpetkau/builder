import commands, cxx, memo, fs


loc = fs.src_tree_for(__file__)


@memo.memoize
def trivial():
    return 1


@memo.memoize
def trivial2():
    return trivial() + trivial()


def echo():
    return commands.run_tool("echo", "hi").stdout.bytes().rstrip()


@memo.memoize
def echo_m():
    return commands.run_tool("echo", "hi").stdout.bytes().rstrip()


def copy_stuff():
    d1 = commands.run_tool("cp", loc / "somefile.txt", "out.txt")
    d2 = commands.run_tool("cp", loc / "somefile.txt", "out.txt")
    d3 = commands.run_tool("cat", d1.tree / "out.txt", d2.tree / "out.txt")
    return d3.stdout.bytes()


def lib1():
    return cxx.lib("lib1", srcs=([loc / "lib1/lib1.cpp"]), include_dirs=[loc / "lib1"],)


def main():
    # aha: this doesn't play well because it treats our file as a package
    # e.g. if `root.foo` is the contents of some build file, and so is `root.foo.bar`,
    # then foo must also be a package.
    # and we can't tell from __import__ if someone is importing foo for itself or
    # for its subpackages, so can't separate them either.
    #
    # TODO: read up on python loaders and do it right
    from . import lib2
    print(f"lib2 is {lib2}")
    return cxx.binary("main", srcs=[loc / "bin/main.cpp"], libs=[lib1(), lib2.lib2()])
