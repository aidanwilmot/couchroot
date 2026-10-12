#!/usr/bin/env python3
"""Provision the signed launcher-owned telemetry adapter with profile guards."""
import argparse,hashlib,importlib.util,json,os,shlex,subprocess,sys,tempfile,zipfile
from pathlib import Path
import xml.etree.ElementTree as ET
ET.register_namespace('','http://tizen.org/ns/packages')
HERE=Path(__file__).resolve().parent
REPO=HERE.parents[1]
PRIVATE=Path.home()/'.local/share/samsung-tv-research'
CLI=PRIVATE/'tizen-sdk/cli/tools/ide/bin/tizen'
DATA='/opt/usr/home/owner/apps_rw/MiniTelemetry/data'
RUNTIME='/tmp/minimal-telemetry-qn90a'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
quote=shlex.quote

def module():
 sys.path.insert(0,str(REPO/'research/s90d-telemetry'))
 spec=importlib.util.spec_from_file_location('telemetry_manage',REPO/'research/s90d-telemetry/manage-tv.py')
 result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result

def run(args,**kwargs):
 return subprocess.run(args,check=True,timeout=90,**kwargs)

def install(profile,package):
 run([str(CLI),'install','-s',profile['host']+':26101','-n',package.name,'--',str(package.parent)])

def main():
 raise SystemExit('Retired: use ./tv-setup plan/apply/verify --device DEVICE --components hub,telemetry; recovery uses ./tv-setup rollback --device DEVICE --run RUN_ID. See docs/guides/telemetry.md.')

if __name__=='__main__':main()
