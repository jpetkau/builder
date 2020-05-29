#!/usr/bin/env python3

import unittest
import config
import fs
import cas
import os


HELLO = b"hello world\n"


class PathTest(unittest.TestCase):
    def setUp(self):
        config.init()

    def test_path(self):
        p = fs.src_root / "x/y" / "z"
        self.assertEqual(str(p), "{src_root}/x/y/z")
        self.assertEqual(str(p / ".."), "{src_root}/x/y")
        self.assertEqual(str(p / "../w"), "{src_root}/x/y/w")
        self.assertEqual(str(p / "../../.."), "{src_root}/")


class BlobTest(unittest.TestCase):
    def setUp(self):
        config.init()

    def test_blob_from_bytes(self):
        b = fs.Blob(bytes=HELLO)
        self.assertEqual(b.bytes(), HELLO)
        with open(b, "rb") as f:
            self.assertEqual(f.read(), HELLO)
        self.assertEqual(b.path(), fs.cas_root / "blob/0d/68656c6c6f20776f726c640a")


class TreeTest(unittest.TestCase):
    def setUp(self):
        config.init()

    def test_tree(self):
        t = fs.src_root.contents()
        print(f"out_root={os.fspath(fs.out_root)}")
        t.write_copy(fs.out_root)

    def test_tree_path(self):
        t = fs.src_root.contents()
        p1 = t / "lib1"
        p2 = t / "lib1"
        self.assertEqual(cas.sig(p1), cas.sig(p2))
        self.assertEqual(cas.sig(p1.contents()), cas.sig(p2.contents()))
        self.assertEqual(cas.sig(p1.contents()), cas.sig(t["lib1"]))

    def test_blob_path(self):
        t = fs.src_root.contents()
        p1 = t / "somefile.txt"
        p2 = t / "somefile.txt"
        self.assertEqual(cas.sig(p1), cas.sig(p2))
        self.assertEqual(cas.sig(p1.contents()), cas.sig(p2.contents()))
        self.assertEqual(cas.sig(p1.contents()), cas.sig(t["somefile.txt"]))


if __name__ == "__main__":
    import logging

    logging.basicConfig(level=logging.DEBUG)
    unittest.main()
