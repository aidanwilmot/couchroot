"""Journaled, disabled-first agent installation using the shared setup engine."""
import argparse
import json
from pathlib import Path
import re
import shutil
import sys
from .artifacts import verify_package
from .autonomous_root import PACKAGE
from .common import STATE, Refused, atomic_json, read_json, sha, lock, safe_id
from .config import resolve
from .engine import Engine,pending,run_id
from .operations import Driver,observed
from .planner import Action,Plan
from .site import binding,configured_profile,load_site
from .transport import Transport,Q,hash_guard

DATA='/opt/usr/home/owner/apps_rw/'+PACKAGE+'/data'
PREFIX='/opt/usr/apps/'+PACKAGE+'/res/wgt/'
SCOPE='autonomous-root-pilot'
PROVISION=('config.json','server-key.pem','server.pem','client.pem')

class PilotTransport(Transport):
    def __init__(self,profile,evidence,files):
        self.pilot_files=files
        super().__init__(profile,evidence)
    def snapshot(self,privileged=False):
        state=super().snapshot(privileged=False)
        script=''
        for i,p in enumerate(self.pilot_files):
            # Both package layouts are observed under a canonical package key.
            candidate=p.replace('/res/wgt/','/') if p.startswith(PREFIX) else p
            script+='printf "PILOT_FILE_'+str(i)+'="\n'
            script+=f'p={Q(p)}\nif test ! -e "$p"; then p={Q(candidate)}; fi\nif test -L "$p"; then echo SYMLINK; elif test -f "$p"; then sha256sum "$p"; else echo ABSENT; fi\n'
        script+='vconftool get db/sdk/develop/ip\n'
        output=self.root(script)
        for i,p in enumerate(self.pilot_files):
            match=re.search(r'PILOT_FILE_'+str(i)+r'=([a-f0-9]{64}|ABSENT|SYMLINK)',output)
            if not match:raise Refused('Pilot file inspection incomplete')
            state['files'][p]=None if match[1]=='ABSENT' else match[1]
        match=re.search(r'db/sdk/develop/ip, value = (\S+) \(String\)',output)
        if not match:raise Refused('Developer host unavailable')
        state['developer_host']=match[1]
        return state

class PilotDriver(Driver):
    def prepare(self,action):
        if action.component!='autonomous-root':raise Refused('Unexpected pilot component')
        source=Path(action.options['source'])
        if action.kind=='package':
            members,_=verify_package(source,self.profile,PACKAGE)
            if {PREFIX+n:(None if n=='signature1.xml' else sha(b)) for n,b in members.items()}!=action.after:raise Refused('Package drift')
        elif action.kind=='file':
            if action.options['path'] not in [DATA+'/'+n for n in PROVISION]:raise Refused('Unexpected provisioning target')
            if sha(source.read_bytes())!=action.after:raise Refused('Provisioning drift')
        else:raise Refused('Unexpected pilot operation')
        target=self.folder/(action.id+source.suffix);shutil.copyfile(source,target);target.chmod(0o600)
        return dict(artifact=str(target),sha256=sha(target.read_bytes()))
    def verify(self,action,before,after):
        if observed(action,after)!=action.after:raise Refused('Pilot readback mismatch')
        if action.kind=='package':
            rows=[r for r in after['packages'] if r[0]==PACKAGE]
            if len(rows)!=1 or rows[0][1:3]!=[PACKAGE+'.App','wgt'] or rows[0][4:]!=['true','false','false','false']:raise Refused('Pilot registration mismatch')
        for field in ('key_filter','task_filter','managed_app'):
            if before.get(field)!=after.get(field):raise Refused('Production routing changed')
        for p,value in before['files'].items():
            if not p.startswith((PREFIX,DATA+'/')) and after['files'].get(p)!=value:raise Refused('Production file changed: '+p)
        if before['developer_host']!=after['developer_host']:raise Refused('Developer host changed during disabled install')


def install(device,artifact,site):
    artifact=artifact.resolve();manifest=read_json(artifact/'manifest.json');profile=configured_profile(device,site)
    if manifest.get('device')!=device or manifest.get('target_binding')!=binding(site,device):raise Refused('Artifact target binding differs')
    pkg=Path(manifest['package'])
    if sha(pkg.read_bytes())!=manifest['package_sha256']:raise Refused('Artifact changed')
    members,_=verify_package(pkg,profile,PACKAGE)
    # Samsung consumes signature1.xml; verification still authenticates every archive member.
    expected={PREFIX+n:(None if n=='signature1.xml' else sha(b)) for n,b in members.items()}
    for n in PROVISION:
        if sha((artifact/'provision'/n).read_bytes())!=manifest['provisioning'][n]:raise Refused('Provisioning changed')
    if read_json(artifact/'provision/config.json').get('enabled') is not False:raise Refused('First installation must be disabled')
    with lock(STATE/(device+'.lock')):
        if pending(STATE,device):raise Refused('Resolve pending device operation first')
        identity=run_id();folder=STATE/'runs'/identity
        files=list(expected)+[DATA+'/'+n for n in PROVISION]
        tv=PilotTransport(profile,folder/'transport',files);state=tv.snapshot()
        if any(r[0]==PACKAGE for r in state['packages']) or any(state['files'].get(p) is not None for p in files):raise Refused('Pilot already exists; inspect and recover rather than overwrite')
        plan=Plan(device);plan.actions=[Action('001-root-package','autonomous-root','package',None,expected,dict(package=PACKAGE,artifact='autonomous-root',previous_version=None,source=str(pkg)))]
        for i,n in enumerate(PROVISION,2):
            plan.actions.append(Action(str(i).zfill(3)+'-root-provision','autonomous-root','file',None,manifest['provisioning'][n],dict(path=DATA+'/'+n,artifact='autonomous-root',source=str(artifact/'provision'/n))))
        choices=resolve(device,overrides={'components':[],'exclude':[],'keep':[],'remove':[],'artifacts':{}})
        driver=PilotDriver(tv,profile,choices,folder)
        engine=Engine(driver,folder,device,choices,target_binding=binding(site,device),scope=SCOPE)
        engine.prepare(plan,state)
        engine.doc['pilot']=dict(artifact=str(artifact),files=files,developer_host=state['developer_host'],status='disabled-install')
        engine.save();engine.apply()
        # Do not finalize normal setup choices or mark pilot acceptance complete.
        return dict(run=identity,phase=engine.doc['phase'],device=device)


def update(device,artifact,previous,site,credentials=None):
    artifact=artifact.resolve();previous=previous.resolve();profile=configured_profile(device,site)
    new=read_json(artifact/'manifest.json');old=read_json(previous/'manifest.json')
    credentials=(credentials or previous).resolve();credential_manifest=read_json(credentials/'manifest.json')
    for item in (new,old,credential_manifest):
        if item.get('device')!=device or item.get('target_binding')!=binding(site,device):raise Refused('Update target binding differs')
        if sha(Path(item['package']).read_bytes())!=item['package_sha256']:raise Refused('Signed package changed')
    current,old_version=verify_package(Path(old['package']),profile,PACKAGE)
    desired,new_version=verify_package(Path(new['package']),profile,PACKAGE)
    if tuple(map(int,new_version.split('.')))<=tuple(map(int,old_version.split('.'))):raise Refused('Forward version required')
    before={PREFIX+n:(None if n=='signature1.xml' else sha(b)) for n,b in current.items()}
    after={PREFIX+n:(None if n=='signature1.xml' else sha(b)) for n,b in desired.items()}
    if set(before)!=set(after):raise Refused('Update file inventory changed; review explicitly')
    with lock(STATE/(device+'.lock')):
        if pending(STATE,device):raise Refused('Resolve pending run first')
        identity=run_id();folder=STATE/'runs'/identity
        files=list(after)+[DATA+'/'+n for n in PROVISION]
        tv=PilotTransport(profile,folder/'transport',files);state=tv.snapshot()
        if {p:state['files'][p] for p in before}!=before:raise Refused('Installed package differs from previous signed artifact')
        for n in PROVISION:
            if state['files'][DATA+'/'+n]!=credential_manifest['provisioning'][n]:raise Refused('Provisioning must be restored to disabled baseline before update')
        if read_json(credentials/'provision/config.json')['enabled'] is not False:raise Refused('Not a disabled baseline')
        a=Action('001-root-update','autonomous-root','package',before,after,dict(package=PACKAGE,artifact='autonomous-root',previous_version=old_version,source=new['package']))
        choices=resolve(device,overrides={'components':[],'exclude':[],'keep':[],'remove':[],'artifacts':{}})
        driver=PilotDriver(tv,profile,choices,folder);engine=Engine(driver,folder,device,choices,target_binding=binding(site,device),scope=SCOPE)
        plan=Plan(device,actions=[a]);engine.prepare(plan,state)
        recovery=folder/'previous-signed.wgt';shutil.copyfile(old['package'],recovery)
        engine.doc['actions'][0]['info'].update(recovery_package=str(recovery),recovery_sha256=sha(recovery.read_bytes()))
        engine.doc['pilot']=dict(artifact=str(artifact),credentials_artifact=str(credentials),files=files,developer_host=state['developer_host'],status='disabled-update')
        engine.save();engine.apply()
        return dict(run=identity,phase=engine.doc['phase'],device=device)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--device',choices=['qn90a','s90d'],required=True);parser.add_argument('--artifact',type=Path,required=True);parser.add_argument('--credentials',type=Path);parser.add_argument('--previous',type=Path);parser.add_argument('--site',type=Path);parser.add_argument('--yes',action='store_true')
    args=parser.parse_args()
    if not args.yes:parser.error('Installation requires --yes')
    try:
        result=update(args.device,args.artifact,args.previous,load_site(args.site),args.credentials) if args.previous else install(args.device,args.artifact,load_site(args.site))
        print(json.dumps(result))
    except Refused as e:print(str(e),file=sys.stderr);return 1
    return 0
if __name__=='__main__':sys.exit(main())
