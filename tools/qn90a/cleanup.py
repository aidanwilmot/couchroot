#!/usr/bin/env python3
"""Remove a fixed set of optional QN90A apps through Samsung's native web-app manager."""
import argparse
import hashlib
import importlib.util
import os
from pathlib import Path, PurePosixPath
import sqlite3
import sys
from datetime import datetime, timezone

TARGETS = {
    '9FhM0cODbY': 'TikTok', 'zigzSWa1hy': 'Instagram',
    'LImG0QPABV': 'QVC+ and HSN+', 'jAfAs7yVDX': 'Samsung GameBreaks',
    'yL49PNFmjW': 'Samsung Promotion', 'HupEmjIB4I': 'Glance',
    'GHI3a0zMSx': 'Xbox', 'IewQEY143t': 'Google Meet',
    'AkhP5nCr24': 'Explore Google Assistant', 'AQKO41xyKP': 'Amazon Alexa',
}
MAIN_APPS = {
    '9FhM0cODbY': '9FhM0cODbY.TikTokTV', 'zigzSWa1hy': 'zigzSWa1hy.InstagramAirwave',
    'LImG0QPABV': 'LImG0QPABV.QXHMarketplace', 'jAfAs7yVDX': 'jAfAs7yVDX.TheSix',
    'yL49PNFmjW': 'yL49PNFmjW.PromotionApp', 'HupEmjIB4I': 'HupEmjIB4I.Glance',
    'GHI3a0zMSx': 'GHI3a0zMSx.XboxGamePass', 'IewQEY143t': 'IewQEY143t.GoogleDuoWeb',
    'AkhP5nCr24': 'AkhP5nCr24.GoogleAssistant', 'AQKO41xyKP': 'AQKO41xyKP.AmazonAlexa',
}
BACKUPS = {
    'optional-apps.tar': 'c435b31914baae308fd43e9a7a853fcbd1fd1f77278d0a3544f992b3e91c8f2e',
    'package-db.sqlite': '1e2abb22b6254149434b414ad118dc412c9a8cbd4724f8cb1918548b9cc0314d',
    'was-db.sqlite': 'b30b100464515e95d5389a6a57c329e01cbe2e564983cceac5579fc19709ece0',
}
CFG = {'tv_host': '192.0.2.11', 'expected_model': 'QN85QN90AAFXZA', 'expected_platform': '21_NIKEM2_QTV'}


def connect_db(path):
    return sqlite3.connect('file:' + str(path) + '?mode=ro', uri=True)


def validate_target(db, original, package):
    if package not in TARGETS:
        raise ValueError('Package is outside the fixed optional-app list')
    fields = 'package_type,package_removable,package_preload,package_readonly,package_system,package_version'
    expected = original.execute('SELECT '+fields+' FROM package_info WHERE package=?', (package,)).fetchone()
    current = db.execute('SELECT '+fields+' FROM package_info WHERE package=?', (package,)).fetchone()
    if current is None or expected is None or current != expected or current[:5] != ('wgt','true','false','false','false'):
        raise ValueError('Unexpected package type, version or protection flags: ' + package)
    if db.execute('SELECT 1 FROM package_dependency_info WHERE depends_on=? LIMIT 1', (package,)).fetchone():
        raise ValueError('Another package declares a dependency on ' + package)
    if db.execute('SELECT mainapp_id FROM package_info WHERE package=?', (package,)).fetchone() != (MAIN_APPS[package],):
        raise ValueError('Unexpected main app identity: ' + package)
    if not db.execute('SELECT 1 FROM package_app_info WHERE package=? LIMIT 1', (package,)).fetchone():
        raise ValueError('Missing application registration: ' + package)


def verify_scope(before, after, removed):
    for table, column in [('package_info','package'), ('package_app_info','package')]:
        old = {r[0] for r in before.execute('SELECT DISTINCT '+column+' FROM '+table)}
        new = {r[0] for r in after.execute('SELECT DISTINCT '+column+' FROM '+table)}
        if (old - new) != {removed}:
            raise RuntimeError('Unexpected package removal set in ' + table + ': ' + repr(old-new))
    old_apps = set(before.execute('SELECT app_id,package FROM package_app_info'))
    new_apps = set(after.execute('SELECT app_id,package FROM package_app_info'))
    if old_apps - new_apps != {row for row in old_apps if row[1] == removed}:
        raise RuntimeError('An unrelated app registration was removed or changed')
    if after.execute('PRAGMA integrity_check').fetchone() != ('ok',):
        raise RuntimeError('Package database integrity check failed')


def validate_catalog(db, original, package):
    query = 'SELECT id,tizen_id,is_removable,is_system,is_lock,install_state,is_app_available,is_need_reset FROM was.widgetinfo WHERE pkgname=?'
    current = db.execute(query, (package,)).fetchall()
    if len(current) != 1 or current != original.execute(query, (package,)).fetchall() or current[0][1:] != (MAIN_APPS[package],1,0,0,3,1,0):
        raise ValueError('Samsung catalog identity/protection check failed: ' + package)


def verify_catalog(before, after, removed):
    old = set(before.execute('SELECT id,pkgname,tizen_id FROM was.widgetinfo'))
    new = set(after.execute('SELECT id,pkgname,tizen_id FROM was.widgetinfo'))
    expected = {row for row in old if row[1] == removed}
    if not expected or old - new != expected or any(row[1] == removed for row in new):
        raise RuntimeError('Unexpected Samsung catalog removal set')
    if after.execute('PRAGMA was.integrity_check').fetchone() != ('ok',):
        raise RuntimeError('Samsung catalog integrity check failed')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('inspect', 'remove'))
    parser.add_argument('--package', choices=tuple(TARGETS), help='Operate on one allowlisted package')
    args = parser.parse_args()
    os.umask(0o077)
    toolkit = Path.home() / '.local/share/samsung-tv-research'
    backup = toolkit / 'qn90a/app-cleanup-backup'
    for name, expected in BACKUPS.items():
        path = backup / name
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise SystemExit('Verified private backup required: ' + name)
    sys.path.insert(0, str(toolkit))
    from samsung_tv import device, capture, SdbClient
    callback = device(CFG)
    client = SdbClient(toolkit / 'bin/sdb', CFG['tv_host'])
    client.connect(); client.require_device()
    session = backup / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    session.mkdir()
    remote = '/home/owner/share/tmp/sdk_tools/qn90a-cleanup-readback.db'
    remote_was = '/home/owner/share/tmp/sdk_tools/qn90a-cleanup-was-readback.db'

    def snapshot(label):
        capture(CFG, callback, '''set -eu
grep -q '^Version=T-NKM2AKUC-2301.1;' /etc/prd_info.ini
test "$(vconftool get memory/menu/network/airplay_status)" = 'memory/menu/network/airplay_status, value = ready (String)'
test "$(vconftool get memory/appfw/current_fullscreen_appid)" = 'memory/appfw/current_fullscreen_appid, value = MiniHub001.Hub (String)'
sqlite3 -cmd '.timeout 3000' /opt/dbspace/.pkgmgr_parser.db '.backup ''' + remote + "'\n" +
                "sqlite3 -cmd '.timeout 3000' /opt/dbspace/.webappservice.db '.backup " + remote_was + "'\n", 15, 'qn90a-cleanup-'+label)
        local = session / (label + '.sqlite')
        client.pull(PurePosixPath(remote), local)
        was_local = session / (label + '-was.sqlite')
        client.pull(PurePosixPath(remote_was), was_local)
        db = connect_db(local)
        db.execute('ATTACH DATABASE ? AS was', ('file:' + str(was_local) + '?mode=ro',))
        return db

    original = connect_db(backup / 'package-db.sqlite')
    original.execute('ATTACH DATABASE ? AS was', ('file:' + str(backup / 'was-db.sqlite') + '?mode=ro',))
    current = snapshot('before')
    packages = [args.package] if args.package else list(TARGETS)
    pending = []
    for package in packages:
        if not current.execute('SELECT 1 FROM package_info WHERE package=?', (package,)).fetchone():
            if current.execute('SELECT 1 FROM package_app_info WHERE package=?', (package,)).fetchone() or current.execute('SELECT 1 FROM was.widgetinfo WHERE pkgname=?', (package,)).fetchone():
                raise RuntimeError('Partial removal found; inspect before continuing: ' + package)
            print(TARGETS[package] + ': already absent'); continue
        validate_target(current, original, package)
        validate_catalog(current, original, package)
        pending.append(package)
        print(TARGETS[package] + ': eligible')
    if args.mode == 'remove':
        for package in pending:
            validate_target(current, original, package)
            validate_catalog(current, original, package)
            # Fixed native operation; never retry an uncertain result automatically.
            spec = importlib.util.spec_from_file_location('qn90a_root', Path(__file__).with_name('root-check.py'))
            root = importlib.util.module_from_spec(spec); spec.loader.exec_module(root)
            operation_error = None
            try:
                root.run('cleanup-' + str(list(TARGETS).index(package)))
            except Exception as error:
                operation_error = error
            after = snapshot('after-' + package)
            if operation_error:
                print('Root operation reported: ' + str(operation_error), flush=True)
                raise RuntimeError('Operation failed or uncertain; inspect saved readback before continuing') from operation_error
            verify_scope(current, after, package)
            verify_catalog(current, after, package)
            capture(CFG, callback, 'set -eu\ntest ! -e /opt/usr/apps/' + package +
                    '\ntest ! -e /opt/share/packages/' + package + '.xml\n', 15, 'qn90a-cleanup-files-' + package)
            current.close(); current = after
            print('Verified removed: ' + TARGETS[package], flush=True)
    current.close(); original.close()
    scratch = (remote, remote + '-journal', remote_was, remote_was + '-journal')
    capture(CFG, callback, 'set -eu\nrm -f ' + ' '.join(scratch) + '\n', 15, 'qn90a-cleanup-readback-cleanup')
    print('Private evidence: ' + str(session))


if __name__ == '__main__':
    main()
