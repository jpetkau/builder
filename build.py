#!/usr/bin/env python3
"""
Main entry point
"""
import logging, os, types, sys
import fs, config, context
import importer


src_root = os.path.abspath(os.path.join(__file__, "../test_data"))


class DebugFinder:
    @classmethod
    def find_spec(cls, name, path, target=None):
        print(f"Importing {name!r}")
        return None
sys.meta_path.insert(0, DebugFinder)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    src_root = os.path.abspath(os.path.join(__file__, "../test_data"))
    junk = os.path.abspath(os.path.join(__file__, "../build-files"))
    config.init(
        src_root=src_root,
        gen_root=os.path.join(junk, "gen"),
        cas_root=os.path.join(junk, "cas"),
        out_root=os.path.join(junk, "out"),
    )

    b = importer.importer("root")

    bin = b.main()

    bin.tree.write_copy(fs.out_root, makedirs=True)
