#!/usr/bin/env python3
"""
call tree:
    bin -> lib -> compile -> tool

bin wants to know if it needs rebuild, so it has to get
hash of lib.
this works because lib is memoized
in fact memoization is all we need: even without laziness
everything works? maybe?

Yes if targets are actually defined like functions, e.g.

    def my_cxx_lib():
        return cxx_lib(...)

Ok, so original motivation for laziness was 'target output file':
- some way of referring to the output of a target so we can pass it around
- why does that need laziness? Maybe it doesn't?

...

`Lazy` represents a future-style view of a lazy value.

e.g. for `bool` it is a value that will eventually be true or false, but may not
be resolved yet.

Internally it stores a thunk which should be evaluated to get the value.

what can you do with a value?
- access properties and methods. In general, this will just immediately return a
  lazy wrapper.
- if it's possible to immediately resolve a value (or barf), then that is what
  happens.
- force it. This fully resolves value to a non-lazy head type.
- get a strong hash of it (which may require resolving it)
- store the hash (and its children) in the cache

It is possible to partially force values. For example, if you have a pair (a,b),
you might want to force just 'a'.

Errors
======
Values act like futures, so if evaluating a value throws an exception, that
exception is stored and re-thrown by anyone who tries to force the value.

Three kinds of errors:
1. build errors, e.g. syntax error in C++ code. These are cached like anything
   else. Functions must throw BuildError (optionally wrapping some other
   exception) to get this behavior.
2. "external" errors, e.g. some tool had a transient failure. These propagate up
   but don't cache. They may or may not abort a build.
3. panics: build system itself had an error and can't continue.

Can we have values which we know the hash for, but not the rest?
- Yes: that's how e.g. memoized outputs are represented
- So the value cache needs to be able to trace references (or use refcounting)
  to avoid killing things we need
- We could flag values in the cache as, "parts known to exist" / "parts may be
  missing / parts known to be missing".
- Anyway for now, assume it's an error if parts are missing.

Encoding types in hashed values
-------------------------------
This is basically the same serializtion problem we have with e.g. pickle(). How
do we name types? What does it mean for a type to be the same?
- At least for v1: like pickle, have a limited set of primitives with fixed
  encoding.

Limitations
-----------

Python statements can force a value early:

    [x for x in thing] -- depends on length of thing
    (x for x in thing) -- doesn't, but we can't do len() any more either.
    list(x for x in thing) -- only works if we wrap 'list', which may be a bad idea
    List(x for x in thing) -- this works
"""
import sig
import context
import logging
import util

logger = logging.getLogger(__name__)

_memo_store = {}


# get memoized value without calling f
# raises KeyError if there is no memoized value
def get(f, *args, **kwargs):
    arg_sig = sig.of((f, args, kwargs))
    return _memo_store[arg_sig].object()


@util.decorator
def memoize(f, sig_value=None):
    """
    Mark a function as part of the heavyweight memo system

    sig_value, if not None, is a fixed Sig to use for f itself.
    """
    f_sig = sig_value or sig.of(f)

    @util.wraps(f)
    def wrapper(*args, **kwargs):
        arg_sig = sig.of((f_sig, args, kwargs))
        res_sig = _memo_store.get(arg_sig, None)
        logger.debug("in memo for %s, arg_sig=%s, res_sig=%s", f, arg_sig, res_sig)
        if res_sig is None:
            with context.options(current_call_hash=arg_sig):
                v = f(*args, **kwargs)
            vs = sig.of(v)
            _memo_store[arg_sig] = vs
            logger.debug("_memo_store[%s] = %s", arg_sig, vs)
            return v
        else:
            return res_sig.object()

    assert sig_value is None or isinstance(sig_value, sig.Sig)
    wrapper.__sig__ = sig_value or sig.of(f)
    return wrapper
