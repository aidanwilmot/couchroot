#!/usr/bin/env python3
"""Operate the reversible S90D renderer overlay using the existing private toolkit."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
TOOLKIT = Path.home() / '.local/share/samsung-tv-research'
TARGET = '192.0.2.12:26101'
STOCK = '/usr/apps/com.samsung.tv.spotlight-ss/lib/arm/libgl-demo-app.so'

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['apply', 'rollback', 'enable-boot', 'update', 'disable-boot', 'preview', 'status'])
    args = parser.parse_args()
    if args.action == 'update':
        script = (HERE/'update.sh').read_text()
        payloads = {'libgl-demo-app.so': HERE/'bin/libgl-demo-app.so',
                    'Boot.dll': HERE/'boot/bin/Release/net6.0/Boot.dll'}
        for name, path in payloads.items():
            key = 'new' if name == 'libgl-demo-app.so' else 'newboot'
            if f'{key}={hashlib.sha256(path.read_bytes()).hexdigest()}' not in script:
                raise SystemExit(f'{name} differs from the reviewed updater; rebuild/review first.')
        subprocess.run([str(Path.home()/'.local/bin/samsung-tv'), 'status'], check=True)
        for name, path in payloads.items():
            result = subprocess.run([str(TOOLKIT/'bin/sdb'), '-s', TARGET, 'push', str(path),
                '/home/owner/share/tmp/sdk_tools/minimal-saver-update/'+name], check=True, capture_output=True, text=True)
            if '1 file(s) pushed' not in result.stdout + result.stderr:
                raise SystemExit(f'SDB did not confirm upload of {name}')
        command = 'nsenter -t 1 -m -- sh -c ' + shlex.quote(script)
    elif args.action == 'enable-boot':
        script = (HERE/'enable-boot.sh').read_text()
        payloads = {name: HERE/'boot/bin/Release/net6.0'/name
                    for name in ['Boot.dll', 'Boot.runtimeconfig.json', 'Boot.deps.json']}
        payloads['oneservice.patched'] = HERE/'bin/oneservice.patched'
        for name, path in payloads.items():
            if hashlib.sha256(path.read_bytes()).hexdigest() not in script:
                raise SystemExit(f'{name} differs from the reviewed installer; rebuild/review first.')
        subprocess.run([str(Path.home()/'.local/bin/samsung-tv'), 'status'], check=True)
        for name, path in payloads.items():
            result = subprocess.run([str(TOOLKIT/'bin/sdb'), '-s', TARGET, 'push', str(path),
                '/home/owner/share/tmp/sdk_tools/minimal-saver-boot/'+name], check=True, capture_output=True, text=True)
            if '1 file(s) pushed' not in result.stdout + result.stderr:
                raise SystemExit(f'SDB did not confirm upload of {name}')
        command = 'nsenter -t 1 -m -- sh -c ' + shlex.quote(script)
    elif args.action == 'disable-boot':
        command = 'nsenter -t 1 -m -- sh -c ' + shlex.quote((HERE/'disable-boot.sh').read_text())
    elif args.action == 'apply':
        binary = HERE / 'bin/libgl-demo-app.so'
        script = (HERE / 'apply.sh').read_text()
        digest = hashlib.sha256(binary.read_bytes()).hexdigest()
        if f'replacement={digest}' not in script:
            raise SystemExit('Build hash differs from reviewed apply.sh; review and update both scripts first.')
        subprocess.run([str(Path.home()/'.local/bin/samsung-tv'), 'status'], check=True)
        result = subprocess.run([str(TOOLKIT/'bin/sdb'), '-s', TARGET, 'push', str(binary),
            '/home/owner/share/tmp/sdk_tools/minimal-saver-renderer.so'], check=True, capture_output=True, text=True)
        if '1 file(s) pushed' not in result.stdout + result.stderr:
            raise SystemExit('SDB did not confirm upload')
        command = 'nsenter -t 1 -m -- sh -c ' + shlex.quote(script)
    elif args.action == 'rollback':
        command = 'nsenter -t 1 -m -- sh -c ' + shlex.quote((HERE/'disable-boot.sh').read_text() + '\n' + (HERE/'rollback.sh').read_text())
    elif args.action == 'preview':
        command = 'app_launcher -s com.samsung.tv.glscreensaver-launcher'
    else:
        command = f'''cat /proc/sys/kernel/random/boot_id
cat /opt/minimal-saver/last-boot.log 2>/dev/null || true
test ! -f /opt/minimal-saver/enabled || echo AUTOLOAD_ENABLED
sha256sum /opt/etc/systemd/oneservice
sha256sum {STOCK}
awk -v p={shlex.quote(STOCK)} '$5==p' /proc/1/mountinfo
ps -eo pid,uid,pcpu,comm | grep -E 'DN_spotlight|DN_ver-launcher' || true'''
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json') as operations:
        json.dump([{'name': args.action+'.txt', 'kind':'command', 'command':command, 'timeout':25}], operations)
        operations.flush()
        subprocess.run(['python3', str(TOOLKIT/'gather-dumps.py')], env={**os.environ, 'DUMP_OPERATIONS_FILE':operations.name}, check=True)
    evidence = Path((TOOLKIT/'latest-dump-path.txt').read_text().strip())
    manifest = json.loads((evidence/'manifest.json').read_text())
    print((evidence/(args.action+'.txt')).read_text())
    if not manifest['complete'] or any(not op['verified'] or op['details'].get('exit') != 0 for op in manifest['operations']):
        for op in manifest['operations']:
            print(op['details'].get('stderr', ''))
        raise SystemExit(f'Operation failed; inspect {evidence} before retrying.')

if __name__ == '__main__':
    main()
