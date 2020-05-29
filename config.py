#!/usr/bin/env python3
import contextlib, os
import util

# default config for development / debugging build
# should do something smarter by default, maybe search from up current dir
# for a special file?
_default_config = {
    "db_root": os.path.abspath(os.path.join(__file__, "../build-files")),
    "cas_root": "{db_root}/cas",
    "out_root": "{db_root}/out",
    "gen_root": "{db_root}/gen",
    "src_root": os.path.abspath(os.path.join(__file__, "../test_data")),
}
config = {}

_initialized = False
_on_init = []  # list of initializers to call on init
_on_uninit = []  # list of objects to close() on uninit


def oninit(f):
    _on_init.append(f)
    if _initialized:
        # already initialized; run init immediately
        _on_uninit.append(f(**config))
    return f


# this is stupid
def init(**cfg):
    uninit()

    global _initialized
    _initialized = True

    config.clear()
    config.update(_default_config)
    config.update(cfg)
    for k in config:
        config[k] = config[k].format(**config)
    for f in _on_init:
        _on_uninit.append(f(**config))


def uninit():
    while _on_uninit:
        x = _on_uninit.pop()
        x.close()
    global _initialized
    _initialized = False
