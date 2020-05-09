"""
Get hash of contents of files, with caching so we don't spend too much time
re-hashing large files over and over.
"""
import dbm, os, stat, struct


class RaceError(RuntimeError):
    ...


class FsSigCache:
    """
    Maintain a cache of the content hashes of filesystem files

    Each cache entry stores the (inode, size, ctime, mtime) of the file
    that was hashed; if all of those match, we re-use the old hash on
    subsequent calls.
    """

    def __init__(self, dbpath, hasher):
        # dbm only has "dumbdbm" on Windows which is *really* slow,
        # single-process exclusive, and just generally bad.
        # TODO: use a better dbm module; semidbm?
        self._db = dbm.open(dbpath, "c")
        self._hasher = hasher

    # Return a hash of the contents of the file at the given path.
    # Will try to re-use a cached value of the hash if possible.
    #
    # A hash will be reused if the size, ctime, mtime, and inode
    # are all unchanged from a stored hash of the same path.
    #
    # Caller can pass in `st` if they have it to save an extra
    # stat() call.
    #
    # Note that on Windows, scandir's stat() is incorrect:
    # - it does not observe modifications to a hard-linked file
    #   via a different path
    # - inode is 0
    #
    # But we really want to support scandir because it's *much*
    # faster for checking that a large tree is unchanged.
    def hash(self, path, st=None) -> bytes:
        path = bytes(os.path.abspath(path), "utf8")
        if st is None:
            st = os.stat(path)
        assert isinstance(st, os.stat_result)
        if stat.S_ISDIR(st.st_mode):
            raise IsADirectoryError("attempt to hash contents of a directory")

        key = _st_key(st)
        old = self._db.get(path, None)
        if old and old[:_ST_KEY_SIZE] == key:
            return old[_ST_KEY_SIZE:]

        # have to do heavier work now so get a real stat
        if not st.st_ino:
            st = os.stat(path)
        h = self._hasher(path)
        st2 = os.stat(path)

        # check that file wasn't modified while we hashed it
        if st != st2:
            raise RaceError(f"file was modified while hashing: {st} -> {st2}")
        self._db[path] = _st_key(st) + h
        return h

    def close(self):
        self._db.close()


# return bytes containing parts of st that we consider relevant
def _st_key(st):
    return struct.pack("<4Q", st.st_ino, st.st_size, st.st_ctime_ns, st.st_mtime_ns)


def _st_key_match(st, key):
    # match as best we can for the st from stat()
    stk = _st_key(st)
    if st.st_ino:
        return stk == key
    else:
        return stk[4:] == key[4:]


_ST_KEY_SIZE = 16
