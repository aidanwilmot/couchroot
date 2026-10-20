"""Private per-invocation build cache; never retains root access on a TV."""
import json
from .common import REPO, Refused, atomic_json, sha


def prepared(profile, folder, probe):
    from .root import prepare_artifacts, operation_source
    folder.mkdir(parents=True,exist_ok=True,mode=0o700)
    key=sha(json.dumps(profile,sort_keys=True).encode()+operation_source(None).encode()+
            (REPO/'research/namespace-root-probe/Program.cs').read_bytes())
    manifest=folder/'manifest.json'
    if manifest.exists():
        data=json.loads(manifest.read_text())
        if data.get('key')!=key:raise Refused('Root session identity/source changed')
        artifacts={}
        for name,entry in data['files'].items():
            path=folder/name
            if path.is_symlink() or not path.is_file() or sha(path.read_bytes())!=entry['sha256']:
                raise Refused('Root session artifact changed')
            artifacts[path]=entry['remote']
        return artifacts
    # Incomplete preparation must not be silently resumed or retried.
    work=folder/'build'
    try:work.mkdir()
    except FileExistsError:raise Refused('Incomplete root session cache; start a new run') from None
    artifacts=prepare_artifacts(profile,work,None,probe)
    atomic_json(manifest,dict(key=key,files={str(p.relative_to(folder)):dict(remote=remote,sha256=sha(p.read_bytes())) for p,remote in artifacts.items()}))
    return artifacts
