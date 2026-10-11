#!/usr/bin/env python3
"""Restore the pre-telemetry helper, retaining the working splash/saver fixes."""
import json
from pathlib import Path
import subprocess
import tempfile
root=Path(__file__).resolve().parent
private=Path.home()/'.local/share/samsung-tv-research/telemetry'
installed=json.loads((private/'installed-hashes.json').read_text())
script='''set -eu
hash() { sha256sum "$1" | cut -d ' ' -f 1; }
root=/opt/minimal-telemetry
live=/opt/minimal-saver/Boot.dll
[ ! -L "$root" ] && [ ! -L "$root/Boot.before.dll" ]
[ "$(hash "$root/Boot.before.dll")" = 4a6fdb3d979ab13ed8d38b2bc6e1b9b94e5a04294312d0f9b50cc7f1f0a6c987 ]
[ "$(hash "$live")" = CURRENT ]
[ ! -e "$live.telemetry-restore" ]
cp --preserve=all "$root/Boot.before.dll" "$live.telemetry-restore"
rm -f "$root/enabled"
systemctl stop AT-HUB.service
mv "$live.telemetry-restore" "$live"
sha256sum "$live"
echo 'Telemetry stopped; previous splash/screensaver helper restored'
'''.replace('CURRENT',installed['Boot.telemetry.dll'])
with tempfile.TemporaryDirectory() as tmp:
 path=Path(tmp)/'rollback.sh';path.write_text(script)
 subprocess.run(['python3',str(root/'tv-op.py'),str(path)],check=True)
