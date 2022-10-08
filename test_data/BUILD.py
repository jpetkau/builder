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
    from . import lib2
    return cxx.binary("main", srcs=[loc / "bin/main.cpp"], libs=[lib1(), lib2.lib2()])
