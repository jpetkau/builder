"""
Hashed objects
==============

("Sig" / "signature" used because the name "hash" is a Python builtin.)

This implements a content-addressable object store.

Currently it is strict; a lazy store seems worthwhile but that isn't what this is.

It is possible to partially force values. For example, if you have a pair (a,b),
you might want to force just 'a'.

For 'blobs' types, the hash is an actual hash of the bits. For types which can be
serialied to/from a blob, the hash is the blob hash plus some type name.

Three kinds of errors:
1. "internal" errors, e.g. syntax error in C++ code. These are cached like anything else.
2. "external" errors, e.g. some tool had a transient failure. These propagate up but don't cache.
3. panics: build system itself had an error and can't continue.

Can we have values which we know the hash for, but not the rest?
- Yes: that's how e.g. memoized outputs are represented
- So the value cache needs to be able to trace references (or use refcounting) to avoid killing things we need
- We could flag values in the cache as, "parts known to exist" / "parts may be missing / parts known to be missing".
- Anyway for now, assume it's an error if parts are missing.

Encoding types in hashed values
-------------------------------
This is basically the same serializtion problem we have with e.g. pickle().
How do we name types? What does it mean for a type to be the same?
- At least for v1: like pickle, have a limited set of primitives with fixed
  encoding, and compound types have a constructor from these.
- Maybe even use pickle's special methods

Hashing function objects
------------------------
We need to be able to hash function objects for comparisons. So
ideally this would be a hash on the expression tree, normalized
as much as possible to find sharing.

- Hashing by name? No, because we can do a new build with a new function with the same name.
- Hashing by name, plus bit hashes of all source files that might have influenced that name?
  - works, but over-conservative
- Hashing by bytecode and hashes of referenced objects?
  - should work, unfortunately sensitive to Python optimization level.
  - can handle partially-evaluated awaitables and generators, that's cool.
  - expression tree would be better
  - `inspect.getclosurevars()` tells you actual global refs, also captures,
    nice. [But not really: if f() defines g() that accesses stuff, g's refs
    are not visible.
  - but fixable:
        f.__globals__ - globals dict
        f.__globals__["__builtins__"].__dict__ - builtins dict
        f.__code__ - code object
            .co_code - bytecode
            .co_names - referenced globals and builtins
            .co_consts - consts, including sub-code objects
            .co_freevars - names of vars from outer scopes
            .co_cellvars - names of vars used by inner scopes
        f.__closure__ - tuple of cells to outer scopes
            [].cell_contents - closed-over value, ValueError if uninitialized

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

But I don't want to make every list different because that would suck.
You must write your code as if objects never have identity.
- Possible way to enforce this: since we're hashing lists on function
  entry to check memoization, could also intern a canonical instance at
  that time? But Python's weak refs are dumb so might be hard.

Limitations
-----------

storing hashed values:
- first serialize the object to a bit string
- subobjects can be represented by hashes in that bit string
- hash of object is hash of serialized string
but also:
- hash of a string of 0..31 bytes is length followed by those bytes.
- so Sig.bits(b: bytes)==b if len(b) <= 31
deser() is stict here, fully loading recursive objects.

For GC:
- uppercase type codes are all types that contain references.
- for these types, the body is exactly a list of references
  concatenated together.

Variation
=========
- At the lowest level, suppose we hardcode just two cases (using h[0]&64):
  1. byte string not containing references
  2. tuple of N references to other objects
- Then the typed hashers just need to decide which to return
- Fetching can actually get a whole tree of tuples of bytes without looking up types
- Still need to encode types like 'list' etc. somehow
- Useful?

    1. Map from arbitrary types to nested tuples of bytes
    bytes -> bytes
    str -> (b's', utf8)
    list -> (b'l', obj1, obj2, ...)
    tuple -> (b't', obj1, obj2, ...)
    global -> (b'g', module, name)
    2. Hash encodes difference between 'bytes' and any other type.

Getting raw bytes objects
=========================
- Should be able to get the raw bytes of any serialized object as a file;
  otherwise blob system needs to duplicate storage.
- How about: *if* we have them in a file, other places can ask for it?
- Makes life harder if serialized form of 'bytes' has any prefix on it.

Python is stupid
================
- list/dict can't be the target of a weakref, nor can you add slots to them,
  nor can they be keys in dictionaries. So how do make a table that tracks
  their hashes?
- could make a table from id->hash, but since there are no weakrefs, this
  keeps the objects alive. Sucky.
- could make a table from id->hash that *doesn't* keep the objects alive. How
  to detect if it's invalid when we get some random new object with the same id?
  answer: we can't.
- could wrap everything everywhere in user-defined types. Eew.
- could keep the objects alive, but occasionally scan for objects with refcount==1
"""
from typing import List
import types
import hashlib
import util
import sys


_hash_store = {}


class Sig:
    """
    The content hash of some object.

    This is just a dumb dataclass to help avoid confusion with `bytes`
    """
    __slots__ = ("value",)

    def __init__(self, *, hash):
        assert type(hash) is bytes
        assert len(hash) >= 1 and len(hash) <= 32
        assert hash[0] & 128 or hash[0]==len(hash)
        self.value = hash

    def __repr__(self):
        return '{' + self.value.hex() + '}'

    def __eq__(self, other):
        return self is other or (type(other) is Sig and self.value == other.value)

    def __hash__(self):
        return self.value.__hash__()

    @property
    def __sig__(self):
        """
        Sig itself is not a hashable object; instead we make sig.of(x) idempotent.
        This turns out to be very convenient since you can use a signature as a
        stand-in for the object when computing other hashes.

        When we want to hash to signatures into a compound objects, use `.value: bytes`
        instead.
        """
        return self

    @staticmethod
    def bits(b: bytes) -> 'Sig':
        if len(b) >= 32:
            out = hashlib.sha256(b).digest()
            out = bytes([out[0] | 128]) + out[1:]
            return Sig(hash=out)
        else:
            return Sig(hash=bytes([len(b) + 1]) + b)

    def object(self):
        """
        Find an object from its hash
        """
        return deser(self._get_serialized())


    def _is_short(self):
        return self.value[0] <= 32

    def _get_serialized(self):
        """
        Get the uparsed bit string corresponding to a hash
        """
        h = self.value
        n = h[0]
        if n <= 32:
            # short string is encoded in the hash itself
            assert n == len(h)
            return h[1:]
        else:
            assert len(h) == 32
            return _hash_store[h]


def of(x):
    """
    Return the signature of some Python object
    """
    h = getattr(x, "__sig__", None)
    if h:
        return h
    b = ser(x)
    h = Sig.bits(b)
    if (h.value[0] & 128):
        _hash_store[h.value] = b
        try:
            # remember hash for faster access later
            # would be nice to detect mutations
            x.__sig__ = h
        except AttributeError:
            pass
    return h


def hcat(*sigs: Sig) -> bytes:
    # concatenate a bunch of hashes
    for sig in sigs:
        assert isinstance(sig, Sig)
    return b"".join(sig.value for sig in sigs)


# inverse of hcat
def hsplit(b: bytes) -> List[Sig]:
    i = 0
    out = []
    while i < len(b):
        n = b[i]
        if n == 0:
            continue  # pad byte
        if n & 128:
            h = b[i : i + 32]
            out.append(Sig(hash=h))
            i += 32
        else:
            h = b[i : i + n]
            out.append(Sig(hash=h))
            i += n
    return out


def ser_bytes(x):
    return x


def deser_bytes(b):
    return b


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
    # kind of tree or linked list
    return hcat(*(of(v) for v in x))


def deser_list(b):
    hs = hsplit(b)
    return [v.object() for v in hs]


ser_tuple = ser_list


def deser_tuple(b):
    return tuple(deser_list(b))


def ser_dict(x):
    return ser_list([list(x.keys()), list(x.values())])


def deser_dict(b):
    ks, vs = deser_list(b)
    assert len(ks) == len(vs)
    return dict(zip(ks, vs))


def deser_false(b):
    assert b == b""
    return False


def deser_true(b):
    assert b == b""
    return True


class Global:
    # reference to value accessible in some module globals
    __slots__ = ["module", "name"]

    def __init__(self, module, name):
        self.module = module
        self.name = name

    def __repr__(self):
        return f"Global({self.module}.{self.name})"


def find_global(obj):
    # if the given object is a global in its module,
    # serialize it by name instead of value
    # TODO: need a way to distinguish sys/non-sys modules
    module = getattr(obj, "__module__", None)
    name = getattr(obj, "__name__", None)
    if module and name and sys.modules[module].__dict__[name] is obj:
        return Global(module, name)
    return None


def ser_global(u):
    return hcat(of(u.module), of(u.name))


def deser_global(b):
    m, n = hsplit(b)
    return sys.modules[m.object()].__dict__[n.object()]


def ser_function(f):
    closed = None
    if f.__closure__ is not None:
        closed = tuple(_name_or_val(c.cell_contents) for c in f.__closure__)
    return hcat(
        of(closed),
        *[of(part) for part in _code_to_tuple(f.__code__, f.__globals__)],
    )


def _name_or_val(v):
    if type(v) in (types.ModuleType,):
        return Global(v.__name__)
    else:
        return v


def ser_class(v):
    g = find_global(type(v))
    if not g:
        raise TypeError(f"Don't know how to serialize {v}")
    return ser_list([g, list(v.__dict__.keys()), list(v.__dict__.values())])


def deser_class(b):
    ty, ks, vs = deser_list(b)
    assert len(ks) == len(vs)
    out = object.__new__(ty)
    out.__dict__.update(**dict(zip(ks, vs)))
    return out


def _lookup_global(name, globals):
    try:
        v = globals[name]
    except KeyError:
        # builtin or missing; in either case, just hash
        # the name.
        return Global(name)
    else:
        return _name_or_val(v)

# return a serializable tuple for some code under the given globals
# this is wrong! because `inspect` is wrong.
# co_names isn't just used for globals. It's also:
# - LOAD_METHOD
# - {LOAD,STORE,DELETE}_ATTR
# - IMPORT_NAME (dotted and non-dotted module names)
#       [don't care; disallow imports]
#
# so maybe the fix is magic ref-finding magic?
#   ideally these are the same:
#       import a.b
#       def foo(): return a.b
#
#       from a import b
#       def foo(): return b
#
# the _ATTR-style refs can be filtered out by just finding those refs.
# this produce a conservative list of bindings for dotted names, since
# we always ref the top object, but that's ok.
#
# could do a fancier thing doing simple dataflow, find actual module refs
def _code_to_tuple(code, globals):
    gs = tuple(_lookup_global(name, globals) for name in code.co_names)
    ks = tuple(
        (_ser_code(k, globals) if type(k) is types.CodeType else k)
        for k in code.co_consts
    )
    return (code.co_code, gs, ks)


deserializers = {
    b"0": deser_false,
    b"1": deser_true,
    b"b": deser_bytes,
    b"i": deser_int,
    b"s": deser_str,
    b"L": deser_list,
    b"T": deser_tuple,
    b"D": deser_dict,
    b"G": deser_global,
    b"C": deser_class
}

serializers = {
    bytes: (b"b", ser_bytes),
    int: (b"i", ser_int),
    str: (b"s", ser_str),
    list: (b"L", ser_list),
    tuple: (b"T", ser_tuple),
    dict: (b"D", ser_dict),
    types.FunctionType: (b"F", ser_function),
    Global: (b"G", ser_global),
}


def ser(x):
    """
    Convert an object to a sized `bytes` representation.
    """
    if x is None:
        return b""
    if x is True:
        return b"1"
    if x is False:
        return b"0"
    try:
        t, tser = serializers[type(x)]
    except KeyError:
        ...
    else:
        return t + tser(x)

    g = find_global(x)
    if g:
        return ser(g)

    g = find_global(type(x))
    if g:
        return b'C' + ser_class(x)

def deser(b):
    if b == b"":
        return None
    t, rest = b[0:1], b[1:]
    return deserializers[b[0:1]](b[1:])


def _byte_length(i: int):
    if i == 0:
        return 0
    elif i > 0:
        return i.bit_length() // 8 + 1
    else:
        return (i + 1).bit_length() // 8 + 1


def file_contents(fspath: str) -> bytes:
    BLOCKSIZE = 65536
    hasher = hashlib.sha256()
    data = f.read(BLOCKSIZE)
    if len(data) < BLOCKSIZE:
        return Sig.bits(data)
    with open(fspath, "rb") as f:
        while True:
            data = f.read(BLOCKSIZE)
            if not data:
                break
            hasher.update(data)
    out = hasher.digest()
    out = bytes([out[0] | 128]) + out[1:]
    return out
