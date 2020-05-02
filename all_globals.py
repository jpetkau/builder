#!/usr/bin/env python3

# set of module names we're ok with hashing globals from
# you can also set `__ALLOW_GLOBAL_REFS__=True` in any
# module to include it in this set.
#
# Right now that is the only way to hash class definitions
# which is unfortunate, because they should be content-hashed
# like functions.
valid_globals = {
    "memo",
    "sig",
    "util",
    "contextlib",
    "functools",
    "hashlib",
    "typing",
    "enum",
    "errno",
    "hashes",
    "hashlib",
    "logging",
    "mock_store",
    "os",
    "posixpath",
    "re",
    "shutil",
    "stat",
    "StringIO",
    "subprocess",
    "sync",
    "sys",
    "tempfile",
    "types",
    "unittest",
}
