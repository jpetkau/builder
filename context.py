#!/usr/bin/env python3
import contextlib

# _opts is a simple flat dictionary of contextual options
# clever nesting etc. left for someday
_opts = {
}

def init_options(**kwargs):
    assert not _opts
    _opts = kwargs

@contextlib.contextmanager
def options(**kwargs):
    global _opts
    old_opts = _opts
    new_opts = old_opts.copy()
    new_opts.update(old_opts)
    _opts = new_opts
    try:
        yield
    finally:
        _opts = old_opts


class Opt:
    def __getattr__(self, name):
        return _opts[name]
    def __getitem__(self, name):
        return _opts[name]

opt=Opt()
