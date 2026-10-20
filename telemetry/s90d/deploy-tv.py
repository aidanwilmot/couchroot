#!/usr/bin/env python3
"""Install an exact-hash telemetry helper, preserving splash and screensaver behavior."""
import hashlib
from pathlib import Path
import subprocess
import tempfile
root=Path(__file__).resolve().parent
private=Path.home()/'.local/share/samsung-tv-research'
files={'Telemetry.dll':root/'collector/bin/Release/net6.0/Telemetry.dll','Boot.telemetry.dll':root/'bin/helper/bin/Release/net6.0/Boot.dll','telemetry-config.json':private/'telemetry/config.json'}
sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
expected='4a6fdb3d979ab13ed8d38b2bc6e1b9b94e5a04294312d0f9b50cc7f1f0a6c987'
for name,path in files.items():
 subprocess.run([str(private/'bin/sdb'),'-s','192.0.2.12:26101','push',str(path),'/home/owner/share/tmp/sdk_tools/'+name],check=True,stdout=subprocess.DEVNULL)
script='''set -eu
[ "$(id -u)" = 0 ]
grep -qx 'Version=T-PTMDAKUC-0090-2130.0;' /etc/prd_info.ini
root=/opt/minimal-telemetry
live=/opt/minimal-saver/Boot.dll
stage=/home/owner/share/tmp/sdk_tools
hash() { sha256sum "$1" | cut -d ' ' -f 1; }
[ ! -e "$root" ] && [ ! -L "$root" ]
[ ! -L "$live" ]
[ "$(hash "$live")" = "EXPECTED" ]
[ -s /opt/usr/home/owner/apps_rw/MiniHub001/data/telemetry.json ]
mkdir -m 0700 "$root"
cp --preserve=all "$live" "$root/Boot.before.dll"
'''.replace('EXPECTED',expected)
for name,path in files.items():
 target={'Telemetry.dll':'/opt/minimal-telemetry/Telemetry.dll','Boot.telemetry.dll':'/opt/minimal-saver/Boot.dll.telemetry-new','telemetry-config.json':'/opt/minimal-telemetry/config.json'}[name]
 script+=f'''[ "$(hash "$stage/{name}")" = "{sha(path)}" ]
cp --preserve=all "$live" "{target}"
cat "$stage/{name}" > "{target}"
[ "$(hash "{target}")" = "{sha(path)}" ]
rm "$stage/{name}"
'''
script+='''mv "$live.telemetry-new" "$live"
: > "$root/enabled"
chmod 0600 "$root/enabled"
systemctl start AT-HUB.service
sha256sum "$live" "$root/Telemetry.dll" "$root/Boot.before.dll"
systemctl show AT-HUB.service -p ActiveState -p MainPID
'''
with tempfile.TemporaryDirectory() as temporary:
 path=Path(temporary)/'install.sh';path.write_text(script)
 subprocess.run(['python3',str(root/'tv-op.py'),str(path)],check=True)
(private/'telemetry/installed-hashes.json').write_text(__import__('json').dumps({name:sha(path) for name,path in files.items()},indent=2))
