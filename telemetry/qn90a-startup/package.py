#!/usr/bin/env python3
"""Build the service adapter and package the existing shared ARMv7 collector."""
from pathlib import Path
import argparse,hashlib,json,os,subprocess,tempfile,zipfile,sys
import xml.etree.ElementTree as ET
ET.register_namespace('','http://tizen.org/ns/packages')
os.umask(0o077)
repo=Path(__file__).resolve().parent
private=Path.home()/'.local/share/samsung-tv-research'
parser=argparse.ArgumentParser();parser.add_argument('--device',default='qn90a');parser.add_argument('--version');args=parser.parse_args()
sys.path.insert(0,str(repo.parents[1]/'research/s90d-telemetry'));from profiles import load
profiles=load();profile=profiles[args.device]
if profile['startup']!='launcher-service':raise SystemExit('Wrong startup profile')
framework=profile['framework']
collector=repo.parent/'s90d-collector/bin/Release'/framework/'Telemetry.dll'
if not collector.is_file():raise SystemExit('Build the netcoreapp3.1 shared collector first')
subprocess.run(['dotnet','build',str(repo/'Service.csproj'),'-c','Release','--nologo','-v','quiet','-p:TargetFramework='+framework],check=True)
subprocess.run(['dotnet','build',str(repo.parents[1]/'research/qn90a-telemetry-startup/bootstrap/Bootstrap.csproj'),'-c','Release','--nologo','-v','quiet','-p:TargetFramework='+framework],check=True)
build=Path(tempfile.mkdtemp(prefix='qn90a-telemetry-',dir=private/'signing/builds'))
pkg=build/'MiniTelemetry-arm.tpk'
with zipfile.ZipFile(pkg,'w',zipfile.ZIP_DEFLATED) as z:
 manifest_xml=ET.fromstring((repo/'tizen-manifest.xml').read_text())
 if args.version:manifest_xml.set('version',args.version)
 z.writestr('tizen-manifest.xml',ET.tostring(manifest_xml,encoding='utf-8',xml_declaration=True))
 for f in (repo/'bin/Release'/framework).glob('Service.*'):
  if f.suffix != '.pdb':z.write(f,'bin/'+f.name)
 for f in (repo.parents[1]/'research/qn90a-telemetry-startup/bootstrap/bin/Release'/framework).glob('Bootstrap.*'):
  if f.suffix != '.pdb':z.write(f,'bin/'+f.name)
 z.write(collector,'bin/Telemetry.dll')
subprocess.run([str(private/'tizen-sdk/cli/tools/ide/bin/tizen'),'package','-t','tpk','-s',profile.get('signing_profile','MinimalHubQN90A'),'--',str(pkg)],check=True)
manifest={'package':str(pkg),'sha256':hashlib.sha256(pkg.read_bytes()).hexdigest(),'collector_sha256':hashlib.sha256(collector.read_bytes()).hexdigest(),'service_sha256':hashlib.sha256((repo/'bin/Release'/framework/'Service.dll').read_bytes()).hexdigest()}
manifest['bootstrap_sha256']=hashlib.sha256((repo.parents[1]/'research/qn90a-telemetry-startup/bootstrap/bin/Release'/framework/'Bootstrap.dll').read_bytes()).hexdigest()
manifest['version']=manifest_xml.attrib['version']
(build/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
(private/'telemetry/devices'/args.device/'service-build.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(pkg)
