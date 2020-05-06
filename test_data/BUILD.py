import fs
import cxx

# TODO: there should be a tree object corresponding to each BUILD file;
# paths in the build file are relative to that tree.
#
# Could have a global named `src` or `here` which is that tree.
# Need to get fancy with import machinery first.


def lib1():
    return cxx.lib(
        "lib1",
        srcs=([fs.src_root / "lib1/lib1.cpp"]),
        include_dirs=[fs.src_root / "lib1"],
    )


def lib2():
    return cxx.lib(
        "lib2",
        srcs=[fs.src_root / "lib2/lib2.cpp"],
        include_dirs=[fs.src_root / "lib2"],
    )


def main():
    return cxx.binary("main", srcs=[fs.src_root / "bin/main.cpp"], libs=[lib1(), lib2()])
