#!/usr/bin/env python3


class _Partial:
    def __init__(self, access_set):
        assert type(access_set) in (set, frozenset)
        self.access_set = access_set


def _memo_sig(A, access_dict):
    cas.sig((A, access_dict))
    return _memo_store[cas.sig((A, access_dict))]


class Memo:
    def get(self, key, default=None):
        return self._store.get(key, default)

    def __getitem__(self, key):
        return self._store[key]

    def __setitem__(self, key, item):
        assert type(key) is cas.Sig
        assert type(item) in (_Partial, cas.Sig, type(None))
        old = _memo_store.get(Y)
        if old and old != item:
            logger.warning("storing inconsistent memo item")
        self._store[key] = item


def get_memo(A, f):
    """
    A = hash of call and args excluding f
    f = some function which may have been called that we don't want to hash
    """
    s = {}  # set of (arg, result) calls to f
    Y = _memo_sig(A, s)
    m = _memo[Y]
    while isinstance(m, _Partial):
        a = set()
        da = m.access_set
        while True:
            a |= da
            s.update({k: f(k) for k in da})

            Y1 = _memo_sig(A, s)
            m = _memo[Y1]
            if m:
                break
            da = _memo_fixup[Y, a]
            if da is None:
                return None
        Y = Y1
    # Either final result hash or None if we don't have it
    return m


# after later call to func with same args (not including fs)
# used=dict of (k,v) of actual accesses and results
def update_memo(A, used0, result):
    used = used0.copy()
    s = {}

    while True:
        Y = _memo_sig(A, s)

        if not used:
            # no checks left to do: we can store final result
            _memo[Y] = result
            return

        ks = _memo[Y]

        if not isinstance(ks, _Partial):
            # new result or clobbering inconsistent result
            _memo[Y] = _Partial(used)
            s.update(used)
            assert s == used0
            used = {}
            continue

        # result was already stored. Narrow down possible "first access" list
        old_acc = ks.access_set
        first_acc = old_acc & set(used.keys())

        if not first_acc:
            logger.error("inconsistency strikes again")
            # can't salvage this without just clobbering all the old results
            first_acc = set(used.keys())

        elif first_acc != old_acc:
            _memo[Y] = _Partial(first_acc)
            _memo_fixup[hash.Sig(Y, first_acc)] = old_acc - first_acc

        for k in first_acc:
            s[k] = used.pop(k)


"""
Finding old_sigs:

- we might have stored a dozen different old_sigs right?
e.g.
first access was {a,b,c,d}
over lots of calls got all sorts of different values at those keys

then along somes Mr. first access {a,c}

Now we wish we'd stored a hundred different {a: aX, c: cX} sets but we didn't

whan can we do?
- we know {c,d} are the missing accesses
- could fall back to "let extra build steps happen"
- could store backup memo linked list:

- first access {a,c} yes but also "other access" {a,b,c,d} [and whatever other sets]
- can't grow without bound: only grows by 1 when we're reducing the set size
- when we go to evaluate one of those other functions, we fix it at that time
  [almost resembles disjoint set algo]

Right, we only write a 'fallback' set when we're clobbering the old set to make
it smaller, so fallbacks are limited in size

not so:
- initial set was {a,b,c,d}
- later find out it's {a,b,c}, then {a,b}, then {a}
- all of those go under _memo[Y0]
- ok, so all we're doing is adding some sorting:

    {a,b,c,d}
    then {a,b,c},{d}
    then {a,b},{c},{d}
    then {a},{b},{c},{d}

But it's not actually getting bigger!

linked list?

    memo[Y] -> partial {a,b,c,d}
    memo[Y] -> partial {a,b,c}, fixup[Y,{a,b,c}] -> {d}
    memo[Y] -> partial {a,b}, fixup[Y,{a,b}] -> {c}
    memo[Y] -> partial {a}, fixup[Y,{a}] -> {b}

Y encodes all the keys and values we looked at already
"""


"""
How do we memo a function that takes, for example, `list[bigtree]`? Or some other
type with possibly-nested tree objects?
- do we need to identify the whole path to that bigtree? yes. Maybe can't
  do that in general, but we can at least:

- allow memo point to explicitly tag special args to walk down
  - handle list/dict/etc. in such args (maybe wrap in a general access proxy)

"""


class AccessProxy:
    def __init__(self, obj, tag):
        self._obj = obj
        self._tag = tag

    def __call__(self, *args, **kwargs):
        try:
            result = self._obj(*args, **kwargs)
        except BuildError as e:
            memo.record(self._tag, "__call__", args, kwargs, memo.Err(e))
        else:
            memo.record(self._tag, "__call__", args, kwargs, result)

    def __getitem__(self, key):
        try:
            result = self._obj[key]
        except BuildError as e:
            memo.record(self._tag, "__call__", args, kwargs, memo.Err(e))
        else:
            memo.record(self._tag, "__call__", args, kwargs, result)

    # ...could wrap all sorts of things here, possibly based on real attrs of obj
    # ...or don't have a universal AccessProxy, only specialized ones

    # What if a method returns 'self'? Need to wrap that too?
    # ugh, probably better not to have a universal wrapper, just specific ones for
    # file tree and options dict.


class YTree:
    """
    Wraps fs.Tree to record access to files.
    """

    def __init__(self, tree, tag):
        self._tree = tree
        self._tag = tag

    def __ser__(self):
        raise TypeError("Oopsie")


def y_memoize(f, arg_index):
    k = arg_index

    @util.wraps(f)
    def wrapper(*args, **kwargs):
        assert type(args[k] is Tree)

        if type(arg_index) is int:
            tree = args[k]
            wtree = WrapTree(tree)
            wargs = args[:k] + [wtree] + args[k + 1 :]
            wkwargs = kwargs
        else:
            tree = kwargs[k]
            wtree = WrapTree(tree)
            wargs = args
            wkwargs = kwargs.copy()
            wkwargs[i] = wtree

        # try simple memoization first, unless it would require
        # hashing a whole source tree
        #
        # maybe that's dumb? if we assume we can always get the source tree
        # efficiently (true except in megarepos, and for them imagine we have
        # a sensible file system), stuff gets simpler?
        if tree.has_cheap_sig():
            arg_sig = cas.sig((cas.WithSig(f_sig), args, kwargs))
            res_sig = _memo_store.get(arg_sig, None)
            if res_sig:
                return res_sig.object()

        with context.options(current_call_hash=arg_sig), context.trace() as tr:
            v = f(*wargs, **wkwargs)

        vsig = cas.store(v)
        if tr.has_trace():
            _memo_store[arg_sig] = vsig
        else:
            raise RuleError("traced function failed to record accesses")
        update_memo(
            cas.sig((cas.WithSig(f_sig), wargs, wkwargs)), tr.get_trace(v), vsig
        )
        return v

    assert sig_value is None or isinstance(sig_value, cas.Sig)
    wrapper.__sig__ = sig_value or cas.sig(f)
    return wrapper


"""
YTree:
- Wraps
BigTree:
- similar API to Tree, but instead of hashing everything, memo parts
- if we run a tool and it doesn't record explicit deps, assume worst case

Always base things on actual hashed trees?
- Yes for output dirs, but can't for source dir

* Make the distinction between Tree input and partial input at the function
  being memoized, not the caller.

* Caller still needs a different type to describe giant source tree vs. smaller
  output trees. Maybe warn on mismatch.
"""
