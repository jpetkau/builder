#!/usr/bin/env python3

import unittest
import config
import fs
import cas
import os


HELLO = b"hello world\n"


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
        t = fs.src_root.tree()
        print(f"out_root={os.fspath(fs.out_root)}")
        t.write_copy(fs.out_root)


if __name__ == "__main__":
    import logging

    logging.basicConfig(level=logging.DEBUG)
    unittest.main()
