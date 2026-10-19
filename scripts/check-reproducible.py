#!/usr/bin/env python3
"""Compare unsigned builds in this checkout and a source-only temporary copy."""
import hashlib
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

root=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--component',choices=('web','managed','all'),default='all',
                    help='Select unsigned web packaging, managed DLLs, or both (default)')
component=parser.parse_args().component
scripts=[]
if component in ('managed','all'):scripts.append('scripts/build-native.py')
if component in ('web','all'):scripts.append('scripts/package.py')
files=subprocess.check_output(['git','ls-files','-z'],cwd=root).decode().split('\0')
with tempfile.TemporaryDirectory(prefix='tv-source-build-') as tmp:
    clean=Path(tmp).resolve()
    for name in filter(None,files):
        source=root/name
        if source.is_symlink():raise SystemExit('Refusing symlink in source snapshot: '+name)
        if not source.is_file():raise SystemExit('Tracked source missing: '+name)
        destination=clean/name;destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(source,destination)
    for directory in (root,clean):
        env=dict(os.environ,SAMSUNG_TV_TOOLKIT=str(clean/'absent-toolkit'),TV_SETUP_STATE=str(clean/'private-state'))
        for script in scripts:
            subprocess.run([sys.executable,script],cwd=directory,env=env,check=True,timeout=600)
    report={}
    if component in ('managed','all'):
        original=json.loads((root/'dist/native-manifest.json').read_text())
        reproduced=json.loads((clean/'dist/native-manifest.json').read_text())
        if original!=reproduced:raise SystemExit('Managed manifest differs across source paths; release blocked')
        report.update(native_assemblies=len(original['files']),native_cross_path_match=True)
    if component in ('web','all'):
        original_package=(root/'dist/MinimalHub-unsigned.wgt').read_bytes()
        if original_package!=(clean/'dist/MinimalHub-unsigned.wgt').read_bytes():raise SystemExit('Unsigned package is not reproducible')
        report.update(unsigned_package_sha256=hashlib.sha256(original_package).hexdigest(),unsigned_package_match=True)
    name='reproducibility.json' if component=='all' else 'reproducibility-'+component+'.json'
    (root/'dist'/name).write_text(json.dumps(report,indent=2)+'\n')
    print('Source-only cross-path '+component+' builds match. No signing or hardware validation performed.')
