#!/usr/bin/env python3
from functools import wraps
import sys


def decorator(d):
    """
    Helper for writing decorators with optional args. These are
    always super piles of nested inner functions, so this moves
    all the confusion to one spot.

        @decorator
        def my_decorator(func, arg1="bar", arg2="foo"):
            @wraps(func)
            def wrapper(): ...
            return wrapper

        @my_decorator
        def foo(): .. # ok

        @my_decorator(arg2="hi")
        def foo(): ... # ok
    """

    @wraps(d)
    def d_wrapper(*args, **kwargs):
        if len(args) == 1 and not kwargs and callable(args[0]):
            return d(args[0])
        else:

            def partial(f):
                return d(f, *args, **kwargs)

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

    @wraps(f)
    def wrapper(self):
        v = getattr(self, name, missing)
        if v is missing:
            v = f(self)
            setattr(self, name, v)
        return v

    return wrapper


# Hashable misc. struct class until I decide how to do it properly
class Struct:
    def __init__(self, **data):
        self.__dict__.update(data)

    def __repr__(self):
        return "".join(
            "Struct(", *(f"{k}={v!r}" for (k, v) in self.__dict__.items()), ")"
        )


def trace(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        print(f"ENTERING {f.__name__}{args} **{kwargs}", file=sys.stderr)
        out = f(*args, **kwargs)
        print(f"LEAVING {f.__name__}{args} **{kwargs} out={out!r}", file=sys.stderr)
        return out

    return wrapper
