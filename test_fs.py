#!/usr/bin/env python3

import unittest
import context
import fs
import cas
import os


HELLO = b"hello world\n"

hsig = cas.sig(fs.Blob(bytes=HELLO))

cfg = dict(
    gen_root=os.path.abspath("test_data/gen"), src_root=os.path.abspath("test_data")
)


class BlobTest(unittest.TestCase):
    def test_blob_from_bytes(self):
        context.init_config(cfg)

        b = fs.Blob(bytes=HELLO)
        self.assertEqual(cas.sig(b), hsig)
        self.assertEqual(b.bytes(), HELLO)
        with open(b, "rb") as f:
            self.assertEqual(f.read(), HELLO)
        self.assertEqual(b.path(), fs.gen_root / "blob/0d/68656c6c6f20776f726c640a")

if __name__ == "__main__":
    import logging

    logging.basicConfig(level=logging.DEBUG)
    unittest.main()
