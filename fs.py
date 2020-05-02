#!/usr/bin/env python3
"""
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
import shutil
import util
import enum
import memo
import posixpath
import sig
import os
import context


__ALLOW_GLOBAL_REFS__ = True


class Root(enum.Enum):
    ABS = "abs"  # An absolute path outside of the build tree
    GEN = "gen_root"  # A path from the generated intermediate files root
    OUT = "out_root"  # A path from the output root
    SRC = "src_root"  # A path from the source root


class Path:
    """
  Represents a location on disk, relative to some root.
  *Which* root is chosen is part of the path's hash, but the location
  of the root itself is not.

  The contents of the file referred to by the path (if any) are not
  part of the hash.

  root_dir:
  - "abs": An absolute path outside of the build tree
  - "src": a path from the source root
  - "gen": a path from the build root
  - "out": a path from the output root
  """

    def __init__(self, root: Root, rel=""):
        assert isinstance(root, Root)
        if root is Root.ABS:
            assert posixpath.isabs(rel)
        else:
            assert not posixpath.isabs(rel)
        self._root = root
        self._rel = rel

    def __fspath__(self):
        """Implement the os.PathLike interface"""
        if self._root is Root.ABS:
            return os.path.normpath(self._rel)
        else:
            return os.path.join(
                context.config[self._root.value], os.path.normpath(self._rel)
            )

    def __repr__(self):
        return f"{{{self._root.value}}}/{self._rel}"

    def __truediv__(self, rel):
        return Path(self._root, posixpath.normpath(posixpath.join(self._rel, rel)))

    def __eq__(self, other):
        if self is other:
            return True
        return (
            type(self) == type(other)
            and self._root is other._root
            and self._rel == other._rel
        )

    def __hash__(self):
        return hash((type(self), self._root, self._rel))

    @memo.memoize
    def blob(self):
        """
      Return a blob representing the contents of the file at this path,
      or None if the file does not exist.

      It is an error to mutate the file once blob() has been called.
      """
        if os.path.exists(self):
            return Blob(path=self)
        else:
            return None

    def is_file(self):
        return os.path.isfile(self)

    def is_dir(self):
        return os.path.isdir(self)


abs_root = Path(Root.ABS, "/")
gen_root = Path(Root.GEN, "")
out_root = Path(Root.OUT, "")
src_root = Path(Root.SRC, "")


def blob_dir(content_sig):
    s = content_sig.hash.hex()
    return Path(Root.GEN, "blob") / s[:2] / s[2:]


def output_dir():
    h = context.opt.current_call_hash
    s = str(h.hash.hex())
    return Path(Root.GEN, "memo") / s[:2] / s[2:]


def make_output_dir():
    p = output_dir(h)
    os.path.makedirs(p, exist_ok=True)
    return p


def tree_from_path(path):
    path = os.fspath(path)
    if not os.path.exists(path):
        return None
    if not os.path.isdir(path):
        return Blob(path)
    names = sorted(os.listdir(path))
    return Tree({name: os.path.join(path, name) for name in names})


def checkFileSig(path, expected):
    h = sig.hash_file_contents(path)
    if h != expected:
        raise RuntimeError(f"hash mismatch in file {path}")
    return expected


class Blob:
    """
    Represents a blob of bytes which may be materialized on disk
    somewhere, but the location is not relevant to consumers.

    A blob that is construct from a path will remember the path

    """

    def __init__(self, *, path=None, content_sig=None, bytes=None):
        if path is None and content_sig is None and bytes is None:
            raise ValueError("Blob requires, path, sig, or bytes")
        if bytes:
            if content_sig:
                assert content_sig == sig.of(bytes)
            else:
                content_sig = sig.of(bytes)
        if path:
            if content_sig:
                assert content_sig == sig.hash_file_contents(path)
            else:
                content_sig = sig.hash_file_contents(path)
        self._bytes = bytes
        self._path = path
        self._content_sig = content_sig

    def __ser__(self):
        return self._content_sig.hash

    @classmethod
    def __deser__(cls, cshash):
        return cls(content_sig=sig.Sig(hash=0))

    def path(self):
        if self._path:
            return self._path

        self._path = self._content_sig.get_path()
        if self._path:
            return self._path

        path = blob_dir(self._content_sig)
        if path.is_file():
            assert self._content_sig == sig.hash_file_contents(path)
            self._path = path
            return path
        data = self._bytes or self._content_sig.object()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)
        return path

    def bytes(self):
        return self._content_sig.object()

    def __fspath__(self):
        return self.path().__fspath__()


class Tree:
    def __init__(self, entries=None, path=None):
        if entries is None and path is None:
            raise ValueError("either entries or path must be given")
        # entries: dict of (name, Blob|Tree)
        if entries:
            for (k, v) in entries.items():
                assert type(k) is str
                assert type(v) in (Blob, Tree)
                # TODO: valid path if also provided
        self._entries = entries
        self._path = path

    @util.lazy_attr("_path", None)
    def materialize(self):
        """
        Return path to root of this tree on-disk.
        """
        # TODO: This requires the whole tree to be in-memory.
        #       We could allow leaves to be represented by
        #       their signatures until needed.
        #
        # TODO: If directory is already on disk, validate it
        #       (once) before assuming it's correct. Try to
        #       recreate it if it's corrupt.
        h = hash.hash(self)
        path = gen_root() / "tree" / sig.of(self)
        if os.path.exists(path):
            # assume it's valid
            return path
        else:
            fsentries = {k: v.fspath() for (k, v) in self.entries.items()}
            os.mkdir(fspath)
            try:
                for k in self.entries:
                    target_fspath = fsentries[k]
                    isdir = isinstance(self.entries[k], Blob)
                    # requires Python >=3.8 on Windows
                    os.symlink(
                        target_fspath,
                        os.path.join(fspath, k),
                        target_is_directory=isinstance(self.entries[k], Blob),
                    )
            except:
                shutil.rmtree(fspath, ignore_errors=True)
                raise
            return fspath
