#!/usr/bin/env python3
"""Replace only the previously recorded telemetry builds and restart AT-HUB."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
root=Path(__file__).resolve().parent
private=Path.home()/'.local/share/samsung-tv-research'
manifest=private/'telemetry/installed-hashes.json'
old=json.loads(manifest.read_text())
files={'Telemetry.dll':root.parent/'s90d-collector/bin/Release/net6.0/Telemetry.dll','Boot.telemetry.dll':root/'bin/helper/bin/Release/net6.0/Boot.dll'}
new={k:hashlib.sha256(v.read_bytes()).hexdigest() for k,v in files.items()}
for name,path in files.items():subprocess.run([str(private/'bin/sdb'),'-s','192.0.2.12:26101','push',str(path),'/home/owner/share/tmp/sdk_tools/'+name],check=True,stdout=subprocess.DEVNULL)
script='''set -eu
hash() { sha256sum "$1" | cut -d ' ' -f 1; }
'''
for name,target in [('Telemetry.dll','/opt/minimal-telemetry/Telemetry.dll'),('Boot.telemetry.dll','/opt/minimal-saver/Boot.dll')]:
 script+=f'''[ "$(hash {target})" = {old[name]} ]
[ "$(hash /home/owner/share/tmp/sdk_tools/{name})" = {new[name]} ]
[ ! -e {target}.telemetry-new ]
cp --preserve=all {target} {target}.telemetry-new
cat /home/owner/share/tmp/sdk_tools/{name} > {target}.telemetry-new
[ "$(hash {target}.telemetry-new)" = {new[name]} ]
'''
script+='systemctl stop AT-HUB.service\n'
for name,target in [('Telemetry.dll','/opt/minimal-telemetry/Telemetry.dll'),('Boot.telemetry.dll','/opt/minimal-saver/Boot.dll')]:
 script+=f'mv {target}.telemetry-new {target}\nrm /home/owner/share/tmp/sdk_tools/{name}\n'
script+='systemctl start AT-HUB.service\n'
with tempfile.TemporaryDirectory() as tmp:
 path=Path(tmp)/'update.sh';path.write_text(script);subprocess.run(['python3',str(root/'tv-op.py'),str(path)],check=True)
old.update(new);manifest.write_text(json.dumps(old,indent=2))
