import os
import anydbm
import stat
import hashes
import errno
import shutil


def statkey(path, st):
    """Convert the result of os.stat to a key for lookup in buildercache"""

    # The "ct", "mt", etc. prefixes aren't really necessary, but help
    # when debugging / inspecting keys.
    return (
        path
        + "\0ct"
        + str(st.st_ctime)
        + " mt"
        + str(st.st_mtime)
        + " sz"
        + str(st.st_size)
        + " in"
        + str(st.st_ino)
    )


class Blob(object):
    """Represents a file on disk and all its contents.
    """

    def __init__(self, fs, path, st, hash=None):
        self.fs = fs
        self.path = path
        self.name = os.path.basename(path)
        self.stat = st
        self._hash = hash
        if stat.S_ISLNK(st.st_mode):
            self.mode = hashes.mode_symlink
        elif stat.S_IXUSR & st.st_mode:
            self.mode = hashes.mode_xblob
        else:
            self.mode = hashes.mode_blob

    @property
    def hash(self):
        if self._hash is None:
            st = self.stat
            cachekey = statkey(self.path, st)
            if cachekey in self.fs.cache:
                self._hash = self.fs.cache[cachekey]
            else:
                self._hash = hashes.hash_object(self.blobdata())
                self.fs.cache[cachekey] = self._hash
        return self._hash

    def blobdata(self):
        return self.fs.get_blob(self.path, self.mode)


class Tree(object):
    """Represents a directory on disk and all its contents.
    """

    # Only one mode is valid for trees
    mode = hashes.mode_tree

    def __init__(self, fs, path, entries=None, hash=None):
        self.fs = fs
        self.path = path
        self.name = os.path.basename(path)
        self._entries = None
        self._hash = hash

    def entries(self):
        """Return a list of nodes representing the entries in this directory"""
        if self._entries is None:
            self._entries = self.fs.listdir(self.path)
        return self._entries

    def tuple_entries(self):
        """Return a list of (mode, name, hash) representing the entries in this directory"""
        return [(o.mode, o.name, o.hash) for o in self.entries()]

    def format_tree(self):
        return hashes.format_tree(self.tuple_entries())

    @property
    def hash(self):
        if self._hash is None:
            self._hash = hashes.hash_treeblob(self.format_tree())
        return self._hash


class FS:
    """Wrap the minimal filesystem operations needed to sync a tree.
    This provides two abilities over directly making filesystem calls:
    - it can be mocked for unit tests
    - it caches the hash of files and contents of directories
    """

    def __init__(self, root, dbpath=None):
        self.root = root
        if dbpath is None:
            dbpath = os.path.join(root, ".buildercache")
        self.cache = anydbm.open(dbpath, "c")

    def node(self, path):
        try:
            st = os.stat(os.path.join(self.root, path))
        except OSError as ex:
            if ex.errno == errno.ENOENT:
                return None
            raise
        if stat.S_ISDIR(st.st_mode):
            return self.treenode(path)
        else:
            return self.blobnode(path, st)

    def treenode(self, path, entries=None):
        return Tree(self, path, entries=entries)

    def blobnode(self, path, st):
        return Blob(self, path, st)

    def put_blob(self, path, contents, mode=hashes.mode_blob, hash=None):
        if mode == hashes.mode_blob or mode == hashes.mode_xblob:
            with open(os.path.join(self.root, path), "wb", buffering=0) as f:
                f.write(contents)
                if mode == hashes.mode_xblob:
                    os.fchmod(f, os.stat(path).st_mode | stat.S_IXUSR)

    def delete(self, path):
        # handles symlinks but not dirs
        os.remove(path)

    def mkdir(self, path):
        os.mkdir(os.path.join(self.root, path))
        return Tree(self, path, entries=[])

    def remove(self, path):
        fullpath = os.path.join(self.root, path)
        try:
            os.remove(fullpath)
        except OSError as ex:
            if ex.errno == errno.EISDIR:
                shutil.rmtree(fullpath)
            else:
                raise

    def listdir(self, path):
        names = sorted(os.listdir(os.path.join(self.root, path)))
        return [self.node(os.path.join(path, name)) for name in names]

    def get_blob(self, path, mode):
        fullpath = os.path.join(self.root, path)
        if mode == hashes.mode_symlink:
            return os.readlink(fullpath)
        else:
            with open(fullpath, "rb") as f:
                return f.read()
