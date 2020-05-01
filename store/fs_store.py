import hashes, os


class FsStore:
    """Filesystem-based object store"""

    def __init__(self, root):
        self.root = root
        self._exists = {}  # map hash -> bool of known hashes

    def put_blob(self, blob):
        """Store a blob"""
        hash = hashes.hash_object(blob)
        self._put(hash, blob)
        self._exists[hash] = True
        return hash

    def put_tree(self, entries):
        """Store a tree, given as a list of (mode, name, hash) entries. This does
    not ensure that the entries exist in the store."""
        treeblob = hashes.format_tree(entries)
        hash = hashes.hash_treeblob(treeblob)
        self._put(hash, treeblob)
        return hash

    def _put(self, hash, data):
        path = self.get_path(hash)
        d = os.path.dirname(path)
        if not os.path.isdir(d):
            os.makedirs(d)
        with open(self.get_path(hash), "wb") as f:
            f.write(data)
            self._exists[hash] = True

    def get_blob(self, hash):
        if not self.exists(hash):
            return None
        path = self.get_path(hash)
        with open(path, "rb") as f:
            return f.read()

    def get_blob_reader(self, hash):
        """Return a reader (open file-like object) on the given hash, or None."""
        if not self.exists(hash):
            return None
        path = self.get_path(hash)
        return open(path, "rb")

    def get_tree(self, hash):
        treeblob = self.get_blob(hash)
        if treeblob is None:
            return None
        return hashes.parse_tree(treeblob)

    def get_path(self, hash):
        h = hash.encode("hex")
        return os.path.join(self.root, "objects", h[:2], h[2:])

    def exists(self, hash):
        path = self.get_path(hash)
        if hash not in self._exists:
            self._exists[hash] = os.path.exists(path)
        return self._exists[hash]

    def check_tree(self, hash, max_results=100):
        """Check if we have the entire tree rooted at 'hash'. If not,
    return a (possibly incomplete) set of which hashes are missing.
    Returns the empty set if it's all here.

    I need to think about this more.
    Check_tree as implemented here is inefficient. I could fix it by explicitly
    recording when a tree is complete in the filesystem, so I don't need to walk it.

    Forcing trees to be complete at upload time would also work, but I don't like it.
    But if I want git compatibility, that's the only way.
    """

        missing = set()
        result = []

        def check(hash, isTree):
            if hash in missing:
                return
            if isTree:
                tree = self.get_tree(hash)
                if tree is None:
                    missing.add(hash)
                    result.append(hash)
                    return
                for (cmode, cname, chash) in tree:
                    check(chash, cmode in hashes.tree_modes)
                    if len(result) >= max_results:
                        return
            else:
                if not self.exists(hash):
                    missing.add(hash)
                    result.append(hash)

        check(hash, True)
        return result


if __name__ == "__main__":
    # When run with 'python -m FsStore', serve from the current
    # directory
    pass
