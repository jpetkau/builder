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

def dict_sub(d, s):
    for k in s:
        del d[k]

def dict_filter(d, s):
    return {d[k] for k in d if k in s}

def dict_add(d0, d1):
    return {**d0, **d1}

def get_memo(A, f):
    """
    A = hash of call and args excluding f
    f = some function which may have been called that we don't want to hash
    """
    s = {}  # set of (arg, result) calls to f
    Y = _memo_sig(A, s)
    m = _memo[Y]
    while isinstance(m, _Partial):
        a = {}
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
            assert s==used0
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
