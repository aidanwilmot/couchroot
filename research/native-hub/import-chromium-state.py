#!/usr/bin/env python3
"""Convert a stable, private web Hub LevelDB snapshot into native preferences.

Deployment supplies the snapshot and explicit CCL reader checkout. Reads only
allowlisted Hub preferences; never changes Chromium files or overwrites output.
No parsing or migration is added to the TV's first-frame path.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

KEYS = frozenset('minimal-hub.' + key + '.v1' for key in
                 ('shortcuts', 'selection', 'layout', 'clock', 'start'))
PREFIX = b'_file://\x00\x01'


def extract_preferences(records):
    """Resolve live values/tombstones by sequence, then decode Chromium strings.

    Records are (user_key, value, sequence, is_live). Obsolete table copies must
    not resurrect a later deletion. Equal-sequence conflicts fail closed.
    """
    latest = {}
    for key, value, seq, live in records:
        if not key.startswith(PREFIX):
            continue
        suffix = key[len(PREFIX):]
        if suffix not in {name.encode('ascii') for name in KEYS}:
            continue
        name = suffix.decode('ascii')
        if not isinstance(seq, int) or seq < 0 or len(value) > 1024 * 1024:
            raise ValueError('Invalid preference record')
        item = (seq, bool(live), value)
        previous = latest.get(name)
        if previous is not None and previous[0] == seq and previous != item:
            raise ValueError('Conflicting preference sequence')
        if previous is None or seq > previous[0]:
            latest[name] = item
    result = {}
    for name, (_, live, value) in latest.items():
        if not live:
            continue
        if not value or value[0] not in (0, 1):
            raise ValueError('Unsupported Chromium string encoding')
        result[name] = value[1:].decode('utf-16-le' if value[0] == 0 else 'latin1', errors='strict')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('snapshot', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--reader-directory', type=Path, required=True)
    parser.add_argument('--snappy-directory', type=Path)
    args = parser.parse_args()
    reader = args.reader_directory / 'ccl_chromium_reader' / 'storage_formats'
    if not (reader / 'ccl_leveldb.py').is_file():
        raise ValueError('Missing CCL reader checkout')
    sys.path.insert(0, str(reader))
    if args.snappy_directory:
        sys.path.insert(0, str(args.snappy_directory))
    import ccl_leveldb
    with ccl_leveldb.RawLevelDb(args.snapshot) as db:
        values = extract_preferences((r.user_key, r.value, r.seq, r.state == ccl_leveldb.KeyState.Live)
                                     for r in db.iterate_records_raw())
    code = 'process.stdout.write(require(process.argv[1]).convert(JSON.parse(require("fs").readFileSync(0,"utf8"))))'
    state = subprocess.run(['node', '-e', code, str(Path(__file__).with_name('import-web-state.cjs'))],
                           input=json.dumps(values).encode(), capture_output=True, check=True).stdout
    if len(state) > 100000:
        raise ValueError('Oversized native preference file')
    fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(state)
        stream.flush()
        os.fsync(stream.fileno())
    print('Converted', len(values), 'supported web preferences;', len(state.splitlines()) - 1, 'shortcuts')


if __name__ == '__main__':
    main()
