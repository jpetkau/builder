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

Errors
======

Three kinds of errors:
1. build errors, e.g. syntax error in C++ code. These are cached like anything
   else. Functions must throw BuildError (optionally wrapping some other
   exception) to get this behavior.
2. "external" errors, e.g. some tool had a transient failure. These propagate up
   but don't cache. They may or may not abort a build.
3. panics: build system itself had an error and can't continue.

Can we have values which we know the hash for, but not the contents?
- Yes: that's how e.g. memoized outputs are represented
- So the value cache needs to be able to trace references (or use refcounting)
  to avoid killing things we need
- We could flag values in the cache as, "parts known to exist" / "parts may be
  missing / parts known to be missing".
- Anyway for now, assume it's an error if parts are missing.

Encoding types in hashed values
-------------------------------
This is basically the same serializtion problem we have with e.g. pickle(). How
do we name types? What does it mean for a type to be the "same"?
- At least for v1: like pickle, have a limited set of primitives with fixed
  encoding.
"""
import dbm, logging, os
import cas, config, context, util


logger = logging.getLogger(__name__)


_memo_store = None
_trace = None  # list of memo checks for unit tests


def set_trace(obj=None):
    global _trace
    _trace = obj


@config.oninit
def init(cas_root, **_):
    global _memo_store
    os.makedirs(cas_root, exist_ok=True)
    _memo_store = dbm.open(os.path.join(cas_root, "memo_db"), "c")
    return _memo_store


def put_memo(arg_sig, v_sig):
    assert isinstance(arg_sig, cas.Sig)
    assert isinstance(v_sig, cas.Sig)
    logger.debug("_memo_store[%s] = %s", arg_sig, v_sig)
    _memo_store[arg_sig.hash] = v_sig.hash


def get_memo(arg_sig):
    h = _memo_store.get(arg_sig.hash)
    if h is None:
        return None
    return cas.Sig(hash=h)


# get memoized value without calling f
# raises KeyError if there is no memoized value
def get(f, *args, **kwargs):
    arg_sig = cas.sig((f, args, kwargs))
    return get_memo(arg_sig).object()


def record_access(*key):
    _access_list.append(key)


@util.decorator
class memoize:
    def __init__(self, func, sig_value=None):
        """
        Mark a function as part of the heavyweight memo system

        sig_value, if not None, is a fixed Sig to use for f itself.
        """
        self._func = func
        self._sig = sig_value

    @property
    @util.lazy_attr("_sig", None)
    def __sig__(self):
        return cas.sig(self._func)

    def __repr__(self):
        return f"{self._func.__name__}:{cas.sig(self._func)}"

    def __call__(self, *args, **kwargs):
        f = self._func
        arg_sig = cas.sig((self, args, kwargs))
        res_sig = get_memo(arg_sig)
        logger.debug("in memo for %s, arg_sig=%s, res_sig=%s", f, arg_sig, res_sig)
        logger.debug("  self.sig=%s", cas.sig(self))
        logger.debug("     f.sig=%s", cas.sig(f))
        logger.debug("  args.sig=%s", [cas.sig(a) for a in args])
        logger.debug("kwargs.sig=%s", cas.sig(kwargs))
        logger.debug("      args=%s", args)
        if res_sig is None:
            if _trace is not None:
                _trace.append(("miss", f.__name__, arg_sig, None))
            with context.options(current_call_hash=arg_sig):
                logger.debug(
                    f"memo calling {f}: no memo for sig {arg_sig} of {(self, args, kwargs)}"
                )
                res = f(*args, **kwargs)
            res_sig = cas.store(res)
            put_memo(arg_sig, res_sig)
            if _trace is not None:
                _trace.append(("store", f.__name__, arg_sig, res_sig))
            return res
        else:
            if _trace is not None:
                _trace.append(("hit", f.__name__, arg_sig, res_sig))
            return res_sig.object()

        assert sig_value is None or isinstance(sig_value, cas.Sig)
        wrapper.__sig__ = sig_value or cas.sig(f)
        return wrapper


def trace_access(*accesses):
    # keys are tuples of:
    #   (func_obj, args, kwargs); kwargs is in args as an imdict, if needed
    # func_obj is a distinct placeholder for the argument
    # func_obj example: function takes two fs trees as input
    #
    assert isinstance(accesses, dict)
    args = args - _all_access_set
    _access_list.append(args)


# example: function takes two source trees as input
# how do we tell them apart? - has to be by arg position
# def f(tree1, tree2):
#    return int(tree1["a/b"]) + int(tree2["c/d"])


# trace_access(f, (0, ("a/b",), {})
# trace_access(f, (1, ("c/d",), {})

"""
How do we annotate parallel vs. sequential accesses?
- for bad tools case, we mark everything parallel anyway and sort it out later.

maybe just always do that? Otherwise we're introducing a lot of spurious dependencies.
- yes: make the default parallel; have an explicit way to mark sequencing.

Naming:
- args named by position: int or string
- but how can we tell? E.g. suppose we passed the same value for tree1 and tree2 above?
- so need to wrap them at memo time.
- which means memoizer needs to look at all the args. But it's doing that anyway so that's ok.

And then globals just come pre-wrapped; key is string with a dot in it.
"""
