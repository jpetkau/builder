#!/usr/bin/env python3

import unittest
import context
import fs
import cas
import os


HELLO = b"hello world\n"

hsig = cas.sig(fs.Blob(bytes=HELLO))

builder_root = fs.abspath(__file__) / ".."
cfg = dict(
    src_root=os.fspath(builder_root / "test_data"),
    cas_root=os.fspath(builder_root / "build-files/cas"),
    gen_root=os.fspath(builder_root / "build-files/gen"),
    out_root=os.fspath(builder_root / "build-files/out"),
)


class BlobTest(unittest.TestCase):
    def test_blob_from_bytes(self):
        context.init_config(**cfg)

        b = fs.Blob(bytes=HELLO)
        self.assertEqual(cas.sig(b), hsig)
        self.assertEqual(b.bytes(), HELLO)
        with open(b, "rb") as f:
            self.assertEqual(f.read(), HELLO)
        self.assertEqual(b.path(), fs.cas_root / "blob/0d/68656c6c6f20776f726c640a")


class TreeTest(unittest.TestCase):
    def test_tree(self):
        context.init_config(**cfg)

        t = fs.src_root.tree()
        print(f"out_root={os.fspath(fs.out_root)}")
        t.write_copy(fs.out_root)


if __name__ == "__main__":
    import logging

    logging.basicConfig(level=logging.DEBUG)
    unittest.main()
