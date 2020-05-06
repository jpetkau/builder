#!/usr/bin/env python3
from functools import wraps
import sys
import os
import posixpath


def decorator(d):
    """
    Helper for writing decorators with optional args.
    
    These are always super confusing piles of nested inner functions, so
    this moves all the confusion to one spot.

        @decorator
        def my_decorator(func, arg1="bar", arg2="foo"):
            def wrapper():
                ...
            return wrapper

        @my_decorator
        def foo(): .. # ok

        @my_decorator(arg2="hi")
        def foo(): ... # ok
    """

    @wraps(d)
    def d_wrapper(*args, **kwargs):
        if len(args) == 1 and not kwargs and callable(args[0]):
            return wraps(args[0])(d(args[0]))

        def partial(f):
            return wraps(f)(d(f, *args, **kwargs))

        return partial

    return d_wrapper


@decorator
def lazy_attr(f, name="", missing=object()):
    """
    Decorator to indicate that an attribute should be computed just
    once and cached (in memory) under the given name.

    This is not part of the heavyweight memo system, just a lightweight
    cache for compute-once attributes.

    If no name is given, it will be the function name suffixed with '_'.
    """
    name = name or "_memo_" + f.__name__

    def wrapper(self):
        v = getattr(self, name, missing)
        if v is missing:
            v = f(self)
            setattr(self, name, v)
        return v

    return wrapper


_trace_indent = 0


def trace(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        global _trace_indent
        print(
            f"{' '*_trace_indent}ENTERING {f.__name__}{args} **{kwargs}",
            file=sys.stderr,
        )
        _trace_indent += 2
        try:
            out = f(*args, **kwargs)
        finally:
            _trace_indent -= 2
            print(
                f"{' '*_trace_indent}LEAVING {f.__name__}{args} **{kwargs} out={out!r}",
                file=sys.stderr,
            )
        return out

    return wrapper


def _err_immutable(self, *args, **kwargs):
    raise TypeError("imdict is immutable")


class imdict(dict):
    """
    Immutable dictionary type
    """

    __slots__ = "__sig__", "__weakref__"

    def __hash__(self):
        return hash(frozenset(self.items()))

    # extra utility methods to make up for missing ones
    # subtracting another dict or iterable removes keys
    def __sub__(self, other):
        my_ks = set(self)
        ks = my_ks - set(other)
        if ks == my_ks:
            return self
        return imdict({k: self[k] for k in ks})

    def __and__(self, other):
        other = set(other)
        return imdict({k: v for (k, v) in self.items() if k in other})

    def updated(self, *args, **kwargs):
        temp = dict(self)
        temp.update(*args, **kwargs)
        return imdict(temp)

    __setitem__ = _err_immutable
    update = _err_immutable
    pop = _err_immutable
    popitem = _err_immutable
    setdefault = _err_immutable


# Hashable misc. struct class until I decide how to do it properly
class Struct:
    def __init__(self, **data):
        self.__dict__.update(data)

    def __repr__(self):
        return "".join([
            "Struct(", *(f"{k}={v!r}" for (k, v) in self.__dict__.items()), ")"
        ])

    def __len__(self):
        return len(self.__dict__)

    def __getitem__(self, key):
        return self.__dict__[key]

    def keys(self):
        return self.__dict__.keys()

if os.name == "nt" and sys.version_info <= (3, 8):
    # work around os.symlink() not working
    import win32file
    import pywintypes

    def symlink(src, dst, target_is_directory=False):
        src = os.fspath(src)
        dst = os.fspath(dst)
        flags = win32file.SYMBOLIC_LINK_FLAG_ALLOW_UNPRIVILEGED_CREATE
        if target_is_directory:
            flags |= win32file.SYMBOLIC_LINK_FLAG_DIRECTORY
        try:
            win32file.CreateSymbolicLink(dst, src, flags)
        except pywintypes.error:
            raise OSError(None, ee.strerror, src, ee.winerror, dst)


else:
    from os import symlink


def makelink(src, dst, target_is_directory=None):
    if target_is_directory is None:
        target_is_directory = os.path.isdir(src)
    if target_is_directory:
        symlink(src, dst, target_is_directory)
    else:
        os.link(src, dst)


# Given multiple lists (e.g. of include paths), combine into a single
# list. Same as set union, except with more predictable ordering.
def merge_lists(*lists):
    if len(lists) == 0:
        return []
    if len(lists) == 1:
        return lists[0]
    merged = {}
    for d in lists:
        merged.update(dict.fromkeys(d, True))
    return list(merged)


def with_ext(name, ext):
    return posixpath.splitext(name)[0] + ext
