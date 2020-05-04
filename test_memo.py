#!/usr/bin/env python3

import unittest
import cas
import memo


@memo.memoize
def f1(x):
    return x


@memo.memoize
def f2():
    return 20


# lie about f3's hash
@memo.memoize(sig_value=cas.sig(f2))
def f3():
    return 30


@memo.memoize
def f4():
    return f1(5) + f2()


class MemoTest(unittest.TestCase):
    def test_memo(self):
        self.assertEqual(cas.sig(f2), cas.sig(f3))
        self.assertEqual(f1(10), 10)
        self.assertEqual(memo.get(f1.__wrapped__, 10), 10)
        self.assertEqual(f2(), 20)
        self.assertEqual(f3(), 20)
        self.assertEqual(f4(), 25)


if __name__ == "__main__":
    import logging

    # logging.basicConfig(level=logging.DEBUG)
    unittest.main()
