"""
TODO: Move CasDB into fs_sig_cache and give them a better name.
- That module then deals exclusively with bytes <-> file system.
- This module then defines the hashing and serialization algos and provides
the CAS interface.

Content addressable store
=========================

("Sig" / "signature" used because the name "hash" is a Python builtin.)

This implements a content-addressable object store.

For 'bytes' types, the hash is an actual hash of the bits. For all other types,
the hash is made by converting the object to a state tuple `(type, obj1, obj2,
...)`, concatenating the hashes of all the subobjects, and hashing that.

This structure means:
- We could lazily decode an object, though that isn't done yet.
- We can trace references for garbage collection without decoding the objects,
  just following hashes.


FS hash cache
-------------
To avoid re-hashing large input files over and over, we keep a db of file
hsahes.


Mode bits (+x)
--------------
Logically, the CAS store doesn't care about mode bits on files (st_mode). The
hash is only of the contents.

But we want to be able to hand out (read-only) paths to blobs, and clients might
need those with +x set or not.

So: `store_file()` and `blob_fspath()` take mode bits, and store the file at a
different path for different modes.

The cas still doesn't *track* modes; this just makes it possible for a caller
that *does* track modes (like fs.py with Blob vs. XBlob) to get files with
desired mode bits without incurring extra copies.


Mutable objects
---------------
It would be really nice if we could reliably ensure immutability. Unfortunately
Python makes this hard.

Basically just try not to mutate hashed things or you will be sad.


Hashing function objects
------------------------
We need to be able to hash function objects for comparisons. So ideally this
would be a hash on the expression tree, normalized as much as possible to find
sharing.

- Hashing by name? No, because we can do a new build with a new function with
  the same name.
- Hashing by name, plus bit hashes of all source files that might have
  influenced that name?
  - works, but over-conservative
- Hashing by bytecode and hashes of referenced objects?
  - should work, unfortunately sensitive to Python optimization level.
  - can handle partially-evaluated awaitables and generators, that's cool.
  - expression tree would be better
  - `inspect.getclosurevars()` tells you actual global refs, also captures,
    nice. [But not really: if f() defines g() that accesses stuff, g's refs are
    not visible.
  - but fixable: f.__globals__ - globals dict
        f.__globals__["__builtins__"].__dict__ - builtins dict f.__code__ - code
        object .co_code - bytecode .co_names - referenced globals and builtins
        .co_consts - consts, including sub-code objects .co_freevars - names of
        vars from outer scopes .co_cellvars - names of vars used by inner scopes
        f.__closure__ - tuple of cells to outer scopes [].cell_contents -
        closed-over value, ValueError if uninitialized


Probably not a good idea to deserialize function or class definitions even if
it's possible. But we do want to be able to restore *instances* of user-defined
types.

Assuming the contents match, does it matter if the definitions differ? But could
hash the definition, and then for deserialization, do a broader globals search
and then only accept the global if the definitions match?


Problems
--------
Object identity: you can write Python code like

    a = []  # or object() or whatever
    b = []
    def foo(x: List):
        if x is a:
            do_this()
        else:
            do_that()

But I don't want to make every list different because that would suck. You must
write your code as if objects never have identity.
- Possible way to enforce this: since we're hashing lists on function entry to
  check memoization, could also intern a canonical instance at that time? But
  Python's weak refs are dumb so might be hard.

Ah don't want to do that anyway. It's too hard to avoid mutating things in
python, will be constant source of bugs. Just have to do extra hashing on
mutable types. Wait for non-Python version for efficiency.

Limitations
-----------

storing hashed values:
- first serialize the object to a bit string
- subobjects can be represented by hashes in that bit string
- hash of object is hash of serialized string but also:
- hash of a string of 0..31 bytes is length followed by those bytes.
- so Sig.bits(b: bytes)==b if len(b) <= 31 deser() is stict here, fully loading
  recursive objects.

For GC:
- uppercase type codes are all types that contain references.
- for these types, the body is exactly a list of references concatenated
  together.

Variation
=========
- At the lowest level, suppose we hardcode just two cases (using h[0]&64):
  1. byte string not containing references
  2. tuple of N references to other objects
- Then the typed hashers just need to decide which to return
- Fetching can actually get a whole tree of tuples of bytes without looking up
  types
- Still need to encode types like 'list' etc. somehow
- Useful?

    1. Map from arbitrary types to nested tuples of bytes bytes -> bytes str ->
       (b's', utf8) list -> (b'l', obj1, obj2, ...) tuple -> (b't', obj1, obj2,
       ...) global -> (b'g', module, name)
    2. Hash encodes difference between 'bytes' and any other type.

Getting raw bytes objects
=========================
- Should be able to get the raw bytes of any serialized object as a file;
  otherwise blob system needs to duplicate storage.
- How about: *if* we have them in a file, other places can ask for it?
- Makes life harder if serialized form of 'bytes' has any prefix on it.

Python is stupid
================
- list/dict can't be the target of a weakref, nor can you add slots to them, nor
  can they be keys in dictionaries. So how do make a table that tracks their
  hashes?
- could make a table from id->hash, but since there are no weakrefs, this keeps
  the objects alive. Sucky.
- could make a table from id->hash that *doesn't* keep the objects alive. How to
  detect if it's invalid when we get some random new object with the same id?
  answer: we can't.
- could wrap everything everywhere in user-defined types. Eew.
- could keep the objects alive, but occasionally scan for objects with
  refcount==1
"""
from typing import List
import dbm, hashlib, logging, os, shutil, stat, sys, types
import all_globals, config, fs_sig_cache, util


logger = logging.getLogger(__name__)

HFLAG_LONG = 128
HFLAG_COMPOUND = 64
HFLAG_MASK = 63
HASH_SIZE = 32

_cas_db = None
_cas_root = None


class CasDB:
    def __init__(self, cas_root):
        self._db = dbm.open(os.path.join(cas_root, "cas_db"), "c")
        self._cache = fs_sig_cache.FsSigCache(
            os.path.join(cas_root, "fs_sig_db"), hasher=_hash_file
        )

    def close(self):
        self._db.close()
        self._cache.close()

    def __setitem__(self, h, data):
        """
        Store raw byte contents of the given h.
        """
        assert isinstance(h, bytes)
        assert isinstance(data, bytes)
        db = self._db
        if (h[0] & HFLAG_LONG) and h not in db:
            db[h] = data
        else:
            # data encoded in h or already stored, nothing to do
            ...

        # TODO: can't store in a file here because we don't know the mode,
        # but should check if file exists. Doing a stat() call every time
        # we store some bytes would be expensive, though, so need an in-memory
        # cache.
        """
            # store blobs in files since we usually need them there anyway
            p = _blob_fspath(sig)
            if os.path.isfile(p):
                return
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "wb") as f:
                f.write(data)
        """

    def __getitem__(self, h):
        n = h[0]
        if n & HFLAG_LONG:
            # stored in cache
            assert len(h) == HASH_SIZE, h
            return self._db[h]
        else:
            # short string is encoded in the hash itself
            assert (n & HFLAG_MASK) == len(h)
            return h[1:]

    def __contains__(self, h):
        return (h[0] & HFLAG_LONG) == 0 or h in self._db

    def file_hash(self, path, *, st=None) -> bytes:
        return self._cache.hash(path, st)


class Sig:
    """
    The content hash of some object.
    """

    __slots__ = ("hash",)

    def __init__(self, *, hash):
        assert type(hash) is bytes
        assert len(hash) >= 1 and len(hash) <= HASH_SIZE
        assert (hash[0] & HFLAG_LONG) or (hash[0] & HFLAG_MASK) == len(hash)
        self.hash = hash

    def __repr__(self):
        return "{" + self.hash.hex() + "}"

    def __eq__(self, other):
        return self is other or (type(other) is Sig and self.hash == other.hash)

    def __hash__(self):
        return self.hash.__hash__()

    def object(self):
        """
        Find an object from its hash
        """
        bits = self._get_bits()
        if self.is_bytes():
            return bits

        sub_objs = [h.object() for h in hsplit(bits)]
        first = sub_objs[0]
        if type(first) is bytes:
            return deserializers[first](*sub_objs[1:])
        elif hasattr(first, "__deser__"):
            return first.__deser__(*sub_objs[1:])
        else:
            return deser_instance(*sub_objs)

    def is_bytes(self):
        return (self.hash[0] & HFLAG_COMPOUND) == 0

    def is_short(self):
        """
        Return true for 'short' hashes, where the full serialization of
        the object is smaller than a hash digest so we just call it the
        hash.
        """
        return (self.hash[0] & HFLAG_LONG) != 0

    def _get_bits(self):
        """
        Get the uparsed bit string corresponding to a hash
        """
        try:
            return _cas_db[self.hash]
        except KeyError:
            # maybe it's in a file?
            if self.is_bytes():
                p = self.get_fspath(kind="blob")
                if not os.path.exists(p):
                    p = self.get_fspath(kind="xblob")
                if os.path.exists(p):
                    with open(p, "rb") as f:
                        return f.read()
            raise

    # return path where blob or tree with the given sig should be materialized,
    # relative to cas root
    def get_relpath(self, *, kind=None, st_mode=None):
        if kind is None and st_mode is None:
            raise ValueError(
                "either kind or st_mode must be specified for object_fspath"
            )

        if st_mode:
            if stat.S_ISDIR(st_mode):
                mkind = "tree"
            elif stat.S_IXUSR & st_mode:
                mkind = "xblob"
            else:
                mkind = "blob"
            # validate that st_mode and kind match
            if kind is not None and kind != mkind:
                raise ValueError(
                    f"wrong kind {kind} for st_mode 0{st_mode:o}: should be {mkind}"
                )
            kind = mkind

        if (kind == "tree") == (self.is_bytes()):
            raise ValueError(
                f"wrong kind {kind} for {self} (is_bytes={self.is_bytes()})"
            )

        s = self.hash.hex()
        return "/".join((kind, s[:2], s[2:]))

    def get_fspath(self, *, kind=None, st_mode=None):
        """
        Get a path of a file containing to this hash's object, if available.

        Requires that this hash represents a bytes type.

        Returns None if `create` is False and the contents are not available in
        a file (e.g. they're stored in a DB or memory or whatever.)
        """
        return os.path.normpath(
            os.path.join(_cas_root, self.get_relpath(kind=kind, st_mode=st_mode))
        )


class WithSig:
    """
    A class which hashes as the given signature:

        sig(WithSig(sig(x))) == sig(x)

    This is used when you have the signature of some object, but want it
    to hash as of it were the object itself, without having to produce the
    object itself.
    """

    __slots__ = ("__sig__",)

    def __init__(self, sig):
        self.__sig__ = sig


def store(x):
    return sig(x, store=True)


# @util.trace
def sig(x, store=False):
    """
    Return the signature of some Python object
    """

    # reuse existing sig if possible
    try:
        s = x.__sig__
    except AttributeError:
        s = None
    else:
        if s and (not store or s.hash in _cas_db):
            return s

    if type(x) is bytes:
        b, h = x, hash_bytes(x)
    else:
        key, parts = _ser(x)
        if type(parts) is bytes:
            parts = (parts,)
        assert type(parts) is tuple
        b, h = _hcat(sig(key, store), *[sig(p, store) for p in parts])

    if store:
        _cas_db[h.hash] = b

    assert s is None or s == h
    return h


def _ser(x):
    # return key, parts
    assert type(x) is not bytes

    if x is False:
        return b"f", ()
    if x is True:
        return b"t", ()
    if x is Global:
        return b"G", ()

    g = find_global(x)
    if g:
        # serialize reference to some global variable
        return Global, g.__ser__()

    ty = type(x)
    if ty in serializers:
        key, tser = serializers[ty]
        return key, tser(x)
    if hasattr(x, "__ser__"):
        return ty, x.__ser__()

    g = find_global(ty)
    if g:
        # serialize instance of class which we can find ref to
        return ty, ser_instance(x)

    raise TypeError(f"Don't know how to serialize {x}")


def _hcat(*sigs: Sig) -> bytes:
    # concatenate a bunch of signatures into a bit sequence
    for sig in sigs:
        assert isinstance(sig, Sig)
    b = b"".join(sig.hash for sig in sigs)
    return b, hash_bytes(b, HFLAG_COMPOUND)


# inverse of _hcat
def hsplit(b: bytes) -> List[Sig]:
    i = 0
    out = []
    while i < len(b):
        b0 = b[i]
        if b0 == 0:
            continue  # pad byte
        if b0 & 128:
            n = HASH_SIZE
        else:
            n = b0 & HFLAG_MASK
        h = b[i : i + n]
        out.append(Sig(hash=h))
        i += n
    return out


def ser_unit(_):
    # serializer for a type with a single well-known instance;
    # type already identifies the instance.
    return ()


def deser_unit(k):
    # serializer for a type with a single well-known instance;
    # just return the instance.
    def deser():
        return k

    return deser


def ser_int(x):
    return x.to_bytes(_byte_length(x), "little", signed=True)


def deser_int(b):
    return int.from_bytes(b, "little", signed=True)


def ser_str(x):
    return x.encode("utf-8")


def deser_str(b):
    return b.decode("utf-8")


def ser_list(x):
    # this format is arbitrarily large; better to use some
    # kind of tree? or rely on the underlying bytes for that optimization?
    return tuple(x)


def deser_list(*xs):
    return list(xs)


ser_tuple = ser_list


def deser_tuple(*xs):
    return xs


def ser_dict(x):
    # must sort so insertion order doesn't affect hash
    keys = sorted(x.keys())
    return keys, [x[k] for k in keys]


def deser_dict(ks, vs):
    assert len(ks) == len(vs)
    return util.imdict(zip(ks, vs))


def ser_sig(x):
    return x.hash


def deser_sig(hash):
    return Sig(hash=hash)


"""
Class instances serialize as (type, dict-keys, dict-values).

The 'type' part will typically be found as a global for deser.
"""


def ser_instance(v):
    assert not isinstance(v, types.ModuleType)
    return ser_dict(v.__dict__)


def deser_instance(ty, ks, vs):
    assert len(ks) == len(vs)
    out = object.__new__(ty)
    out.__dict__.update(**dict(zip(ks, vs)))
    return out


"""
Serializing globals

As in pickle, we can serialize many top-level objects by just recording their
module and name, and expecting to find the same object later for deserialization
or signature comparison.

Pickle has a difference in that they *want* to recover the same-named object
even after it has changed, to support versioning, while we ideally would
never do that.

So we only do this for names that are:
- part of Python itself
- part of the core logic

The implementation is:
- If we couldn't serialize an object some other way, we try to find it as
  a global. We don't look everywhere; currently we require it to match by
  module and name.

- Better: import an explicit list of modules and generate a reverse mapping
  that doesn't need __module__ or __name__)

- Instances of Global represents found globals; it serializes as an
  object instance, and deserializes by looking up the name.

- The single "Global" itself has special-case handling.
"""


class Global:
    # reference to value accessible in some module globals
    __slots__ = ["module", "name"]

    def __init__(self, module, name):
        assert type(module) is str
        assert type(name) is str, name
        self.module = module
        self.name = name

    def __repr__(self):
        return f"Global({self.module}.{self.name})"

    def __ser__(self):
        return bytes(self.module, "utf8"), bytes(self.name, "utf-8")

    @staticmethod
    def __deser__(module, name):
        return sys.modules[str(module, "utf8")].__dict__[str(name, "utf8")]


def find_global(obj):
    # if the given object is a global in its module,
    # serialize it by name instead of value
    module = getattr(obj, "__module__", None)
    if module is None:
        return None
    if module not in all_globals.valid_globals and not sys.modules[module].__dict__.get(
        "__ALLOW_GLOBAL_REFS__", False
    ):
        return None
    name = getattr(obj, "__name__", None)
    if name is None:
        return None
    if sys.modules[module].__dict__.get(name, None) is not obj:
        return None
    return Global(module, name)


def ser_module(obj):
    return bytes(obj.__name__, "utf8")


def deser_module(name):
    return sys.modules[str(name, "utf8")]


def ser_function(f):
    cells = ()
    if f.__closure__:
        cells = tuple(c.cell_contents for c in f.__closure__)
    names = _code_names(f.__code__)
    return (cells, f.__code__, *(_lookup_global(name, f.__globals__) for name in names))


def ser_code(code):
    return (
        code.co_argcount,
        code.co_cellvars,
        code.co_code,
        code.co_consts,
        code.co_flags,
        code.co_freevars,
        code.co_kwonlyargcount,
        code.co_varnames,
    )


# Used when `name` was used in some function with env `globals`.
def _lookup_global(name, globals):
    assert type(name) is str
    try:
        v = globals[name]
    except KeyError:
        # builtin or missing; in either case, just hash
        # the name.
        return Global("", name)
    else:
        return v


# return list of globals names referenced from some code,
# including in nested code blocks.
#
# this is wrong! because `inspect` is wrong.
# co_names isn't just used for globals. It's also:
#
# - LOAD_METHOD
# - {LOAD,STORE,DELETE}_ATTR
# - IMPORT_NAME (dotted and non-dotted module names)
#       [don't care; disallow imports]
#
# the _ATTR-style refs can be filtered out by just finding those refs.
# this produce a conservative list of bindings for dotted names, since
# we always ref the top object, but that's ok.
def _code_names(code):
    # find list of global names possibly referenced by some code
    # in original order (because that matters) but with nesting flattened
    # (because that can be hashed from the code itself).
    names = [*code.co_names]
    for k in code.co_consts:
        if type(k) is types.CodeType:
            names.extend(_code_names(k))
    return names


serializers = {
    type(None): (b"", ser_unit),
    int: (b"i", ser_int),
    str: (b"s", ser_str),
    list: (b"L", ser_list),
    tuple: (b"T", ser_tuple),
    dict: (b"D", ser_dict),
    util.imdict: (b"D", ser_dict),
    Sig: (b"S", ser_sig),
    types.ModuleType: (b"M", ser_module),
    types.FunctionType: (b"F", ser_function),
    types.CodeType: (b"FC", ser_code),
    logging.Logger: (b"", ser_unit),  # treat loggers as None
}


deserializers = {
    b"": deser_unit(None),
    b"f": deser_unit(False),
    b"t": deser_unit(True),
    b"G": deser_unit(Global),
    b"i": deser_int,
    b"s": deser_str,
    b"L": deser_list,
    b"T": deser_tuple,
    b"D": deser_dict,
    b"S": deser_sig,
    b"C": deser_instance,
}


def _byte_length(i: int):
    if i == 0:
        return 0
    elif i > 0:
        return i.bit_length() // 8 + 1
    else:
        return (i + 1).bit_length() // 8 + 1


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
    return Sig(hash=bytes(h))


# raw hasher
def _hash_file(fspath) -> bytes:
    with open(fspath, "rb") as f:
        return hash_byte_stream(f).hash


# equivalent to store(read(file)), but does a copy instead of read/write
def store_file(path, st=None) -> Sig:
    path = os.fspath(path)
    if st is None:
        st = os.stat(path)
    sig = Sig(hash=_cas_db.file_hash(path, st=st))
    dst = sig.get_fspath(st_mode=st.st_mode)
    if not os.path.exists(dst):
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copyfile(path, dst)
    return sig


def checkFileSig(path, expected):
    h = _hash_file(path)
    if h != expected.hash:
        raise RuntimeError(f"hash mismatch in file {path}")
    return expected


@config.oninit
def init(cas_root, **_):
    global _cas_root
    global _cas_db

    os.makedirs(cas_root, exist_ok=True)
    _cas_root = cas_root
    _cas_db = CasDB(cas_root)
    return _cas_db
