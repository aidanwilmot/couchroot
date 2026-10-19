#!/usr/bin/env python3
"""Build the embedded native launcher twice and verify both managed TV targets."""
import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tvsetup.artifacts import Builder
from tvsetup.config import profile
from tvsetup.root_launcher import build

with tempfile.TemporaryDirectory(prefix='couchroot-launcher-') as tmp:
    hashes=[]
    for name in ('first','second'):
        folder=Path(tmp)/name
        builder=Builder(profile('qn90a'),{},folder/'logs')
        native=build(folder/'native',builder.command)
        record={'native':hashlib.sha256(native.read_bytes()).hexdigest()}
        for device in ('qn90a','s90d'):
            builder.profile=profile(device)
            output=folder/device
            builder.build_managed(ROOT/'research/autonomous-root/payload/SamsungTvRootAgent.csproj',output,native_app_launcher=native)
            record[device]=hashlib.sha256((output/'SamsungTvRootAgent.dll').read_bytes()).hexdigest()
        result=subprocess.check_output(['dotnet','run','--project',str(ROOT/'tests/root-agent-harness/Harness.csproj'),
            '-p:NativeAppLauncher='+str(native),'--','--native-resource'],cwd=ROOT,text=True)
        if 'NATIVE_RESOURCE_SHA256 '+record['native'] not in result:raise SystemExit('Embedded native bytes differ')
        hashes.append(record)
    if hashes[0]!=hashes[1]:raise SystemExit('Embedded launcher builds differ across output paths')
print('PASS source-built ARM launcher and both embedded TV workers are reproducible; embedded bytes verified')
