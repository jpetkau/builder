#!/usr/bin/env python3

import unittest
import cas

__ALLOW_GLOBAL_REFS__ = True


def global_fun():
    print("hi")


def hidden1(x):
    print("hi", x)


def hidden2(x):
    print("hi", x)


def hidden3(x, y):
    print("hi", x)


def hidden4(x, y):
    print("hi", unittest)


def get_hidden1(f=hidden1):
    return f


def get_hidden2(f=hidden2):
    return f


def get_hidden3(f=hidden3):
    return f


def get_hidden4(f=hidden4):
    return f


del hidden1
del hidden2
del hidden3
del hidden4


class Thing:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

    def __eq__(self, other):
        d0, d1 = self.__dict__, other.__dict__
        for k in set(d0) | set(d1):
            if not k.startswith("__"):
                if k not in d0 or k not in d1 or d0[k] != d1[k]:
                    return False
        return True

    def __repr__(self):
        return f"Thing{self.__dict__}"


cases = [
    b"",
    b"foo",
    None,
    True,
    False,
    "",
    "foo",
    "仙侠小说",
    0,
    -1,
    1,
    0x7FFF,
    0x8000,
    -0x8000,
    -0x8001,
    [],
    (),
    [0],
    [0, 1],
    [0, [1, 2], (3, 4, [])],
    {},
    {0: 1, 2: 3},
    {"a": 1, "b": 2, "c": [0, 1, 2]},
    "this string is longer than 31 bytes so it must actually be hashed",
    {
        "a": "short",
        "b": [
            "this string is part of a list",
            "that is too long to represent",
            "as a short hash",
        ],
    },
    cas.sig(b"spam"),
    cas.Global,
    Thing,
    Thing(x=1, y=2),
    cas.sig(Thing),
    cas.sig(Thing(x=1, y=2)),
    global_fun,
]


class SigTest(unittest.TestCase):
    def test_prims(self):
        self.assertEqual(cas.sig(b"").hash, b"\x01")
        self.assertEqual(cas.sig(b"foo").hash, b"\x04foo")
        self.assertEqual(cas.sig(None).hash, b"\x42\x01")
        self.assertEqual(cas.sig(False).hash, b"\x43\x02f")
        self.assertEqual(cas.sig(True).hash, b"\x43\x02t")
        self.assertEqual(cas.sig(0).hash, b"\x44\x02i\x01")
        self.assertEqual(cas.sig(1).hash, b"\x45\x02i\x02\x01")
        self.assertEqual(cas.sig(127).hash, b"\x45\x02i\x02\x7f")
        self.assertEqual(cas.sig(-128).hash, b"\x45\x02i\x02\x80")
        self.assertEqual(cas.sig(0x7FFF).hash, b"\x46\x02i\x03\xff\x7f")
        self.assertEqual(cas.sig(-0x8000).hash, b"\x46\x02i\x03\x00\x80")
        self.assertEqual(cas.sig(cas.Global).hash, b"\x43\x02G")
        self.assertEqual(cas.sig(cas.Global("X", "Y")).hash, b"\x48\x43\x02G\x02X\x02Y")

    def test_dict_order(self):
        self.assertEqual(cas.sig({1: 2, 3: 4}), cas.sig({3: 4, 1: 2}))

    def test_fn_sig(self):
        self.assertEqual(cas.sig(get_hidden1()), cas.sig(get_hidden2()))
        self.assertNotEqual(cas.sig(get_hidden1()), cas.sig(get_hidden3()))
        cas.sig(get_hidden4())

    def test_prim_from_sig(self):
        self.assertEqual(cas.Sig(hash=b"\x01").object(), b"")
        self.assertEqual(cas.Sig(hash=b"\x04Foo").object(), b"Foo")

    def test_compound_sig(self):
        # list is compound (b"L", content-hashes)
        self.assertEqual(cas.sig([]).hash, b"\x43\x02L")
        self.assertEqual(cas.sig(()).hash, b"\x43\x02T")
        self.assertEqual(cas.sig([None, True]).hash, b"\x48\x02L\x42\x01\x43\x02t")

    def test_roundtrip(self):
        for x in cases:
            with self.subTest(value=x):
                h = cas.store(x)
                self.assertEqual(h.object(), x)


if __name__ == "__main__":
    import logging

    logging.basicConfig(level=logging.DEBUG)
    unittest.main()
