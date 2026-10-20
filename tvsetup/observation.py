"""One supervised read-only reboot observation, including nested SDK/root/NAS calls."""
import os
from pathlib import Path
import sys
import uuid
from .common import REPO, Refused, atomic_json, read_json, run


def observe(profile,evidence,nas,remaining):
    identifier='observation-'+uuid.uuid4().hex
    request=evidence/(identifier+'-request.json')
    response=evidence/(identifier+'-response.json')
    atomic_json(request,dict(profile=profile,nas=nas.settings if nas is not None else None))
    try:
        run([sys.executable,'-m','tvsetup.observation',request,response],cwd=REPO,
            timeout=remaining,supervise=True)
    except Refused as error:
        (evidence/(identifier+'.log')).write_text(getattr(error,'output',str(error)))
        raise
    result=read_json(response)
    if not isinstance(result,dict) or not isinstance(result.get('boot'),str) or not isinstance(result.get('verification'),dict):
        raise Refused('Reboot observation returned incomplete evidence')
    verification=result['verification']
    if not {'startup','telemetry','scope'} <= verification.keys() or any(not isinstance(v,str) for v in verification.values()):
        raise Refused('Reboot observation is missing required startup/telemetry evidence')
    return result


def main():
    os.umask(0o077)
    # common.run descendants must remain inside the supervisor's process group.
    os.environ['TV_SETUP_SUPERVISED_PGID']=str(os.getpgrp())
    request,response=map(Path,sys.argv[1:])
    data=read_json(request)
    from .transport import Transport
    from .nas import NAS
    from .cli import verification
    p=data['profile']
    with Transport(p,request.parent) as tv:state=tv.snapshot(privileged=True)
    result=verification(p,state)
    if data['nas'] is not None:
        result.update(NAS(request.parent,data['nas']).verify(p['id'],state['boot'],(state.get('preferences') or {}).get('enabled',True)))
    atomic_json(response,dict(boot=state['boot'],verification=result))


if __name__=='__main__':main()
