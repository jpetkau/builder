#!/usr/bin/env python3
import contextlib, os

# default config for development / debugging build
# should do something smarter by default, maybe search from up current dir
# for a special file?
config = {
    "cas_root": os.path.abspath(os.path.join(__file__, "../build-files/cas")),
    "out_root": os.path.abspath(os.path.join(__file__, "../build-files/out")),
    "gen_root": os.path.abspath(os.path.join(__file__, "../build-files/gen")),
    "src_root": os.path.abspath(os.path.join(__file__, "../test_data")),
}


def init_config(**cfg):
    config.clear()
    config.update(cfg)


# _opts is a simple flat dictionary of contextual options
# clever nesting etc. left for someday
_opts = {}


def init_options(**kwargs):
    assert not _opts
    _opts = kwargs


@contextlib.contextmanager
def options(**kwargs):
    global _opts
    old_opts = _opts
    new_opts = old_opts.copy()
    new_opts.update(kwargs)
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


opt = Opt()
