#!/usr/bin/env python3
"""Offline host dependency check. Never contacts a TV or a NAS."""
import importlib.metadata
import json
import platform
import shutil
import subprocess
import sys
from pathlib import Path

root=Path(__file__).resolve().parents[1]
failures=[]
def check(ok,message):
    print(('OK: ' if ok else 'MISSING: ')+message)
    if not ok:failures.append(message)
check(sys.version_info >= (3,12),'Python 3.12+ (including the upstream transport)')
check(platform.system() in ('Darwin','Linux'),'macOS or Linux host; Windows/WSL not validated')
try: check(importlib.metadata.version('lxml')=='6.1.1','lxml 6.1.1; pip install -r tvsetup/requirements.txt')
except importlib.metadata.PackageNotFoundError:check(False,'lxml; pip install -r tvsetup/requirements.txt')
for name in ('git','openssl','dotnet','ssh','scp'):
    check(bool(shutil.which(name)),name+' on PATH')
if shutil.which('dotnet'):
    result=subprocess.run(['dotnet','--version'],cwd=root,text=True,capture_output=True,timeout=20)
    expected=json.loads((root/'global.json').read_text())['sdk']['version']
    check(result.returncode==0 and result.stdout.strip()==expected,'.NET SDK '+expected+' selected by global.json')
print('Optional component prerequisites: TIZEN or tizen on PATH; Samsung SDB for setup-toolkit.sh; emcc for QN90A saver; ARM compiler and owner-provided GLES library for S90D renderer.')
print('Certificate trust, Developer Mode and firmware resources are checked separately. This command performs no live validation.')
sys.exit(bool(failures))
