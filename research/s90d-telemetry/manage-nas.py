#!/usr/bin/env python3
"""Back up and update telemetry files without replacing the live TrueNAS app config."""
import argparse, hashlib, json, os, secrets, shlex, ssl, subprocess, time
from pathlib import Path
from profiles import load as load_profiles
R=Path(__file__).resolve().parent
P=Path.home()/'.local/share/samsung-tv-research/telemetry'
BASE='/mnt/.ix-apps/app_mounts/netdata/config'
SSH=['ssh','-o','ConnectTimeout=8','-i',str(Path.home()/'.ssh/tv_nas_ed25519'),'root@192.0.2.20']
def remote(command):return subprocess.check_output(SSH+[command],text=True)
def copy(path,target):subprocess.run(['scp','-q','-i',str(Path.home()/'.ssh/tv_nas_ed25519'),str(path),'root@192.0.2.20:'+target],check=True)
def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=['update','status','rollback']);parser.add_argument('--backup');a=parser.parse_args();os.umask(0o077)
 if a.action=='status':
  print(remote('docker ps --filter label=com.docker.compose.project=ix-s90d-telemetry --format "{{.Names}} {{.Status}}"'));return
 if a.action=='rollback':
  if not a.backup or not a.backup.isdigit():raise SystemExit('Provide --backup timestamp printed by update')
  location=BASE+'/telemetry-backups/'+a.backup
  print(remote('test -f '+location+'/before.tar && tar -xf '+location+'/before.tar -C '+BASE+' && docker restart ix-s90d-telemetry-receiver-1 ix-s90d-telemetry-dashboard-1'))
  ledger=P/'shared/deployed-hashes.json'
  if ledger.exists():
   ledger.write_text(json.dumps({target:remote('sha256sum '+shlex.quote(BASE+'/'+target)).split()[0] for target in json.loads(ledger.read_text())},indent=2))
  restart_plugin();return
 ledger=P/'shared/deployed-hashes.json'
 if ledger.exists():
  for target,digest in json.loads(ledger.read_text()).items():
   actual=remote('sha256sum '+shlex.quote(BASE+'/'+target)).split()[0]
   if actual!=digest:raise SystemExit('Deployed artifact changed: '+target)
 before=json.loads(remote('midclt call app.config s90d-telemetry'))
 if not {'receiver','dashboard'}<=before.get('services',{}).keys():raise SystemExit('Unexpected live app; inspect first')
 stamp=str(int(time.time()));backup=P/'shared'/stamp;backup.mkdir(parents=True,mode=0o700)
 (backup/'app-before.json').write_text(json.dumps(before,indent=2))
 pairing=json.loads(remote('cat '+BASE+'/s90d-receiver/receiver.json'))
 records=pairing.get('devices',{'s90d':pairing})
 profiles=load_profiles()
 for identity,profile in profiles.items():
  if identity not in records:records[identity]=dict(token=secrets.token_hex(32),allowed_ip=profile['host'])
  if records[identity]['allowed_ip']!=profile['host']:raise SystemExit('IP identity conflict')
 pairing={'devices':records};(backup/'receiver.json').write_text(json.dumps(pairing))
 cert=remote('cat '+BASE+'/s90d-receiver/server.crt')
 pin=hashlib.sha256(ssl.PEM_cert_to_DER_cert(cert)).hexdigest()
 for identity,profile in profiles.items():
  path=P/'devices'/identity;path.mkdir(parents=True,exist_ok=True,mode=0o700)
  cfg=dict(device_id=identity,endpoint='https://192.0.2.20:20490/v1/devices/'+identity,token=records[identity]['token'],certificate_sha256=pin,dashboard_config_path=profile.get('dashboard_config_path','/opt/usr/home/owner/apps_rw/MiniHub001/data/telemetry.json'),firmware=profile['firmware'],runtime_version=profile['runtime'],startup=profile['startup'])
  (path/'config.json').write_text(json.dumps(cfg))
 public={id:{k:p[k] for k in ('name','chart_prefix','snapshot')} for id,p in profiles.items()}
 (backup/'devices.json').write_text(json.dumps(public))
 location=BASE+'/telemetry-backups/'+stamp
 registry=BASE+'/custom-plugins.d/s90d-data/devices.json'
 registry_backup=' custom-plugins.d/s90d-data/devices.json' if remote('test -f '+registry+' && echo yes || true').strip()=='yes' else ''
 remote('mkdir -p '+location+' && chmod 0700 '+BASE+'/telemetry-backups '+location+' && tar -cf '+location+'/before.tar -C '+BASE+' s90d-receiver s90d-dashboard custom-plugins.d/s90d.plugin custom-plugins.d/s90d-code'+registry_backup+' && cp -p '+BASE+'/custom-plugins.d/s90d-data/latest.json '+location+'/latest-before.json')
 # Never mount the public device registry alongside receiver secrets.
 files={R/'nas/receiver.py':'s90d-receiver/receiver.py',R/'nas/metrics.py':'s90d-receiver/metrics.py',R/'nas/s90d.plugin':'custom-plugins.d/s90d.plugin',backup/'receiver.json':'s90d-receiver/receiver.json',backup/'devices.json':'custom-plugins.d/s90d-data/devices.json'}
 for name in ('server.py','index.html','dashboard.js','dashboard.css'):files[R/'dashboard'/name]='s90d-dashboard/'+name
 for source,target in files.items():
  dest=BASE+'/'+target;copy(source,dest+'.new')
  digest=hashlib.sha256(source.read_bytes()).hexdigest()
  mode='0400' if target.endswith('receiver.json') else '0755' if target.endswith('.plugin') else '0644'
  remote('test "$(sha256sum '+dest+'.new | cut -d " " -f 1)" = '+digest+' && chown 65534:201 '+dest+'.new && chmod '+mode+' '+dest+'.new && mv '+dest+'.new '+dest)
 copy(R/'nas/metrics.py',BASE+'/custom-plugins.d/s90d-code/metrics.py.new')
 remote('test "$(sha256sum '+BASE+'/custom-plugins.d/s90d-code/metrics.py.new | cut -d " " -f 1)" = '+hashlib.sha256((R/'nas/metrics.py').read_bytes()).hexdigest()+' && chmod 0644 '+BASE+'/custom-plugins.d/s90d-code/metrics.py.new && mv '+BASE+'/custom-plugins.d/s90d-code/metrics.py.new '+BASE+'/custom-plugins.d/s90d-code/metrics.py')
 after=json.loads(remote('midclt call app.config s90d-telemetry'))
 if after!=before:raise SystemExit('App changed concurrently; inspect before restart')
 print(remote('docker restart ix-s90d-telemetry-receiver-1 ix-s90d-telemetry-dashboard-1'))
 hashes={target:hashlib.sha256(source.read_bytes()).hexdigest() for source,target in files.items() if source.suffix in ('.py','.js','.html','.css','.plugin')}
 hashes['custom-plugins.d/s90d-code/metrics.py']=hashlib.sha256((R/'nas/metrics.py').read_bytes()).hexdigest()
 ledger.write_text(json.dumps(hashes,indent=2))
 restart_plugin();print('Updated; preserved live app configuration and Netdata DB. Rollback backup:',stamp)
def restart_plugin():
 # Only our external plugin restarts; the Netdata daemon and database stay running.
 remote("pids=$(pgrep -f '^/usr/bin/python3 .*s90d.plugin|^/usr/bin/python3 /etc/netdata/custom-plugins.d/s90d.plugin|^python3 .*s90d.plugin' || true); if test -n \"$pids\"; then kill $pids; fi")
if __name__=='__main__':main()
