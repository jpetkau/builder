import hashes
import os

# A local node contains:
# - name
# - mode
# - ability to get contents

# A remote node is similar. Note that it is a descriptor of how to fetch
# a tree or blob, not the tree or blob itself.


def pull_tree(store, hash, fs, path):
    pull_object(store, hash, hashes.mode_tree, fs, path)


def pull_object(store, hash, mode, fs, path, local_obj=None):
    if local_obj is None:
        local_obj = fs.node(path)

    # First check if we already have it
    if local_obj is not None and local_obj.mode == mode and local_obj.hash == hash:
        return local_obj

    # No, we don't. Check if we can just write a simple object
    if mode not in hashes.tree_modes:
        if local_obj is not None:
            fs.remove(path)
        return fs.put_blob(path, store.get_blob(hash), mode=mode, hash=hash)

    # We're pulling a tree
    if local_obj is None:
        local_obj = fs.mkdir(path)
    elif local_obj.mode != hashes.mode_tree:
        # local_obj was a blob, not a tree. Replace it with an empty directory.
        fs.remove(path)
        local_obj = fs.mkdir(path)

    local_contents = dict((o.name, o) for o in local_obj.entries())

    remote_entries = store.get_tree(hash)
    new_local_entries = []
    for (cmode, cname, chash) in remote_entries:
        local_child = local_contents.get(cname)

        # Mark this local node as synchronized
        if local_child is not None:
            del local_contents[cname]

        o = pull_object(store, chash, cmode, fs, os.path.join(path, cname), local_child)
        new_local_entries.append(o)

    # delete extra entries from local_obj
    for (name, node) in local_contents.items():
        fs.remove(os.path.join(path, name))

    return fs.treenode(path, entries=new_local_entries)


# Push a tree to the remote repository.
# Protocol:
# 1. Check if the tree is already there. If not, the query will return
#    a (possibly incomplete) list of missing hashes.
def push_tree(tree, store):
    reverse_index = None

    while True:
        missing = store.check_tree(tree.hash)

        if len(missing) == 0:
            # Remote store already has this full tree
            return

        if reverse_index is None:
            reverse_index = {}
            for node in tree.all_nodes():
                reverse_index[node.hash] = node

        for m in missing:
            if m.hash not in reverse_index:
                raise IOError("Store needs object ", m, " but we don't have it")
            node = reverse_index[m.hash]
            if node.nodetype == "tree":
                store.put_tree(node.tuple_entries())
            else:
                store.put_blob(node.blobcontents())
