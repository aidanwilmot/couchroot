#!/usr/bin/env python3
"""Install, inspect, or roll back the S90D native splash compatibility helper."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('apply', 'status', 'rollback'))
    args = parser.parse_args()
    toolkit = Path.home() / '.local/share/samsung-tv-research'
    config = json.loads((toolkit / 'config.json').read_text())
    if config.get('tv_host') != '192.0.2.12':
        raise SystemExit('Private toolkit is not targeting the reviewed S90D.')
    root = Path(__file__).resolve().parents[2]
    script = (root / 'research/s90d-splash/helper.sh').read_text()
    if args.action == 'apply':
        artifact = root / 'research/s90d-splash/bin/helper/bin/Release/net6.0/Boot.dll'
        digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
        if ('replacement=' + digest) not in script:
            raise SystemExit('Helper build differs from reviewed installer.')
        subprocess.run([str(Path.home() / '.local/bin/samsung-tv'), 'status'], check=True)
        subprocess.run([str(toolkit / 'bin/sdb'), '-s', '192.0.2.12:26101',
                        'push', str(artifact), '/home/owner/share/tmp/sdk_tools/MinimalHubSplash.dll'], check=True)
    with tempfile.TemporaryDirectory(prefix='s90d-splash-') as temp:
        operations = Path(temp) / 'operations.json'
        operations.write_text(json.dumps([{
            'name': args.action + '.txt', 'kind': 'command', 'timeout': 20,
            'command': 'set -- ' + args.action + '\n' + script,
        }]))
        result = subprocess.run(['python3', str(toolkit / 'gather-dumps.py')],
                                env=dict(os.environ, DUMP_OPERATIONS_FILE=str(operations)),
                                capture_output=True, text=True)
        print(result.stdout, end='')
        if result.stderr:
            print(result.stderr, end='')
        # Resolve this invocation's output, never a concurrently replaced latest pointer.
        paths = [line.removeprefix('DUMP_DIRECTORY ') for line in result.stdout.splitlines()
                 if line.startswith('DUMP_DIRECTORY ')]
        if result.returncode or len(paths) != 1:
            raise SystemExit('Collector did not finish; inspect its evidence before retrying.')
        evidence = Path(paths[0])
        manifest = json.loads((evidence / 'manifest.json').read_text())
        records = manifest['operations']
        if not manifest['complete'] or len(records) != 1:
            raise SystemExit('Incomplete helper operation.')
        record = records[0]
        print((evidence / record['name']).read_text())
        if not record['verified'] or record['details'].get('exit') != 0:
            raise SystemExit(record['details'].get('stderr') or 'Helper operation failed.')


if __name__ == '__main__':
    main()
