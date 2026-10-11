#!/usr/bin/env python3
"""Install the reviewed NAS receiver as a TrueNAS custom app; no credentials in git."""
import hashlib
import json
import os
from pathlib import Path
import secrets
import shlex
import ssl
import subprocess
root=Path(__file__).resolve().parent
private=Path.home()/'.local/share/samsung-tv-research/telemetry'
private.mkdir(mode=0o700,exist_ok=True)
os.umask(0o077)
ssh=['ssh','-i',str(Path.home()/'.ssh/tv_nas_ed25519'),'root@192.0.2.20']
base='/mnt/.ix-apps/app_mounts/netdata/config'
backend=base+'/s90d-receiver';plugins=base+'/custom-plugins.d'
if not (private/'receiver.json').exists():
 token=secrets.token_hex(32)
 (private/'receiver.json').write_text(json.dumps(dict(token=token,allowed_ip='192.0.2.12')))
 subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','3650','-subj','/CN=s90d-telemetry','-keyout',str(private/'server.key'),'-out',str(private/'server.crt')],check=True,capture_output=True)
 pin=hashlib.sha256(ssl.PEM_cert_to_DER_cert((private/'server.crt').read_text())).hexdigest()
 (private/'config.json').write_text(json.dumps(dict(endpoint='https://192.0.2.20:20490/v1/s90d',certificate_sha256=pin,token=token,dashboard_config_path='/opt/usr/home/owner/apps_rw/MiniHub001/data/telemetry.json')))
compose={'services':{'receiver':{
 'image':'netdata/netdata@sha256:21970e176031fdb9469503534d01b4dc2fe2c36d369a5a4be74b6ec5c8b7a5c3',
 'entrypoint':['/usr/bin/python3','-B','/config/receiver.py'],'user':'65534:201','read_only':True,
 'restart':'unless-stopped','init':True,'pids_limit':16,'mem_limit':'96m','cpus':0.25,
 'healthcheck':{'test':['CMD','/usr/bin/python3','-c','import socket; s=socket.create_connection(("127.0.0.1",8443),2); s.close()'],'interval':'30s','timeout':'5s','retries':3},
 'cap_drop':['ALL'],'security_opt':['no-new-privileges:true'],
 'ports':['192.0.2.20:20490:8443/tcp'],
 'volumes':[backend+':/config:ro',plugins+'/s90d-data:/data:rw'],
 'logging':{'driver':'json-file','options':{'max-size':'1m','max-file':'2'}}}}}
(private/'app-create.json').write_text(json.dumps(dict(app_name='s90d-telemetry',custom_app=True,custom_compose_config=compose)))
# Fresh install only. Refuse to replace any existing app files or plugin.
subprocess.run(ssh+['set -eu; test ! -e '+shlex.quote(backend)+'; test ! -e '+shlex.quote(plugins+'/s90d.plugin')+'; mkdir -m 0755 '+shlex.quote(backend)+' '+shlex.quote(plugins+'/s90d-code')+'; mkdir -m 0750 '+shlex.quote(plugins+'/s90d-data')+'; chown 65534:201 '+shlex.quote(plugins+'/s90d-data')],check=True)
for source,destination in [(root/'nas/receiver.py',backend+'/receiver.py'),(root/'nas/metrics.py',backend+'/metrics.py'),(root/'nas/metrics.py',plugins+'/s90d-code/metrics.py'),(private/'receiver.json',backend+'/receiver.json'),(private/'server.key',backend+'/server.key'),(private/'server.crt',backend+'/server.crt'),(private/'app-create.json',backend+'/app-create.json')]:
 subprocess.run(['scp','-q','-i',str(Path.home()/'.ssh/tv_nas_ed25519'),str(source),'root@192.0.2.20:'+destination],check=True)
subprocess.run(ssh+['set -eu; chmod 0644 '+backend+'/*.py '+backend+'/server.crt '+plugins+'/s90d-code/metrics.py; chown 65534:201 '+backend+'/receiver.json '+backend+'/server.key; chmod 0400 '+backend+'/receiver.json '+backend+'/server.key; midclt call -j app.create "$(cat '+backend+'/app-create.json)" >/dev/null'],check=True)
subprocess.run(['scp','-q','-i',str(Path.home()/'.ssh/tv_nas_ed25519'),str(root/'nas/s90d.plugin'),'root@192.0.2.20:'+plugins+'/s90d.plugin'],check=True)
subprocess.run(ssh+['chmod 0755 '+plugins+'/s90d.plugin; docker ps --filter label=com.docker.compose.project=ix-s90d-telemetry --format "{{.Names}} {{.Status}} {{.Ports}}"'],check=True)
print('NAS receiver installed; credentials retained privately.')
