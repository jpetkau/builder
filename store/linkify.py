"""
This module provides a function linkify(dirs, cache) which uses content-based hashes
to replace duplicate files in the given set of directories with hard links. It
is meant for command-line use.

It's not really related to the rest of builder, except that it uses the same
underlying cache of file hashes.
"""


def linkify(dir, fs):
    tree = fs.tree(dir)
