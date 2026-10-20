#!/usr/bin/env python3
"""Identity-guarded QN90A boot relay install/status/rollback/reboot."""
import argparse,contextlib,hashlib,importlib.util,io,json,os,re,shlex,subprocess,sys,time
from datetime import datetime,timezone
from pathlib import Path
HERE=Path(__file__).resolve().parent
REPO=HERE.parents[1]
sys.path.insert(0,str(REPO))
from tvsetup.reboot import reboot_command
PRIVATE=Path.home()/'.local/share/samsung-tv-research'
STATE=PRIVATE/'qn90a/hub-boot'
REMOTE='/opt/minimal-hub-boot'
APP='/opt/usr/apps/MiniHubBoot/bin/Boot.dll'
DB='/opt/dbspace/.app-context.db'
STAGE='/home/owner/share/tmp/sdk_tools/HubBootControl.dll'
CLI=PRIVATE/'tizen-sdk/cli/tools/ide/bin/tizen'
SDB=PRIVATE/'bin/sdb'
SERIAL='192.0.2.11:26101'
Q=shlex.quote

def module(name,path):
 spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def run(args):subprocess.run([str(x) for x in args],check=True,timeout=90)

def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=['install','status','rollback','reboot']);args=parser.parse_args()
 os.umask(0o077);STATE.mkdir(parents=True,exist_ok=True)
 sys.path.insert(0,str(PRIVATE));from samsung_tv import device,capture
 cfg={'tv_host':'192.0.2.11','expected_model':'QN85QN90AAFXZA','expected_platform':'21_NIKEM2_QTV'}
 callback=device(cfg)
 guard="set -eu\ngrep -qx 'Version=T-NKM2AKUC-2301.1;' /etc/prd_info.ini\ntest \"$(uname -m)\" = armv7l\ntest -d /usr/share/dotnet/shared/Microsoft.NETCore.App/3.1.3\ntest \"$(sha256sum /usr/bin/dotnet-launcher | cut -d ' ' -f 1)\" = 5f33f4d63bc7eb5a09cdedf377398d6c2f4142e629a1f73921f31f08cb7791f3\n"
 capture(cfg,callback,guard,15,'qn90a-hub-boot-identity')
 sys.path.insert(0,str(REPO/'telemetry/s90d'))
 transport=module('telemetry_transport',REPO/'telemetry/s90d/manage-tv.py')
 def root(script):
  log=io.StringIO()
  try:
   with contextlib.redirect_stdout(log):transport.root_operation('qn90a',guard+script)
  finally:print(log.getvalue(),end='')
  return log.getvalue()
 def save(info):
  temporary=STATE/'installed.json.new';temporary.write_text(json.dumps(info,indent=2)+'\n');temporary.replace(STATE/'installed.json')
 def verify(info):
  artifacts=info.get('artifacts')
  if not isinstance(artifacts,dict) or set(artifacts)!= {'Boot.dll','Boot.deps.json','Boot.runtimeconfig.json'}:raise RuntimeError('Incomplete artifact ledger')
  if any(name not in ('Boot.dll','Boot.deps.json','Boot.runtimeconfig.json') or not re.fullmatch('[a-f0-9]{64}',digest) for name,digest in artifacts.items()):raise RuntimeError('Invalid artifact ledger')
  return ''.join(f'test "$(sha256sum /opt/usr/apps/MiniHubBoot/bin/{name} | cut -d \' \' -f 1)" = {digest}\n' for name,digest in artifacts.items())

 if args.action=='status':
  ledger=STATE/'installed.json'
  if ledger.exists():print('Local deployment:',ledger.read_text())
  root((HERE/'status.sh').read_text());return
 if args.action=='reboot':
  # Delayed once so the temporary root transport can restore its private mounts.
  # This has no postboot command and is never retried automatically.
  root("cat /proc/sys/kernel/random/boot_id /proc/uptime\n" + reboot_command("minimal-hub-reboot", "Owner-authorized Minimal Hub full reboot validation") + "echo Native-reboot-scheduled\n")
  return
 manifest=STATE/'installed.json'
 if args.action=='install':
  if manifest.exists():raise SystemExit('Already installed; use status, or rollback before reinstalling')
  # Check absence before building/installing; never replace an unknown package/rule.
  root(f'''test ! -e /opt/usr/apps/MiniHubBoot
test "$(sqlite3 {DB} "select count(*) from task_filter where appid='MiniHubBoot.Start';")" = 0
test "$(sqlite3 {DB} "select count(*) from managed_app where appid='MiniHubBoot.Start';")" = 0
''')
  info=module('boot_build',HERE/'build.py').build()
  package=Path(info['package'])
  if hashlib.sha256(package.read_bytes()).hexdigest()!=info['package_sha256']:raise SystemExit('Package drift')
  # Save recovery information before the first package or route mutation.
  info.update(phase='prepared',backup=REMOTE+'/context-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')+'.db')
  save(info)
  output=root(f"""test ! -L {REMOTE}
mkdir -p {REMOTE}
chmod 700 {REMOTE}
test ! -e {info['backup']}
sqlite3 {DB} '.backup {info['backup']}'
test "$(sqlite3 {info['backup']} 'pragma quick_check;')" = ok
echo BOOT_BACKUP_SHA=$(sha256sum {info['backup']} | cut -d ' ' -f 1)
""")
  info['backup_sha256']=re.search(r'BOOT_BACKUP_SHA=([a-f0-9]{64})',output)[1]
  info['phase']='package-installing';save(info)
  run([CLI,'install','-s',SERIAL,'-n',package.name,'--',package.parent])
  info['phase']='package-installed';save(info)
  root(verify(info))
 else:
  if not manifest.exists():raise SystemExit('No deployment ledger; inspect before rollback')
  info=json.loads(manifest.read_text())
  # A retry after a completed uninstall must also finish local ledger cleanup.
  output=root('if test -e /opt/share/packages/MiniHubBoot.xml; then\n'+verify(info)+'echo BOOT_APP_PRESENT=1\nelse\necho BOOT_APP_PRESENT=0\nfi\n')
  present='BOOT_APP_PRESENT=1' in output
  info['phase']='rolling-back';save(info)
 run(['dotnet','build',HERE/'control/Control.csproj','-c','Release','--nologo','-v','quiet'])
 run([SDB,'-s',SERIAL,'push',HERE/'control/bin/Release/netcoreapp3.1/Control.dll',STAGE])
 sql=(HERE/('install.sql' if args.action=='install' else 'rollback.sql')).read_text()
 inverse=(HERE/('rollback.sql' if args.action=='install' else 'install.sql')).read_text()
 script=f"trap 'rm -f {STAGE}' EXIT\n"
 if args.action=='rollback':
  # Exact guards apply if rows exist; absent rows are a valid partial rollback.
  script+=f"rows=$(sqlite3 {DB} \"select (select count(*) from task_filter where appid='MiniHubBoot.Start')+(select count(*) from managed_app where appid='MiniHubBoot.Start');\")\nif test \"$rows\" != 0; then\n"
 script+=f"sqlite3 -bail {DB} <<'SQL'\n{sql}SQL\n"
 if args.action=='rollback':script+='fi\n'
 if args.action=='install':
  script+=f"if ! /usr/bin/dotnet {STAGE}; then\nsqlite3 -bail {DB} <<'SQL'\n{inverse}SQL\n/usr/bin/dotnet {STAGE}\nexit 1\nfi\n"
 else:
  # On notification failure leave persisted removal in place. A retry always
  # repeats the native reload, even when the rows were already removed.
  script+=f"/usr/bin/dotnet {STAGE}\n"
 script+=f"test \"$(sqlite3 {DB} 'pragma quick_check;')\" = ok\n"
 if args.action=='install':
  info['phase']='installed'
  script+=f"printf '%s\\n' {Q(json.dumps(info))} > {REMOTE}/deployment.json\nchmod 600 {REMOTE}/deployment.json\n"
 else:script+=f"rm -f {REMOTE}/deployment.json\napp_launcher -k MiniHubBoot.Start || true\n"
 root(script)
 time.sleep(6) # documented native debounce; keep helper package until reload
 if args.action=='install':save(info)
 else:
  info['phase']='routes-removed';save(info)
  # Samsung TV CLI uninstall routes through the web catalog, which omits
  # this native TPK. Use the normal native package manager, with readback.
  if present:root(verify(info)+'pkgcmd -u -n MiniHubBoot --global\n')
  root('test ! -e /opt/share/packages/MiniHubBoot.xml\ntest ! -e /opt/usr/apps/MiniHubBoot/bin/Boot.dll\n')
  info['phase']='rolled-back';save(info)
  manifest.replace(STATE/'rolled-back.json')
 print('Complete. Run status; reboot explicitly to validate startup.')
if __name__=='__main__':main()
