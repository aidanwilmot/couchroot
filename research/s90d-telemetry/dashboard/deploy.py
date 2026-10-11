#!/usr/bin/env python3
"""Add the read-only dashboard service, preserving the receiver's current app settings."""
import json
import os
from pathlib import Path
import shlex
import subprocess
import time
root=Path(__file__).resolve().parent
private=Path.home()/'.local/share/samsung-tv-research/telemetry/dashboard'
private.mkdir(parents=True,exist_ok=True,mode=0o700)
os.umask(0o077)
ssh=['ssh','-i',str(Path.home()/'.ssh/tv_nas_ed25519'),'root@192.0.2.20']
base='/mnt/.ix-apps/app_mounts/netdata/config'
# The middleware returns the current compose configuration, so previous receiver edits survive.
result=subprocess.run(ssh+['midclt call app.config s90d-telemetry'],check=True,capture_output=True,text=True)
config=json.loads(result.stdout)
(private/('app-before-'+str(int(time.time()))+'.json')).write_text(json.dumps(config,indent=2))
compose=config
if 'services' not in compose:raise SystemExit('Unexpected custom app configuration; review before update')
if 'dashboard' in compose['services']:raise SystemExit('Dashboard already exists; inspect before replacing')
code=base+'/s90d-dashboard'
subprocess.run(ssh+['test ! -e '+shlex.quote(code)+' && mkdir -m 0755 '+shlex.quote(code)],check=True)
for name in ('server.py','index.html','dashboard.css','dashboard.js'):
 subprocess.run(['scp','-q','-i',str(Path.home()/'.ssh/tv_nas_ed25519'),str(root/name),'root@192.0.2.20:'+code+'/'+name],check=True)
subprocess.run(ssh+['chmod 0644 '+code+'/*'],check=True)
compose['services']['dashboard']={
 'image':compose['services']['receiver']['image'],
 'entrypoint':['/usr/bin/python3','-B','/dashboard/server.py'],
 'user':'65534:201','read_only':True,'restart':'unless-stopped','init':True,
 'pids_limit':32,'mem_limit':'96m','cpus':0.25,'cap_drop':['ALL'],
 'security_opt':['no-new-privileges:true'],'ports':['192.0.2.20:20491:8080/tcp'],
 'volumes':[code+':/dashboard:ro',base+'/custom-plugins.d/s90d-data:/data:ro'],
 'healthcheck':{'test':['CMD','/usr/bin/python3','-c','import urllib.request; urllib.request.urlopen("http://127.0.0.1:8080/health",timeout=2).read()'],'interval':'30s','timeout':'5s','retries':3},
 'logging':{'driver':'json-file','options':{'max-size':'1m','max-file':'2'}}}
update=private/'app-update.json';update.write_text(json.dumps({'custom_compose_config':compose}))
subprocess.run(['scp','-q','-i',str(Path.home()/'.ssh/tv_nas_ed25519'),str(update),'root@192.0.2.20:'+code+'/app-update.json'],check=True)
subprocess.run(ssh+['midclt call -j app.update s90d-telemetry "$(cat '+code+'/app-update.json)" >/dev/null'],check=True)
print('TV dashboard: http://192.0.2.20:20491/')
