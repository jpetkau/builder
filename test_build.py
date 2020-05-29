#!/usr/bin/env python3
"""
Main entry point
"""
import os, sys, tempfile, types, unittest
import config, fs, memo


class TestBuild(unittest.TestCase):
    def setUp(self):
        self.trace = []
        if "root" not in sys.modules:
            root = types.ModuleType("root")
            root.__path__ = [os.path.normpath(os.path.join(__file__, "../test_data"))]
            sys.modules["root"] = root

        self.bdir = tempfile.TemporaryDirectory()
        print(f"cache dir is {self.bdir.name}")
        config.init(db_root=self.bdir.name)
        memo.set_trace(self.trace)

    def tearDown(self):
        config.uninit()
        self.bdir.cleanup()
        memo.set_trace(None)

    def test_trivial(self):
        trace = self.trace
        import root.BUILD as b

        self.assertEqual(b.trivial(), 1)
        self.assertEqual(b.trivial(), 1)

        self.assertEqual(
            [t[:2] for t in trace],
            [("miss", "trivial"), ("store", "trivial"), ("hit", "trivial")],
        )

    def test_trivial2(self):
        trace = self.trace
        import root.BUILD as b

        self.assertEqual(b.trivial2(), 2)
        self.assertEqual(b.trivial2(), 2)

        self.assertEqual(
            [t[:2] for t in trace],
            [
                ("miss", "trivial2"),
                ("miss", "trivial"),
                ("store", "trivial"),
                ("hit", "trivial"),
                ("store", "trivial2"),
                ("hit", "trivial2"),
            ],
        )

    def test_tool_echo(self):
        trace = self.trace
        import root.BUILD as b

        self.assertEqual(b.echo(), b"hi")
        self.assertEqual(b.echo(), b"hi")
        self.assertEqual(b.echo_m(), b"hi")
        self.assertEqual(b.echo_m(), b"hi")
        self.assertEqual(
            [t[:2] for t in trace],
            [
                ("miss", "run_tool"),
                ("store", "run_tool"),
                ("hit", "run_tool"),
                ("miss", "echo_m"),
                ("hit", "run_tool"),
                ("store", "echo_m"),
                ("hit", "echo_m"),
            ],
        )

    def test_tool_copies(self):
        trace = self.trace
        import root.BUILD as b

        expected = b"somefile contents\n" * 2
        self.assertEqual(b.copy_stuff(), expected)
        self.assertEqual(
            [t[:2] for t in trace],
            [
                ("miss", "run_tool"),
                ("store", "run_tool"),
                ("hit", "run_tool"),  # aha bug?
                ("miss", "run_tool"),
                ("store", "run_tool"),
            ],
        )


if __name__ == "__main__":
    import logging

    # logging.basicConfig(level=logging.DEBUG)
    unittest.main()
