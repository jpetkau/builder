import hashes
import StringIO


def take_unique(n, seq):
    s = set()
    for v in seq:
        if v not in s:
            s.add(v)
            yield v
            if len(s) >= n:
                return


class RemoteStore:
    """Use the Store API to access a remote server"""

    def put_blob(self, blob):
        hash = hashes.hash_object(blob)
        self.blobs[hash] = blob
        return hash

    def put_tree(self, entries):
        treeblob = hashes.format_tree(entries)
        hash = hashes.hash_treeblob(treeblob)
        self.trees[hash] = treeblob
        return hash

    def get_blob(self, hash):
        return self.blobs.get(hash, None)

    def get_blob_reader(self, hash):
        blob = self.get_blob(hash)
        if blob:
            return StringIO.StringIO(blob)
        else:
            return None

    def get_tree(self, hash):
        tree = self.trees.get(hash, None)
        if tree is not None:
            tree = hashes.parse_tree(tree)
        return tree

    def check_tree(self, hash, max_results=100):
        def check_tree_iter(hash):
            if hash not in self.trees:
                yield hash
                return
            for (cmode, cname, chash) in self.get_tree(hash):
                if cmode in hashes.tree_modes:
                    for h in check_tree_iter(chash):
                        yield h
                else:
                    if chash not in self.blobs:
                        yield chash

        return list(take_unique(100, check_tree_iter(hash)))


# Given a dictionary of string -> (string | dict),
# populate a store (presumably a MockStore).
def push_dict_as_tree(store, d):
    contents = []
    for name, v in d.items():
        if type(v) is dict:
            h = push_dict_as_tree(store, v)
            contents.append((hashes.mode_tree, name, h))
        else:
            h = store.put_blob(v)
            contents.append((hashes.mode_blob, name, h))
    return store.put_tree(contents)


def pull_tree_as_dict(store, hash):
    entries = store.get_tree(hash)
    tree = {}
    for (cmode, cname, chash) in entries:
        if cmode in hashes.tree_modes:
            tree[cname] = pull_tree_as_dict(store, chash)
        else:
            tree[cname] = store.get_blob(chash)
    return tree
