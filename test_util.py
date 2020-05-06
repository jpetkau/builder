#!/usr/bin/env python3

import unittest
import util


@util.decorator
class Dec:
    def __init__(self, func, msg="nope"):
        self.func = func
        self.msg = msg

    def __call__(self, *args, **kwargs):
        return self.func(*args, **kwargs) + " " + self.msg


@util.decorator
def dec(func, msg="nope"):
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs) + " " + msg

    return wrapper


@dec
def ffoo(msg):
    return "foo " + msg


@dec("yep")
def ffooey(msg):
    return "foo " + msg


@Dec
def foo(msg):
    return "foo " + msg


@Dec("yep")
def fooey(msg):
    return "foo " + msg


class DecoratorTest(unittest.TestCase):
    def test_decorate_fun(self):
        self.assertEqual(ffoo("x"), "foo x nope")
        self.assertEqual(ffooey("y"), "foo y yep")
        self.assertEqual(ffoo.__name__, "ffoo")
        self.assertEqual(ffooey.__name__, "ffooey")

    def test_decorate_class(self):
        self.assertEqual(foo("x"), "foo x nope")
        self.assertEqual(fooey("y"), "foo y yep")
        self.assertEqual(foo.__name__, "foo")
        self.assertEqual(fooey.__name__, "fooey")


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
        o = LazyAttrs(1)
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
