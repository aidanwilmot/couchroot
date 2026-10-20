#!/usr/bin/env python3
"""Check QN90A saver builds across source paths; never enroll new trusted bytes."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

root=Path(__file__).resolve().parents[1]
version=subprocess.check_output(['emcc','--version'],text=True)
if not re.search(r'\b3\.1\.64\b',version.splitlines()[0]):
    raise SystemExit('Use Emscripten 3.1.64 (emscripten/emsdk:3.1.64); other versions are not reviewed')
sources=('qn90a-screensaver/core.c','qn90a-screensaver/fragment.glsl',
         'qn90a-screensaver/build-web.sh','system-screensaver/renderer.c',
         'system-screensaver/simulation.h','system-screensaver/mesh.h')
outputs=('core.js','shaders.js')
with tempfile.TemporaryDirectory(prefix='saver-source-') as temporary:
    clean=Path(temporary)
    for name in sources:
        destination=clean/'native'/name
        destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(root/'native'/name,destination)
    (clean/'native/qn90a-screensaver/web').mkdir()
    builds=[]
    for directory in (root,clean):
        subprocess.run(['sh','native/qn90a-screensaver/build-web.sh'],cwd=directory,check=True,timeout=180)
        builds.append({name:hashlib.sha256((directory/'native/qn90a-screensaver/web'/name).read_bytes()).hexdigest() for name in outputs})
    if builds[0]!=builds[1]:raise SystemExit('Saver output differs across source paths; release blocked')
reviewed=json.loads((root/'tvsetup/profiles/qn90a.json').read_text())['saver_generated']
matches={name:digest==reviewed[name] for name,digest in builds[0].items()}
out=root/'dist';out.mkdir(exist_ok=True)
(out/'saver-reproducibility.json').write_text(json.dumps(dict(emscripten='3.1.64',cross_path_match=True,
    files=builds[0],reviewed_digest_matches=matches),indent=2)+'\n')
print('Saver source-only cross-path builds match. Reviewed digest matches: '+json.dumps(matches))
print('Compilation is not hardware acceptance. Profile pins remain unchanged; review any differing bytes before hardware validation.')
