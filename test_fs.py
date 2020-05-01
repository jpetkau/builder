#!/usr/bin/env python3

import unittest
import context
import fs


HELLO=b"hello world\n"

hsig=sig.of(fs.Blob(bytes=HELLO))

class BlobTest(unittest.TestCase):
    def test_blob_from_bytes(self):
        with context.options(gen_root="test_data/gen", src_root="test_data"):
            b=Blob(bytes=HELLO)
            self.assertEqual(sig.of(b), hsig)
            self.assertEqual(b.bytes, HELLO)
            with b.path.open() as f:
                self.assertEqual(f.read(), HELLO)
            self.assertEqual(b.path, fs.gen_root / "blobs/aa/aaa")

    def test_blob_from_path(self):
        with context.options(gen_root="test_data/gen", src_root="test_data"):
            b=Blob(path=fs.src_root / "hello.txt")
            self.assertEqual(sig.of(b), hsig)
            self.assertEqual(b.bytes, HELLO)
            with b.path.open() as f:
                self.assertEqual(f.read(), HELLO)
            self.assertEqual(b.path, fs.gen_root / "blobs/aa/aaa")

if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.DEBUG)
    unittest.main()
