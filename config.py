#!/usr/bin/env python3
import contextlib, os
import util

# default config for development / debugging build
# should do something smarter by default, maybe search from up current dir
# for a special file?
_default_config = {
    "cas_root": os.path.abspath(os.path.join(__file__, "../build-files/cas")),
    "out_root": os.path.abspath(os.path.join(__file__, "../build-files/out")),
    "gen_root": os.path.abspath(os.path.join(__file__, "../build-files/gen")),
    "src_root": os.path.abspath(os.path.join(__file__, "../test_data")),
}
config = {}

_initialized = False
_oninit = []
_ondeinit = []


def oninit(f):
    _oninit.append(f)
    if _initialized:
        _ondeinit.append(f(**config))
    return f


# this is stupid
def init(**cfg):
    global _initialized

    if _initialized:
        for x in _ondeinit:
            x.close()
        _ondeinit.clear()

    _initialized = True
    if not cfg:
        cfg = _default_config

    config.clear()
    config.update(cfg)
    for f in _oninit:
        _ondeinit.append(f(**cfg))
