#!/usr/bin/env python3

import unittest
import util


class LazyAttrs:
    def __init__(self, val):
        self.val = val

    @util.lazy_attr("_spam")
    def m(self):
        return self.val

    @property
    @util.lazy_attr
    def p(self):
        return self.val


class LazyAttrTest(unittest.TestCase):
    def test_lazy_attr(self):
        o = Oncer(1)
        assert not hasattr(o, "_spam")
        assert not hasattr(o, "_memo_p")
        self.assertEqual(o.m(), 1)
        o.val += 1
        self.assertEqual(o.p, 2)
        o.val += 1
        assert o._spam == 1
        assert o._memo_p == 2
        self.assertEqual(o.m(), 1)
        self.assertEqual(o.p, 2)


if __name__ == "__main__":
    unittest.main()
