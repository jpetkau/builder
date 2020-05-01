#!/usr/bin/env python3

import unittest
import sig

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
    None,
    True,
    False,
    b"",
    b"foo",
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
    Thing,
    Thing(x=1,y=2)
]


class SigTest(unittest.TestCase):
    def test_prims(self):
        self.assertEqual(sig.of(None).value, b"\x01")
        self.assertEqual(sig.of(False).value, b"\x020")
        self.assertEqual(sig.of(True).value, b"\x021")
        self.assertEqual(sig.of(0).value, b"\x02i")
        self.assertEqual(sig.of(1).value, b"\x03i\x01")
        self.assertEqual(sig.of(2).value, b"\x03i\x02")
        self.assertEqual(sig.of(0x7FFF).value, b"\x04i\xff\x7f")
        self.assertEqual(sig.of(-0x8000).value, b"\x04i\x00\x80")

    def test_prim_from_sig(self):
        self.assertEqual(sig.Sig(hash=b"\x01").object(), None)

    def test_compound_sig(self):
        self.assertEqual(sig.of([]).value, b"\x02L")
        self.assertEqual(sig.of(()).value, b"\x02T")
        self.assertEqual(sig.of([None, True]).value, b"\x05L\x01\x021")
        self.assertEqual(
            sig.of([None, True, [1, 2]]).value, b"\x0dL\x01\x021\x08L\x03i\x01\x03i\x02"
        )
        self.assertEqual(
            sig.of([None, True, (1, 2)]).value, b"\x0dL\x01\x021\x08T\x03i\x01\x03i\x02"
        )
        self.assertEqual(sig.of({}).value, b"\x06D\x02L\x02L")

    def test_roundtrip(self):
        for x in cases:
            h = sig.of(x)
            with self.subTest(value=x, hash=h):
                self.assertEqual(h.object(), x)


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.DEBUG)
    unittest.main()
