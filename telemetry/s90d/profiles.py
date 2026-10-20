"""Public device inventory validation; pairing data lives elsewhere."""
import ipaddress
import json
from pathlib import Path
import re

ID=re.compile(r'[a-z][a-z0-9_-]{0,47}')
def load(path=None):
    records=json.loads(Path(path or Path(__file__).with_name('devices.json')).read_text())
    if not isinstance(records,dict) or not 1<=len(records)<=32:raise ValueError('device count')
    prefixes=set();hosts=set();snapshots=set()
    for identity,profile in records.items():
        if not ID.fullmatch(identity):raise ValueError('device id')
        ipaddress.ip_address(profile['host'])
        if not ID.fullmatch(profile['chart_prefix']):raise ValueError('chart prefix')
        expected='latest.json' if identity=='s90d' else identity+'.json'
        if profile['snapshot']!=expected:raise ValueError('snapshot must match identity')
        if identity=='s90d' and profile['chart_prefix']!='s90d':raise ValueError('reserved S90D history')
        if identity!='s90d' and profile['chart_prefix']=='s90d':raise ValueError('reserved S90D history')
        if profile['chart_prefix'] in prefixes or profile['host'] in hosts or profile['snapshot'] in snapshots:raise ValueError('duplicate device resource')
        prefixes.add(profile['chart_prefix']);hosts.add(profile['host']);snapshots.add(profile['snapshot'])
        if not isinstance(profile['name'],str) or not 1<=len(profile['name'])<=80 or any(ord(c)<32 for c in profile['name']):raise ValueError('friendly name')
        if not re.fullmatch('[0-9a-f]{64}',profile['host_sha256']):raise ValueError('host hash')
        if profile['startup']=='launcher-service' and not re.fullmatch('[0-9a-f]{64}',profile.get('launcher_sha256','')):raise ValueError('launcher hash')
        supported={'s90d-helper':'net6.0','launcher-service':'netcoreapp3.1'}
        if supported.get(profile['startup'])!=profile['framework'] or profile['architecture']!='armv7l':raise ValueError('unsupported runtime/startup profile')
    return records
