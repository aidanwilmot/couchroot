"""Shared receiver/dashboard maintenance without replaying a historical compose file."""
import hashlib
import json
from pathlib import Path
import re
import shlex
import ssl
from .common import PRIVATE, REPO, Refused, atomic_json, run, sha
from .config import profile
from .planner import Action
from .transport import hash_guard
from .staging import clear_verified_stage

BASE='/mnt/.ix-apps/app_mounts/netdata/config'
SSH_OPTIONS=['-o','BatchMode=yes','-o','ConnectTimeout=8','-o','StrictHostKeyChecking=yes']
Q=shlex.quote
CODE=REPO/'research/s90d-telemetry'
FILES={
 's90d-receiver/receiver.py':CODE/'nas/receiver.py',
 's90d-receiver/metrics.py':CODE/'nas/metrics.py',
 's90d-receiver/inspector.py':CODE/'nas/inspector.py',
 'custom-plugins.d/s90d.plugin':CODE/'nas/s90d.plugin',
 'custom-plugins.d/s90d-code/metrics.py':CODE/'nas/metrics.py',
 'custom-plugins.d/s90d-code/inspector.py':CODE/'nas/inspector.py',
 **{'s90d-dashboard/'+name:CODE/'dashboard'/name for name in ('server.py','index.html','dashboard.js','dashboard.css','inspector.js')},
}


class NAS:
    def __init__(self,folder,settings=None):
        self.folder=folder
        self.settings=settings or {}
        self.base=self.settings.get('base',BASE)

    def configured(self):
        if not self.settings: raise Refused('This component requires explicit NAS settings in site.json; exclude telemetry,dashboard for TV-only setup')
    def source_bytes(self,target,source):
        data=source.read_bytes()
        origin=self.settings.get('netdata_url')
        if origin:
            if target=='s90d-dashboard/server.py':
                data=data.replace(b"'http://netdata:19999'",repr(origin).encode())
            elif target=='s90d-dashboard/index.html':
                import html
                data=data.replace(b'http://netdata.example.invalid:19999/',html.escape(origin+'/',quote=True).encode())
        return data
    def remote(self,script):
        self.configured()
        return run(['ssh',*SSH_OPTIONS,self.settings['ssh_target'],'set -eu\n'+script],timeout=90)
    def snapshot(self):
        compose=json.loads(self.remote('midclt call app.config s90d-telemetry'))
        if not {'receiver','dashboard'}<=compose.get('services',{}).keys():raise Refused('Shared app must have receiver and dashboard services; inspect NAS provisioning before setup')
        registry=json.loads(self.remote('cat '+self.base+'/custom-plugins.d/s90d-data/devices.json'))
        for device in ('s90d','qn90a'):
            p=profile(device)
            if registry.get(device,{}).get('chart_prefix')!=p['chart_prefix'] or registry.get(device,{}).get('snapshot')!=p['snapshot']:
                raise Refused('NAS device registry would lose/misroute existing history: '+device)
        files={}
        for target in FILES:
            output=self.remote('if test -L '+Q(self.base+'/'+target)+'; then echo SYMLINK; elif test -f '+Q(self.base+'/'+target)+'; then sha256sum '+Q(self.base+'/'+target)+'; else echo ABSENT; fi').strip()
            if output=='SYMLINK':raise Refused('Symlink in NAS managed file')
            files[target]=None if output=='ABSENT' else output.split()[0]
        containers=self.remote('docker ps --filter label=com.docker.compose.project=ix-s90d-telemetry --format "{{.Names}} {{.Status}}"')
        return dict(files=files,compose_sha256=sha(json.dumps(compose,sort_keys=True).encode()),registry=registry,containers=containers)

    def add_plan(self,plan,shared):
        state=self.snapshot();desired={target:sha(self.source_bytes(target,source)) for target,source in FILES.items()}
        if state['files']!=desired:
            plan.states['dashboard']='drifted'
            plan.actions.insert(0,Action('000-dashboard','dashboard','nas',state['files'],desired,dict(compose_sha256=state['compose_sha256'])))
            if not shared:plan.issues.append('dashboard: shared NAS changes affect both TVs; explicitly add --shared-nas')
        if not all(name in state['containers'] for name in ('ix-s90d-telemetry-receiver-1','ix-s90d-telemetry-dashboard-1')):
            plan.unsupported('dashboard','Both shared services must be running; inspect NAS app health')
        return state

    def pairing(self,p):
        # This method returns credentials only to a mode-0600 per-run payload.
        data=json.loads(self.remote('cat '+self.base+'/s90d-receiver/receiver.json'))
        records=data.get('devices',{'s90d':data})
        entry=records.get(p['id'])
        if not entry or entry.get('allowed_ip')!=p['host'] or not isinstance(entry.get('token'),str) or len(entry['token'])<32:
            raise Refused('NAS pairing record missing/mismatched; provision this physical TV’s isolated credential first')
        cert=self.remote('cat '+self.base+'/s90d-receiver/server.crt')
        pin=hashlib.sha256(ssl.PEM_cert_to_DER_cert(cert)).hexdigest()
        return dict(device_id=p['id'],endpoint=self.settings['receiver_url']+'/v1/devices/'+p['id'],token=entry['token'],certificate_sha256=pin,
                    dashboard_config_path=p.get('dashboard_config_path','/opt/usr/home/owner/apps_rw/MiniHub001/data/telemetry.json'),
                    firmware=p['firmware'],runtime_version=p['runtime'],startup=p['startup'])

    def check_pairing(self,plan,p,state):
        current=state.get('pairing_config')
        if current is None:return
        if not isinstance(current,dict):raise Refused('Pairing configuration must be an object')
        for key,expected in [('device_id',p['id']),('firmware',p['firmware']),('runtime_version',p['runtime'])]:
            if current.get(key)!=expected:raise Refused('Private pairing identity mismatch: '+key)
        from .config import validate_endpoint
        validate_endpoint(p['id'],current.get('endpoint'))
        expected=self.pairing(p)
        # Preserve custom URL and extension fields, while detecting receiver credential/pin drift.
        wanted={**current,**expected,'endpoint':current['endpoint']}
        if current!=wanted:
            path='/opt/usr/home/owner/apps_rw/MiniTelemetry/data/config.json'
            plan.add('telemetry','pairing',state['files'][path],'paired',path=path)

    def verify(self,device,boot,enabled=True):
        from urllib.request import urlopen
        self.configured()
        with urlopen(self.settings['dashboard_url']+'/api/snapshot?range=900&device='+device,timeout=8) as response:
            raw=response.read(2097153)
        if len(raw)>2097152:raise Refused('Dashboard verification response exceeds bound')
        data=json.loads(raw)
        if data.get('device')!=device or not {'s90d','qn90a'}<={d.get('id') for d in data.get('devices',[])}:
            raise Refused('Dashboard device isolation/registry mismatch')
        sample=data.get('latest') or {}
        fresh=sample.get('boot')==boot and 0<=data.get('server_time',0)-sample.get('received_at',-1000)<=35
        history=data.get('charts',{})
        available=len(history)==9 and all(not c.get('error') and not c.get('unavailable') and c.get('labels') for c in history.values())
        return {'receiver':'disabled by TV preference' if not enabled else 'fresh current-boot ingestion' if fresh else 'current-boot ingestion not verified',
                'dashboard':'both devices and nine history charts available' if available else 'history availability not verified'}

    def prepare(self,action):
        out=self.folder/'nas-source';out.mkdir(mode=0o700)
        for target,source in FILES.items():
            path=out/target;path.parent.mkdir(parents=True,exist_ok=True,mode=0o700);path.write_bytes(self.source_bytes(target,source))
        return dict(source=str(out),backup=self.base+'/telemetry-backups/tv-setup-'+self.folder.name)

    def backup(self,action,info):
        before=self.snapshot()
        if before['files']!=action.before or before['compose_sha256']!=action.options['compose_sha256']:raise Refused('Shared NAS changed before backup')
        location=info['backup']+'-'+info.get('attempt','first')
        info['backup']=location
        self.remote(f'test ! -L {Q(self.base+"/telemetry-backups")}\nmkdir -p {Q(self.base+"/telemetry-backups")}\nchmod 700 {Q(self.base+"/telemetry-backups")}\ntest ! -e {Q(location)}\nmkdir -m 700 {Q(location)}\nmidclt call app.config s90d-telemetry > {Q(location+"/app-before.json")}\n')
        for target,digest in action.before.items():
            if digest is None:continue
            dest=location+'/'+target
            self.remote(f'mkdir -p {Q(str(Path(dest).parent))}\ncp --preserve=all {Q(self.base+"/"+target)} {Q(dest)}\ntest "$(sha256sum {Q(dest)} | cut -d " " -f 1)" = {digest}\n')
        # Pairing is not rewritten, and its hash must survive every update/rollback.
        info['pairing_sha256']=self.remote('sha256sum '+self.base+'/s90d-receiver/receiver.json').split()[0]
        info['registry_sha256']=self.remote('sha256sum '+self.base+'/custom-plugins.d/s90d-data/devices.json').split()[0]
        return info

    def check_shared(self,action,info):
        current=self.snapshot()
        if current['compose_sha256']!=action.options['compose_sha256']:raise Refused('Live compose changed; refusing shared update/restart')
        for path,key in [('s90d-receiver/receiver.json','pairing_sha256'),('custom-plugins.d/s90d-data/devices.json','registry_sha256')]:
            if self.remote('sha256sum '+self.base+'/'+path).split()[0]!=info[key]:raise Refused('Shared identity/pairing changed concurrently')
        return current

    def execute(self,action,info):
        current=self.check_shared(action,info)
        if current['files']!=action.before:raise Refused('NAS code changed after backup')
        # Upload every payload before replacing any live file; never replace config/data.
        for target,digest in action.after.items():
            source=Path(info['source'])/target
            if sha(source.read_bytes())!=digest:raise Refused('NAS payload changed locally')
            remote=info['backup']+'/new/'+target
            self.remote('mkdir -p '+Q(str(Path(remote).parent)))
            run(['scp','-q',*SSH_OPTIONS,source,self.settings['ssh_target']+':'+remote],timeout=60)
            self.remote('test "$(sha256sum '+Q(remote)+' | cut -d " " -f 1)" = '+digest)
        current=self.check_shared(action,info)
        if current['files']!=action.before:raise Refused('NAS code changed while staging')
        for target,digest in action.after.items():
            live=self.base+'/'+target;source=info['backup']+'/new/'+target
            temporary=live+'.tv-setup-'+self.folder.name+'.new'
            script=hash_guard(live,action.before[target])+clear_verified_stage(temporary,digest)
            if action.before[target] is not None:script+=f'cp --preserve=all {Q(live)} {Q(temporary)}\ncat {Q(source)} > {Q(temporary)}\n'
            else:script+=f'cp {Q(source)} {Q(temporary)}\nchown 65534:201 {Q(temporary)}\nchmod {"0755" if target.endswith(".plugin") else "0644"} {Q(temporary)}\n'
            script+=hash_guard(temporary,digest)+f'mv {Q(temporary)} {Q(live)}\n';self.remote(script)
        self.check_shared(action,info);self.restart()
        if self.snapshot()['files']!=action.after:raise Refused('Shared NAS readback failed')

    def restart(self):
        self.remote('docker restart ix-s90d-telemetry-receiver-1 ix-s90d-telemetry-dashboard-1')
        self.remote("pids=$(pgrep -f '^/usr/bin/python3 .*s90d.plugin|^python3 .*s90d.plugin' || true); if test -n \"$pids\"; then kill $pids; fi")

    def rollback(self,action,info):
        state=self.check_shared(action,info)
        # Interrupted batches can contain a mix of before/after bytes; reject external drift.
        if any(h not in (action.before[p],action.after[p]) for p,h in state['files'].items()):raise Refused('Unrelated NAS drift blocks rollback')
        for target,digest in action.before.items():
            live=self.base+'/'+target
            if state['files'][target]==digest:continue
            temporary=live+'.tv-setup-'+self.folder.name+'.restore'
            guard=hash_guard(live,state['files'][target])
            if digest is None:self.remote(guard+'rm -f '+Q(live));continue
            backup=info['backup']+'/'+target
            self.remote(guard+hash_guard(backup,digest)+clear_verified_stage(temporary,digest)+f'cp --preserve=all {Q(backup)} {Q(temporary)}\n'+hash_guard(temporary,digest)+f'mv {Q(temporary)} {Q(live)}\n')
        self.check_shared(action,info);self.restart()
        if self.snapshot()['files']!=action.before:raise Refused('NAS rollback verification failed')
