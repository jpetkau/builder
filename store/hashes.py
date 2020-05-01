from hashlib import sha1
import re


valid_nodetypes = set(["blob", "tree"])


mode_blob = "100644"  # regular file
mode_xblob = "100755"  # executable file
mode_symlink = "120000"
mode_tree = "040000"
mode_git_submodule = "160000"

valid_modes = set(
    [
        mode_blob,
        mode_xblob,
        mode_symlink,
        mode_tree,
        # mode_git_submodule
    ]
)

tree_modes = set([mode_tree, mode_git_submodule])

hash_empty_tree = "4b825dc642cb6eb9a060e54bf8d69288fbee4904".decode("hex")


def hash_object(contents, nodetype="blob"):
    h = sha1(nodetype)
    h.update(" ")
    h.update(str(len(contents)))
    h.update("\0")
    h.update(contents)
    return h.digest()


def hash_treeblob(treeblob):
    return hash_object(treeblob, nodetype="tree")


def hash_tree(entries):
    return hash_treeblob(format_tree(entries))


def format_tree(entries):
    """Format a list of entries (mode, name, hash) for transport or hashing"""
    return "".join(
        mode + " " + name + "\0" + hash for (mode, name, hash) in sorted(entries)
    )


def parse_tree(treeblob):
    """Parse the result of format_tree() back into a list of entries"""
    entries = re.findall(r"([0-9]+) ([^\0]*)\0(.{20})", treeblob, flags=re.DOTALL)
    assert format_tree(entries) == treeblob
    return entries
