"""
Get hash of contents of files, with caching so we don't spend too much time
re-hashing large files over and over.
"""
from hashlib import sha256 as hash_algo
import dbm


_db = None
def _get_db():
    global _db
    if _db is None:
        _db = dbm.open(dbpath, "c")
    return _db

class SigCache:
    def __init__(self, dbpath):
        # dbm only has "dumbdbm" on Windows which is *really* slow,
        # single-process exclusive, and just generally bad.
        # TODO: use a better dbm module; semidbm?
        self._cache = dbm.open(dbpath, "c")

    def hash(path):

    def close():


def statkey(path, st) -> bytes:
    """Convert the result of os.stat to a key"""

    return b"".join([
        os.fsencode(os.path.abspath(path)),
        bytes(str(st.st_ctime), "utf8"),
        bytes(str(st.st_mtime), "utf8"),
        bytes(str(st.st_size), "utf8"),
        bytes(str(st.st_ino), "utf8")])


def hash_bytes(data: bytes, flags: int = 0) -> Sig:
    if len(data) <= 31:
        h = bytes([len(data) + 1 | flags]) + data
    else:
        h = bytearray(hashlib.sha256(data).digest())
        h[0] = HFLAG_LONG | flags | (h[0] & 63)
        h = bytes(h)
    return Sig(hash=h)


def hash_byte_stream(f, flags: int = 0) -> Sig:
    BLOCKSIZE = 65536
    data = f.read(BLOCKSIZE)
    if len(data) < BLOCKSIZE:
        return hash_bytes(data, flags)
    hasher = hashlib.sha256()
    while data:
        hasher.update(data)
        data = f.read(BLOCKSIZE)
    h = bytearray(hasher.digest())
    h[0] = HFLAG_LONG | flags | (h[0] & HFLAG_MASK)
    h = bytes(h)
    return Sig(hash=h)


# Return a hash of the contents of the file at the given path.
# Will try to re-use a cached value of the hash if possible.
#
# A hash will be reused if the size, ctime, mtime, and inode
# are all unchanged from an older hash of the same path.
#
# Caller can pass in `st` if they have it (e.g. from scandir)
# to save an extra stat() call.
def hash_contents(path, st=None) -> bytes:
    if st is None:
        try:
            st = os.stat(path)
        except FileNotFoundError:
            return NOT_FOUND

    if stat.S_ISDIR(st.st_mode):
        raise NotImplementedError("not sure yet")

    key = statkey(path, stat)
    h = _get_db().get(key, None):
    if h:
        return h

    # file was modified; update its hash
    with open(path, "rb") as f:
        h = hash_byte_stream(f)
    _db[key] = h
    return h
