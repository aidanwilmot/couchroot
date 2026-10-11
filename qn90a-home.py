#!/usr/bin/env python3
"""One-shot, firmware-guarded QN90A Home routing and native key verification."""
import argparse
import hashlib
import importlib.util
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('apply', 'restore', 'key'))
    args = parser.parse_args()
    if args.mode == 'apply':
        backup = Path.home() / '.local/share/samsung-tv-research/qn90a/app-context-original.db'
        if not backup.exists() or hashlib.sha256(backup.read_bytes()).hexdigest() != '44f5aebf3f476c31a42751a14dc4da77518873b2cb34e59613c1f22910f456b8':
            raise SystemExit('Verified private original routing backup is required before applying')
    path = Path(__file__).with_name('qn90a-root-check.py')
    spec = importlib.util.spec_from_file_location('qn90a_root', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.run(args.mode)


if __name__ == '__main__':
    main()
