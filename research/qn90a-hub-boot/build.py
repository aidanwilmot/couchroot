#!/usr/bin/env python3
"""Build and normally sign the QN90A no-window boot relay; never install implicitly."""
from pathlib import Path
import hashlib,json,os,subprocess,zipfile
HERE=Path(__file__).resolve().parent
PRIVATE=Path.home()/'.local/share/samsung-tv-research/qn90a/hub-boot'
CLI=Path.home()/'.local/share/samsung-tv-research/tizen-sdk/cli/tools/ide/bin/tizen'
def build():
 os.umask(0o077);PRIVATE.mkdir(parents=True,exist_ok=True)
 subprocess.run(['dotnet','build',str(HERE/'relay/Boot.csproj'),'-c','Release','--nologo','-v','quiet'],check=True)
 artifacts=[HERE/'relay/bin/Release/netcoreapp3.1'/name for name in ('Boot.dll','Boot.deps.json','Boot.runtimeconfig.json')]
 if not all(p.is_file() for p in artifacts):raise RuntimeError('Missing runtime artifacts')
 pkg=PRIVATE/'MiniHubBoot-arm.tpk'
 with zipfile.ZipFile(pkg,'w',zipfile.ZIP_DEFLATED) as z:
  z.write(HERE/'relay/tizen-manifest.xml','tizen-manifest.xml')
  for p in artifacts:z.write(p,'bin/'+p.name)
 subprocess.run([str(CLI),'package','-t','tpk','-s','MinimalHubQN90A','--',str(pkg)],check=True)
 info={'package':str(pkg),'package_sha256':hashlib.sha256(pkg.read_bytes()).hexdigest(),'relay_sha256':hashlib.sha256((HERE/'relay/bin/Release/netcoreapp3.1/Boot.dll').read_bytes()).hexdigest()}
 info['artifacts']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in artifacts}
 (PRIVATE/'build.json').write_text(json.dumps(info,indent=2)+'\n');return info
if __name__=='__main__':print(json.dumps(build(),indent=2))
