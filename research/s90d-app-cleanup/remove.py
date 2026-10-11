#!/usr/bin/env python3
"""Remove only the reviewed S90D optional apps, with backup and scope guards."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import sqlite3
import subprocess
import sys
import tarfile

TOOLKIT = Path.home() / '.local/share/samsung-tv-research'
PRIVATE = TOOLKIT / 'analysis/s90d-app-cleanup'
TARGETS = {
    'LImG0QPABV': 'QVC+ and HSN+', 'zigzSWa1hy': 'Instagram',
    'HupEmjIB4I': 'Glance', 'yL49PNFmjW': 'Samsung Promotion',
    'jAfAs7yVDX': 'Samsung GameBreaks', 'CmeyUlnhYY': 'Amazon Luna',
    'KMZlIHL7Pp': 'Blacknut Cloud Gaming', 'GHI3a0zMSx': 'Xbox',
    'com.microsoft.copilot': 'Copilot',
}
BACKUP = TOOLKIT / 'dumps/20260920T163630Z/optional-apps-backup.tar.gz'
BACKUP_SHA = '557a6f08dda048382a04f50e9b0f2f91b4602b445d158a3aa991e470c3607acf'
FIELDS = 'package_type,package_version,package_removable,package_preload,package_readonly,package_system,mainapp_id'


def open_db(path):
    return sqlite3.connect('file:' + str(path) + '?mode=ro', uri=True)


def extract_db(dump, label):
    with tarfile.open(dump / 'package-after.tar.gz') as archive:
        data = archive.extractfile('./0000.sqlite').read()
    path = PRIVATE / (label + '.sqlite')
    path.write_bytes(data)
    return open_db(path)


def verify_scope(before, after, removed):
    if after.execute('PRAGMA integrity_check').fetchone() != ('ok',):
        raise RuntimeError('Package database integrity failed')
    for table, columns, package_index in [('package_info', 'package', 0), ('package_app_info', 'app_id,package', 1)]:
        old = set(before.execute('SELECT ' + columns + ' FROM ' + table))
        new = set(after.execute('SELECT ' + columns + ' FROM ' + table))
        expected = {row for row in old if row[package_index] in removed}
        if old - new != expected or any(row[package_index] in removed for row in new):
            raise RuntimeError('Unexpected removal scope in ' + table)


def run_collector(ops, name):
    config = PRIVATE / (name + '-operations.json')
    config.write_text(json.dumps(ops))
    log = PRIVATE / (name + '.log')
    with log.open('w') as out:
        result = subprocess.run([sys.executable, str(TOOLKIT / 'gather-dumps.py')],
                                env={**os.environ, 'DUMP_OPERATIONS_FILE': str(config)},
                                stdout=out, stderr=subprocess.STDOUT)
    lines = log.read_text().splitlines()
    dirs = [line.split(' ', 1)[1] for line in lines if line.startswith('DUMP_DIRECTORY ')]
    if not dirs:
        raise RuntimeError('Collector did not start; inspect ' + str(log))
    dump = Path(dirs[-1])
    manifest = json.loads((dump / 'manifest.json').read_text())
    if result.returncode or not manifest['complete'] or not all(r['verified'] and r['details']['exit'] == 0 for r in manifest['operations']):
        raise RuntimeError('Operation uncertain/failed; inspect ' + str(dump) + ' before any retry')
    print('Evidence:', dump, flush=True)
    return dump


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('package', choices=tuple(TARGETS))
    args = parser.parse_args()
    os.umask(0o077)
    if json.loads((TOOLKIT / 'config.json').read_text())['tv_host'] != '192.0.2.12':
        raise SystemExit('Wrong TV configured')
    if hashlib.sha256(BACKUP.read_bytes()).hexdigest() != BACKUP_SHA:
        raise SystemExit('Verified private backup required')
    original = open_db(PRIVATE / 'before.sqlite')
    package = args.package
    row = original.execute('SELECT ' + FIELDS + ' FROM package_info WHERE package=?', (package,)).fetchone()
    if row is None or row[2:6] != ('true','false','false','false'):
        raise SystemExit('Original protection flags not eligible')
    # Snapshot immediately before this one change. Check only known prior removals.
    snapshot = {'name':'package-after.tar.gz','kind':'sqlite','roots':['/opt/dbspace/.pkgmgr_parser.db']}
    pre = run_collector([snapshot], 'before-' + package)
    current = extract_db(pre, 'before-' + package)
    gone = {r[0] for r in original.execute('SELECT package FROM package_info')} - {r[0] for r in current.execute('SELECT package FROM package_info')}
    if gone - TARGETS.keys():
        raise SystemExit('Unrelated packages changed since inventory')
    verify_scope(original, current, gone)
    now = current.execute('SELECT ' + FIELDS + ' FROM package_info WHERE package=?', (package,)).fetchone()
    if now is None:
        print(TARGETS[package] + ': already absent'); return
    if now != row or current.execute('SELECT 1 FROM package_dependency_info WHERE depends_on=?', (package,)).fetchone():
        raise SystemExit('Package metadata/dependencies changed')
    # Exact identity/version/protection/dependency checks also run on the TV.
    predicate = ' AND '.join(key + '=' + "'" + value.replace("'", "''") + "'" for key,value in zip(['package'] + FIELDS.split(','), [package] + list(row)))
    sql = 'SELECT count(*) FROM package_info WHERE ' + predicate + ";"
    deps = "SELECT count(*) FROM package_dependency_info WHERE depends_on='" + package + "';"
    command = "set -eu\ntest \"$(id -u)\" = 0\ngrep -q '^Version=T-PTMDAKUC-0090-2130.0;' /etc/prd_info.ini\n"
    command += 'test "$(sqlite3 /opt/dbspace/.pkgmgr_parser.db ' + shlex.quote(sql) + ')" = 1\n'
    command += 'test "$(sqlite3 /opt/dbspace/.pkgmgr_parser.db ' + shlex.quote(deps) + ')" = 0\n'
    command += "/usr/bin/pkgcmd -u -n " + shlex.quote(package) + '\n'
    post = run_collector([{'name':'uninstall.txt','kind':'command','command':command,'timeout':25}, snapshot], 'remove-' + package)
    after = extract_db(post, 'after-' + package)
    verify_scope(current, after, {package})
    print('Verified removed: ' + TARGETS[package], flush=True)


if __name__ == '__main__':
    main()
