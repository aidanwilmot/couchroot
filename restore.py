#!/usr/bin/env python3
"""Restore the recorded TV configuration using native APIs that preserve key permissions."""
from pathlib import Path
import os
import subprocess
import tempfile

def configure(mode):
    if mode not in ('stock', 'hub'):
        raise ValueError('Expected stock or hub')
    os.umask(0o077)
    root = Path(__file__).resolve().parent
    toolkit = Path.home() / '.local/share/samsung-tv-research'
    remote = '/home/owner/share/tmp/sdk_tools/MinimalHubControl.dll'
    with tempfile.TemporaryDirectory(prefix='hub-restore-', dir=toolkit) as temp:
        temp = Path(temp)
        output = temp / 'out'
        subprocess.run(['dotnet', 'build', str(root / 'native/HubControl.csproj'),
                        '-c', 'Release', '--nologo', '-v', 'quiet', '-o', str(output),
                        '-p:BaseIntermediateOutputPath=' + str(temp / 'obj') + '/'], check=True)
        # Verify this is still the configured model and developer host before uploading.
        subprocess.run([str(Path.home() / '.local/bin/samsung-tv'), 'status'], check=True)
        subprocess.run([str(toolkit / 'bin/sdb'), '-s', '192.0.2.12:26101',
                        'push', str(output / 'MinimalHubControl.dll'), remote], check=True)
        script = temp / 'restore.sh'
        script.write_text(('''set -eu
    trap 'rm -f /home/owner/share/tmp/sdk_tools/MinimalHubControl.dll' EXIT
    if [ MODE = hub ]; then test -d /opt/usr/apps/MiniHub001; fi
    current=$(vconftool get db/appfw/startup_appid)
    case "$current" in
      'db/appfw/startup_appid, value = MiniHub001.Hub (String)'|\
      'db/appfw/startup_appid, value = org.tizen.tv-viewer (String)') ;;
      *) echo 'Unexpected startup value; inspect before restoring.' >&2; exit 3 ;;
    esac
    /usr/bin/dotnet /home/owner/share/tmp/sdk_tools/MinimalHubControl.dll MODE
    for k in db/appfw/startup_appid db/appfw/home_appid db/menu/smart_hub/ontvsetting/auto_start; do vconftool get "$k"; done
    ''').replace('MODE', mode))
        subprocess.run([str(Path.home() / '.local/bin/samsung-tv'),
                        'run', str(script), '--timeout', '30'], check=True)

if __name__ == '__main__':
    configure('stock')
