#!/usr/bin/env python3
"""Firmware-guarded QN90A idle AirPlay return rule; exact transactional rollback."""
import argparse
import hashlib
import importlib.util
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('apply', 'restore', 'early-apply', 'early-restore'))
    args = parser.parse_args()
    if args.mode.endswith('apply'):
        backup = Path.home() / '.local/share/samsung-tv-research/qn90a/before-cast-route.db'
        if not backup.exists() or hashlib.sha256(backup.read_bytes()).hexdigest() != '1bce2f3edb8cccb525849bf25ed61b85a206121e62a6d5c40c83406a0396861c':
            raise SystemExit('Verified private pre-casting routing backup is required')
    spec = importlib.util.spec_from_file_location('qn90a_root', Path(__file__).with_name('root-check.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.run('cast-' + args.mode)


if __name__ == '__main__':
    main()
