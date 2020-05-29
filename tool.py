#!/usr/bin/env python3
import argparse, logging, os
import fs, cas, config


if __name__ == "__main__":
    # logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument("command")
    parser.add_argument("path")
    args = parser.parse_args()

    config.init()

    if args.command == "hash":
        tree = (fs.src_root / args.path).contents()
        print(cas.sig(tree, False))
