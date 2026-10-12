#!/usr/bin/env python3
"""Guarded Home integration for the owner’s QN85QN90AAFXZA, firmware 2301.1."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['query', 'overlay', 'restore-overlay', 'enable', 'restore'])
    args = parser.parse_args()
    os.umask(0o077)
    repo = Path(__file__).resolve().parents[2]s[2]
    toolkit = Path.home() / '.local/share/samsung-tv-research'
    sys.path.insert(0, str(toolkit))
    from samsung_tv import device, capture
    cfg = {'tv_host': '192.0.2.11', 'expected_model': 'QN85QN90AAFXZA',
           'expected_platform': '21_NIKEM2_QTV'}
    callback = device(cfg)
    guard = "set -eu\ngrep -q '^Version=T-NKM2AKUC-2301.1;' /etc/prd_info.ini\n"
    capture(cfg, callback, guard, 10, 'qn90a-firmware-guard')
    with tempfile.TemporaryDirectory(prefix='qn90a-control-', dir=toolkit) as folder:
        folder = Path(folder)
        output = folder / 'out'
        subprocess.run(['dotnet', 'build', str(repo / 'tools/dotnet/QN90AControl.csproj'),
                        '-c', 'Release', '--nologo', '-v', 'quiet', '-o', str(output),
                        '-p:BaseIntermediateOutputPath=' + str(folder / 'obj') + '/'], check=True)
        remote = '/home/owner/share/tmp/sdk_tools/QN90AMinimalHubControl.dll'
        subprocess.run([str(toolkit / 'bin/sdb'), '-s', '192.0.2.11:26101', 'push',
                        str(output / 'QN90AMinimalHubControl.dll'), remote], check=True)
        script = "trap 'rm -f " + remote + "' EXIT\n" + guard
        if args.mode in ('overlay', 'enable'):
            script += 'test -d /opt/usr/apps/MiniHub001\n'
        script += '/usr/bin/dotnet ' + remote + ' ' + args.mode + '\n'
        capture(cfg, callback, script, 25, 'qn90a-' + args.mode)


if __name__ == '__main__':
    main()
