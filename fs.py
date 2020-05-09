#!/usr/bin/env python3
"""
TODO:
- It will remain a pain using 'Path' objects instead of plain pathnames when defining commands to run. Maybe allow pathnames in more places, and check that they're in safe places before using?

filesystem:

* mapping from pure view to real FS is via a shim layer with aproppriate
  concessions to reality.

* file content hash database is maintained separately - cache hashes with name,
  inode, filesize, modification time; we trust the hash as long as everything
  else looks the same. Models a real content-hashing filesystem.

* pure view of FS is much like git: a tree is represented by a hash of its root,
  which is a list of name + contents.

* suppose we want to run a binary that takes an FS tree as input. There is a
  method to explicitly request that tree materialized on the FS somewhere.

* often it's *already* materialized on the FS somewhere, possibly in multiple
  places. How do we pick which one?

  - for read-only trees, dir is based on that tree's own content hash. this may
    involve an extra copy or link for intermediate steps. Removing those is an
    optimization for later.

    [Less easy if we include the source tree, but that overlaps with the
    partial-subset-magic case; leave it for later too.]

  - for writable trees, dir is based on the memo hash we're currently working
    on.

* Logically: do we distinguish `Blob` from `bytes`?

  Yes: otherwise e.g. it's really inconvenient to pass a mix of command-line
  arguments and blob inputs to a command.


Source trees
------------
Source trees are a different type than `Tree`:


Scary trees
-----------
The 'gen/tree' and 'gen/blob' roots are content-named, so it's important not to
make links from there into possibly-writable locations.

However if we don't want too excessively many copies of things (or we want to
deliberately allow building things that symlink into source), we might also want
a less-trusted gen root for which we allow such things and try to deal with
them.

Again, later optimization.


Files modified during build
---------------------------
Need to build mechanisms to detect if it does and delete any possibly-corrupt
state, but initially pretend this can't happen.


Going from a source file to a blob
----------------------------------
1. Immediately make a copy under //blob when we first encounter a source file?
   Kinda gross, quite possibly not what we want.
2. Different type than Blob? (since it knows its location)
3. Blob with a secret path? - seems like that could cause trouble

Ok: hide stuff in the filesystem layer. Given the hash of a Tree or Blob, the
filesystem can retrieve *some* path to with that hash, either generated or in
source.

Where does it initially get that from, if it's not scanning the whole world?
- Could keep a DB of hash->last known location
- or just remember stuff that it had to read for other reasons?

rule 1 builds a tree and returns a Tree
rule 2 takes that as input

next run
- memoized rule 1 gives us back the Tree
- we should check on disk in the rule 1 gendir
  1. If that was deleted, we could check if the blobs exist and create on demand

- shouldn't have to copy blobs to content hashed location because logically
  they should be stable where they are. But copying them might be a good idea
  anyway.

Also:
- path relative to some root can be just a pair (Tree, relpath). Possibly with
  a class for convenience, but don't need new semantics.


Mutable folders
---------------

Suppose we have some tools that run in three steps, each of which wants to mutate
all over a folder tree?

- could have part of the fs marked for mutable ops. Blobs and Trees never point
  into there; you can construct them but they immediately copy data out.

- or same thing, but defer the copy until we're about to do some possibly-mutating
  operation.

[If we always copy output blobs from gen folders to a more stable cache,
it might not be that expensive anyway, since only blobs we've never seen before get
copied. So the mutable-fs case is just disabling one optimization we might be doing.]

"""
import enum, logging, os, posixpath, secrets, shutil, stat
import cas, context, util
from util import imdict


logger = logging.getLogger(__name__)


__ALLOW_GLOBAL_REFS__ = True


class Root(enum.Enum):
    ABS = "abs"  # An absolute path outside of the build tree
    GEN = "gen_root"  # A path from the generated intermediate files root
    CAS = "cas_root"  # A path into the content-addressable store area
    OUT = "out_root"  # A path from the output root
    SRC = "src_root"  # A path from the source root

    def __str__(self):
        return f"{self.value}"

    def __fspath__(self):
        if self is Root.ABS:
            return ""
        else:
            return context.config[self.value]


class Path:
    """
    Represents a location on disk, relative to some root.
    *Which* root is chosen is part of the path's hash, but the location
    of the root itself is not.

    The contents of the file referred to by the path (if any) are not
    part of the hash.

    root:
    - "abs": An absolute path outside of the build tree
    - "src": a path from the source root
    - "gen": a path from the build root
    - "out": a path from the output root
    - a Tree object
    """

    def __init__(self, root: Root, rel=""):
        assert isinstance(root, Root) or isinstance(root, Tree)
        if root is Root.ABS:
            assert os.path.isabs(rel), rel
        else:
            assert not posixpath.isabs(rel)
        self.root = root
        self._rel = rel

    def __fspath__(self):
        """
        Implement the os.PathLike interface
        """
        return os.path.normpath(os.path.join(self.root, self._rel))

    def __repr__(self):
        return f"{cas.sig(self.root)}/{self._rel}"

    def __truediv__(self, rel):
        if self.root is Root.ABS:
            return Path(self.root, os.path.normpath(os.path.join(self._rel, rel)))
        else:
            return Path(self.root, posixpath.normpath(posixpath.join(self._rel, rel)))

    def __ser__(self):
        if self.root is Root.GEN:
            raise RuleError("can't hash intermediate paths")
        return (self.root, self._rel)

    @classmethod
    def __deser__(cls, root, rel):
        return cls(root, rel)

    def __eq__(self, other):
        if self is other:
            return True
        return (
            type(self) == type(other)
            and self.root is other.root
            and self._rel == other._rel
        )

    def __hash__(self):
        return hash((type(self), self.root, self._rel))

    def tree(self, *, st=None):
        """
        Return a Tree (or Blob) representing the current contents of the filesystem
        at this path.

        Raises FileNotFoundError if there is no file at this path.

        st is the file's stat_result, if already known, to save a stat() call.
        """
        if isinstance(self.root, Tree):
            return self.root[self._rel]

        if st is None:
            st = os.stat(self)
        if stat.S_ISDIR(st.st_mode):
            entries = sorted(os.scandir(self), key=lambda p: p.name)
            return Tree({e.name: (self / e.name).tree(st=e.stat()) for e in entries})
        else:
            # this path points to a blob
            sig = cas.store_file(self, st)
            if st.st_mode & stat.S_IXUSR:
                return XBlob(content_sig=sig)
            else:
                return Blob(content_sig=sig)

    def exists(self):
        return os.path.exists(self)

    def is_file(self):
        return os.path.isfile(self)

    def is_dir(self):
        return os.path.isdir(self)

    def remove(self):
        """
        Delete the file or tree at this path.

        Only files under out_root and gen_root can be removed this way.
        """
        assert self.root in (Root.OUT, Root.GEN)
        path = os.fspath(self)
        try:
            st = os.lstat(path)
        except FileNotFoundError:
            pass
        else:
            _rmtree(path)

    def basename(self):
        return posixpath.basename(self._rel)


def abspath(p):
    return Path(Root.ABS, os.path.abspath(p))


gen_root = Path(Root.GEN, "")
cas_root = Path(Root.CAS, "")
out_root = Path(Root.OUT, "")
src_root = Path(Root.SRC, "")


def _cas_dir(kind, content_sig):
    s = content_sig.hash.hex()
    return cas_root / kind / s[:2] / s[2:]


def make_output_dir():
    # Create a temporary directory for running a tool
    # and return a path to it
    while True:
        h = secrets.token_hex(6)
        parent = gen_root / h[:2]
        p = parent / h[2:]
        try:
            os.makedirs(parent, exist_ok=True)
            os.mkdir(p)
        except FileExistsError:
            continue
        return p


class Blob:
    """
    Represents a handle to some blob of bytes as a pure value.

    Implements __fspath__ so you can use it as a path in open() etc.
    It will be materialized on disk if necessary for this.

    Note that a Blob by itself doesn't track its name; use Trees for
    that.

    The derived class XBlob is a blob that sets the x-bit on write.
    (TODO: But it does *not* return a file with the x-bit from __fspath__,
    which it should. Need more integration with cas for that.)
    """

    _mode = 0o444

    def __init__(self, *, bytes=None, content_sig=None):
        if bytes is not None:
            if content_sig:
                assert content_sig == cas.sig(bytes)
            else:
                content_sig = cas.store(bytes)
        assert content_sig.is_bytes()
        self._bytes = bytes
        self.content_sig = content_sig

    def __ser__(self):
        return self.content_sig.hash

    @classmethod
    def __deser__(cls, cshash):
        return cls(content_sig=cas.Sig(hash=cshash))

    @util.lazy_attr("_path", None)
    def path(self):
        path = Path(Root.CAS, self.content_sig.get_relpath(st_mode=self._mode))
        if not path.exists():
            self.write_copy(path, False)
        return path

    def __fspath__(self):
        return self.path().__fspath__()

    def write_copy(self, path, clobber=True):
        data = self._bytes or self.content_sig.object()
        if clobber:
            path.remove()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "xb") as f:
            os.chmod(path, self._mode)
            f.write(data)

    @util.lazy_attr("_bytes", None)
    def bytes(self):
        return self.content_sig.object()

    def __eq__(self, other):
        if self is other:
            return True
        if type(self) != type(other):
            return False
        return self.content_sig == other.content_sig


class XBlob(Blob):
    """Blob that sets executable bit when materialized"""

    _mode = 0o555


class Tree:
    def __init__(self, entries):
        # entries: dict of (name, Blob|Tree)
        if entries:
            for (k, v) in entries.items():
                assert type(k) is str
                assert isinstance(v, Blob) or isinstance(v, Tree)
        self._entries = imdict(entries)

    @util.lazy_attr("_fspath", None)
    def __fspath__(self):
        """
        Return path to root of this tree on-disk.
        """
        # TODO: If directory is already on disk, validate it
        #       (once) before assuming it's correct - could
        #       have been half-built and aborted before.
        fspath = cas.object_fspath(cas.sig(self), "tree")
        if os.path.exists(fspath):
            # assume it's valid
            return fspath
        else:
            assert "blob" not in fspath
            os.makedirs(fspath)
            fsentries = {k: v.__fspath__() for (k, v) in self.items()}
            for k in self._entries:
                util.makelink(
                    fsentries[k], os.path.join(fspath, k),
                )
            return fspath

    def write_copy(self, path, *, clobber=True, makedirs=False):
        """
        Write contents of this tree at the given path.

        This is much more expensive than __fspath__(), because it always makes
        a full copy.

        If `clobber` is True, conflicting files at the path will be replaced. Non-
        conflicting files will be left alone; call `path.remove()` first if you
        really want to replace everything.
        """
        assert path.root in (Root.ABS, Root.OUT, Root.GEN)
        try:
            if makedirs:
                assert "blob" not in os.fspath(path)
                os.makedirs(path, exist_ok=True)
            else:
                os.mkdir(path)
        except FileExistsError:
            if clobber and not stat.S_ISDIR(os.lstat(path).st_mode):
                path.remove()
                os.mkdir(path)
        for (k, v) in self.items():
            v.write_copy(path / k, clobber=clobber)
        return path

    def __truediv__(self, rel):
        """
        Get a path into this tree (which may or may not exist)
        """
        return Path(self, rel)

    def __getitem__(self, rel):
        """
        Get a subtree of this tree.

            tree / "foo" - relative path inside the same tree
            tree["foo"] or tree.get("foo") - standalone subtree

            tree[""] == just returns the tree itself
            tree["a/b"] is the same as tree["a"]["b"]

        Raises FileNotFoundError if the element does not exist.
        """
        out = self
        for part in rel.split("/"):
            if not isinstance(out, Tree) or part not in out._entries:
                raise FileNotFoundError(f"{cas.sig(self)}/{rel}")
            out = out._entries[part]
        return out

    def get(self, name, default=None):
        return self._entries.get(name, default)

    def items(self):
        return self._entries.items()

    def pick(self, *names):
        """
        Return a tree containing a subset of items from this tree.
        """
        return Tree({name: self[name] for name in names})


def _rmtree(path):
    path = os.fspath(path)
    try:
        os.remove(path)
    except PermissionError:
        os.chmod(path, stat.S_IWUSR)
        os.remove(path)
    except IsADirectoryError:
        for name in os.listdir(path):
            _rmtree(os.path.join(path, name))
        os.rmdir(path)
