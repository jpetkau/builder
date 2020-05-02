#!/usr/bin/env python3

import unittest
import sig

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
    sig.of(b"spam"),
    sig.Global,
    Thing,
    Thing(x=1, y=2),
    sig.of(Thing),
    sig.of(Thing(x=1, y=2)),
    global_fun,
]


class SigTest(unittest.TestCase):
    def test_prims(self):
        self.assertEqual(sig.of(b"").hash, b"\x01")
        self.assertEqual(sig.of(b"foo").hash, b"\x04foo")
        self.assertEqual(sig.of(None).hash, b"\x42\x01")
        self.assertEqual(sig.of(False).hash, b"\x43\x02f")
        self.assertEqual(sig.of(True).hash, b"\x43\x02t")
        self.assertEqual(sig.of(0).hash, b"\x44\x02i\x01")
        self.assertEqual(sig.of(1).hash, b"\x45\x02i\x02\x01")
        self.assertEqual(sig.of(127).hash, b"\x45\x02i\x02\x7f")
        self.assertEqual(sig.of(-128).hash, b"\x45\x02i\x02\x80")
        self.assertEqual(sig.of(0x7FFF).hash, b"\x46\x02i\x03\xff\x7f")
        self.assertEqual(sig.of(-0x8000).hash, b"\x46\x02i\x03\x00\x80")
        self.assertEqual(sig.of(sig.Global).hash, b"\x43\x02G")
        self.assertEqual(sig.of(sig.Global("X", "Y")).hash, b"\x48\x43\x02G\x02X\x02Y")

    def test_fn_sig(self):
        self.assertEqual(sig.of(get_hidden1()), sig.of(get_hidden2()))
        self.assertNotEqual(sig.of(get_hidden1()), sig.of(get_hidden3()))
        sig.of(get_hidden4())

    def test_prim_from_sig(self):
        self.assertEqual(sig.Sig(hash=b"\x01").object(), b"")
        self.assertEqual(sig.Sig(hash=b"\x04Foo").object(), b"Foo")

    def no_test_compound_sig(self):
        self.assertEqual(sig.of([]).hash, b"\x02L")
        self.assertEqual(sig.of(()).hash, b"\x02T")
        self.assertEqual(sig.of([None, True]).hash, b"\x05L\x01\x021")
        self.assertEqual(
            sig.of([None, True, [1, 2]]).hash, b"\x0dL\x01\x021\x08L\x03i\x01\x03i\x02"
        )
        self.assertEqual(
            sig.of([None, True, (1, 2)]).hash, b"\x0dL\x01\x021\x08T\x03i\x01\x03i\x02"
        )
        self.assertEqual(sig.of({}).hash, b"\x06D\x02L\x02L")

    def test_roundtrip(self):
        for x in cases:
            with self.subTest(value=x):
                h = sig.of(x)
                self.assertEqual(h.object(), x)


if __name__ == "__main__":
    import logging

    logging.basicConfig(level=logging.DEBUG)
    unittest.main()
