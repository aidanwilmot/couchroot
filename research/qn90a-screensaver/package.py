#!/usr/bin/env python3
"""Stage and sign the standalone QN90A saver with the existing private profile."""
from pathlib import Path
import hashlib, json, os, shutil, subprocess, tempfile
os.umask(0o077)
source = Path(__file__).resolve().parent / 'web'
private = Path.home() / '.local/share/samsung-tv-research'
for name in ('core.js', 'shaders.js'):
    if not (source / name).is_file():
        raise SystemExit('Run build-web.sh with Emscripten first')
build = Path(tempfile.mkdtemp(prefix='qn90a-saver-', dir=private / 'signing/builds'))
stage = build / 'web'
shutil.copytree(source, stage)
with (build / 'sign.log').open('w') as log:
    subprocess.run([str(private / 'tizen-sdk/cli/tools/ide/bin/tizen'), 'package', '-t', 'wgt',
                    '-s', 'MinimalHubQN90A', '-o', str(build), '--', str(stage)],
                   stdout=log, stderr=subprocess.STDOUT, check=True)
package = build / 'AsteroidsSaver.wgt'
(build / 'Asteroids Screensaver.wgt').rename(package)
(build / 'manifest.json').write_text(json.dumps({'package': package.name, 'profile': 'MinimalHubQN90A',
    'sha256': hashlib.sha256(package.read_bytes()).hexdigest(), 'bytes': package.stat().st_size}, indent=2)+'\n')
print(package)
