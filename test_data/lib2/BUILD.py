import commands, cxx, memo, fs


loc = fs.src_tree_for(__file__)


def lib2():
    return cxx.lib("lib2", srcs=[loc / "lib2.cpp"], include_dirs=[loc],)
