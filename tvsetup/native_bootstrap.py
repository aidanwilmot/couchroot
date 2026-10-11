"""Experimental, bounded host bootstrap. No production pairing or boot-file changes.

The caller owns the device lock and pending-run check. A journaled generation is
one TV boot, not one host connection. Existing stopped/failed units are never
restarted by reconciliation. Only a new boot permits automatic recreation.
"""
import math
import re
import time
import uuid

from .common import Refused, atomic_json, sha, safe_id
from .transport import Q, hash_guard

SCOPE = 'native-bootstrap-pilot'
LABEL = 'User::Pkg::MiniTelemetry'
PROPERTIES = ('LoadState', 'ActiveState', 'SubState', 'MainPID', 'NRestarts',
              'Result', 'Description', 'User', 'Group', 'SmackProcessLabel',
              'Restart', 'RestartUSec', 'Nice', 'ExecStart', 'BindReadOnlyPaths',
              'StartLimitIntervalUSec', 'StartLimitBurst', 'RuntimeMaxUSec')


def layout(identity):
    safe_id(identity)
    suffix = sha(identity.encode())[:16]
    base = '/opt/minimal-native-pilot-' + suffix
    return dict(base=base, code=base+'/code', data=base+'/data',
                runtime='/tmp/minimal-native-pilot-'+suffix,
                staging='/home/owner/share/tmp/sdk_tools/native-pilot-'+suffix,
                unit='minimal-native-pilot-'+suffix)


def validate_doc(doc):
    if doc.get('scope') != SCOPE or doc.get('schema') != 1:
        raise Refused('Not a native bootstrap pilot journal')
    if any(doc.get(k) != v for k, v in layout(doc['run']).items()):
        raise Refused('Pilot paths differ from the run identity')
    if doc.get('device') not in ('qn90a', 's90d'):
        raise Refused('Invalid pilot target')
    if type(doc.get('expires')) not in (int, float) or not math.isfinite(doc['expires']):
        raise Refused('Invalid pilot deadline')
    if type(doc.get('desired')) is not bool:
        raise Refused('Invalid pilot desired state')
    expected = {'collector', 'config.json', 'preferences.json', 'enabled'}
    if set(doc.get('files', {})) != expected or any(
            not re.fullmatch('[a-f0-9]{64}', v) for v in doc['files'].values()):
        raise Refused('Invalid pilot payload manifest')


def description(doc):
    return 'Minimal Hub isolated native pilot ' + doc['run']


def argv(doc):
    return (doc['code']+'/collector --root '+doc['data']+' --runtime '+doc['runtime']+
            ' --run-for 600')


def parse_observation(text):
    match = re.search(r'PILOT_BOOT\n([^\n]+)\nPILOT_UNIT\n(.*?)\nPILOT_END', text, re.S)
    if not match:
        raise Refused('Incomplete bootstrap observation')
    boot = match[1].strip()
    try:
        if str(uuid.UUID(boot)) != boot: raise ValueError()
    except ValueError:
        raise Refused('Invalid boot identity') from None
    props = dict(line.split('=', 1) for line in match[2].splitlines() if '=' in line)
    if props.get('LoadState') not in ('loaded', 'not-found'):
        raise Refused('Unrecognized pilot unit state')
    return dict(boot=boot, unit=props)


def verify_unit(doc, unit):
    expected = dict(Description=description(doc), User='5001', Group='100',
                    SmackProcessLabel=LABEL, Restart='on-failure', Nice='10',
                    RestartUSec='2s', StartLimitIntervalUSec='1min', StartLimitBurst='3',
                    RuntimeMaxUSec='10min')
    if any(unit.get(k) != v for k, v in expected.items()):
        raise Refused('Existing pilot unit properties do not match; no mutation submitted')
    execution = re.search(r'argv\[\]=(.*?) ;', unit.get('ExecStart', ''))
    if not execution or execution[1] != argv(doc):
        raise Refused('Existing pilot executable/arguments differ')
    if unit.get('BindReadOnlyPaths') not in (doc['code'], doc['code']+':'+doc['code']+':rbind'):
        raise Refused('Existing pilot read-only code view differs')


def decision(doc, observation, now):
    """Pure reconciliation policy, including lost replies and explicit stop."""
    validate_doc(doc)
    unit = observation['unit']
    if unit['LoadState'] != 'not-found':
        verify_unit(doc, unit)
    if not doc['desired'] or now >= doc['expires']:
        return 'stop' if unit.get('ActiveState') in ('active', 'activating', 'reloading') else 'quiet'
    generation = doc.get('generation')
    if unit['LoadState'] == 'loaded':
        if generation != observation['boot']:
            raise Refused('Unrecorded pilot unit in this boot')
        return 'running' if unit.get('ActiveState') in ('active', 'activating') else 'quiescent'
    if generation == observation['boot']:
        # A GC'd explicit stop, rate limit, lost reply or natural exit is not a reboot.
        return 'quiescent'
    return 'create'


class Bootstrap:
    def __init__(self, tv, doc, folder):
        validate_doc(doc)
        self.tv, self.doc, self.folder = tv, doc, folder

    def save(self):
        atomic_json(self.folder/'journal.json', self.doc)

    def payload_guards(self):
        d = self.doc
        script = ''
        for name, digest in d['files'].items():
            parent = d['code'] if name == 'collector' else d['data']
            script += hash_guard(parent+'/'+name, digest)
        script += f'test "$(stat -c %u:%a {d["code"]})" = 0:555\n'
        script += f'test "$(stat -c %u:%a {d["code"]}/collector)" = 0:555\n'
        return script

    def stage(self):
        d = self.doc
        d['phase'] = 'preparing'; self.save()
        self.tv.sdk(f'set -eu\ntest ! -e {d["staging"]}\ntest ! -L {d["staging"]}\nmkdir {d["staging"]}\n')
        for name in d['files']:
            source = self.folder/'payload'/name
            if sha(source.read_bytes()) != d['files'][name]:
                raise Refused('Local pilot payload changed')
            self.tv.push(source, d['staging']+'/'+name)
        script = ''.join(hash_guard(d['staging']+'/'+n, h) for n, h in d['files'].items())
        script += f'''test ! -e {d['base']}
test ! -L {d['base']}
mkdir -m 755 {d['base']} {d['code']}
mkdir -m 700 {d['data']}
chown 0:0 {d['base']} {d['code']}
chown 5001:100 {d['data']}
chsmack -a {LABEL} {d['base']}
chsmack -a {LABEL} {d['code']}
chsmack -a {LABEL} {d['data']}
cp {d['staging']}/collector {d['code']}/collector
chown 0:0 {d['code']}/collector
chmod 555 {d['code']}/collector {d['code']}
chsmack -a {LABEL} {d['code']}/collector
'''
        for name in ('config.json', 'preferences.json', 'enabled'):
            script += f'''cp {d['staging']}/{name} {d['data']}/{name}
chown 5001:100 {d['data']}/{name}
chmod 600 {d['data']}/{name}
chsmack -a {LABEL} {d['data']}/{name}
'''
        script += self.payload_guards()+'echo PILOT_STAGED\n'
        if 'PILOT_STAGED' not in self.tv.root(script):
            raise Refused('Pilot staging unconfirmed')
        d['phase'] = 'prepared'; self.save()

    def observe(self):
        unit = self.doc['unit']+'.service'
        script = ('printf "PILOT_BOOT\\n"\ncat /proc/sys/kernel/random/boot_id\n'
                  'printf "PILOT_UNIT\\n"\n'
                  'systemctl show '+unit+' '+ ' '.join('-p '+p for p in PROPERTIES)+
                  ' || true\nprintf "\\nPILOT_END\\n"\n')
        return parse_observation(self.tv.sdk(script))

    def ensure(self):
        observed = self.observe()
        action = decision(self.doc, observed, time.time())
        if action == 'stop':
            self.stop(); return action
        if action != 'create':
            if action == 'running' and self.doc['phase'] == 'starting':
                self.doc['phase'] = 'running'; self.save()
            return action
        d = self.doc
        remaining = min(600, int(d['expires']-time.time()))
        if remaining < 30:
            return 'quiet'
        # Durable intent precedes submission. A lost reply is reconciled, never replayed.
        d['generation'] = observed['boot']; d['phase'] = 'starting'; self.save()
        script = self.payload_guards()
        script += f'test "$(cat /proc/sys/kernel/random/boot_id)" = {Q(observed["boot"])}\n'
        script += f'test "$(systemctl show {d["unit"]}.service -p LoadState --value)" = not-found\n'
        script += f'''systemd-run --unit={d['unit']}-expiry --on-active={remaining}s --timer-property=AccuracySec=1s -p Type=oneshot /usr/bin/systemctl stop {d['unit']}.service
test "$(systemctl show {d['unit']}-expiry.timer -p ActiveState --value)" = active
systemd-run --unit={d['unit']} --description={Q(description(d))} -p User=5001 -p Group=100 -p SmackProcessLabel={LABEL} -p BindReadOnlyPaths={d['code']} -p Nice=10 -p UMask=0077 -p Restart=on-failure -p RestartSec=2s -p StartLimitIntervalSec=60s -p StartLimitBurst=3 -p RuntimeMaxSec=600s -p TimeoutStopSec=4s {argv(d)}
echo PILOT_SUBMITTED
'''
        if 'PILOT_SUBMITTED' not in self.tv.root(script):
            raise Refused('Bootstrap submission unconfirmed; reconcile before continuing')
        observed = self.observe()
        if decision(d, observed, time.time()) != 'running':
            raise Refused('New pilot service did not stay running')
        d['phase'] = 'running'
        d.setdefault('boots', []).append(dict(boot=observed['boot'], unit=observed['unit'], at=time.time()))
        self.save()
        return 'created'

    def fail_main(self):
        observed = self.observe(); verify_unit(self.doc, observed['unit'])
        pid = observed['unit'].get('MainPID', '0')
        if not pid.isdecimal() or int(pid) < 2 or observed['unit'].get('ActiveState') != 'active':
            raise Refused('No active pilot main process to test')
        d = self.doc
        self.tv.root(self.payload_guards()+
                     f'test "$(systemctl show {d["unit"]}.service -p MainPID --value)" = {pid}\n'
                     f'systemctl kill --kill-who=main --signal=KILL {d["unit"]}.service\n')
        return observed

    def inspect(self):
        observed = self.observe(); verify_unit(self.doc, observed['unit'])
        pid = observed['unit'].get('MainPID', '0')
        if not pid.isdecimal() or int(pid) < 2:
            raise Refused('No active pilot process to inspect')
        d = self.doc
        return self.tv.root(self.payload_guards()+f'''
test "$(systemctl show {d['unit']}.service -p MainPID --value)" = {pid}
test "$(readlink /proc/{pid}/exe)" = {d['code']}/collector
awk '/^(Name|PPid|Uid|Gid|VmRSS|CapInh|CapPrm|CapEff):/ {{print}}' /proc/{pid}/status
cat /proc/{pid}/attr/current
grep {Q(d['code'])} /proc/{pid}/mountinfo
if grep -E 'libcoreclr|libhostfxr|libhostpolicy|/dotnet/' /proc/{pid}/maps; then exit 7; fi
echo NO_MANAGED_RUNTIME
printf 'PILOT_STATUS\\n'
cat {d['runtime']}/status.json
printf '\\nPILOT_STATUS_END\\n'
''')

    def stop(self):
        self.doc['desired'] = False; self.doc['phase'] = 'stopping'; self.save()
        observed = self.observe()
        if observed['unit']['LoadState'] == 'loaded':
            verify_unit(self.doc, observed['unit'])
            # Stopping this verified unit must still work after a partial cleanup.
            self.tv.root(f'systemctl stop {self.doc["unit"]}.service\n')
        self.doc['phase'] = 'stopped'; self.save()

    def cleanup(self):
        self.stop()
        d = self.doc
        d['phase'] = 'cleaning'; self.save()
        script = ''
        # Only exact run-specific files. Unknown drift blocks deletion.
        for path in (d['base'], d['code'], d['data'], d['runtime'], d['staging']):
            script += f'test ! -L {path}\nif test -e {path}; then test -d {path}; fi\n'
        for name, digest in d['files'].items():
            parent = d['code'] if name == 'collector' else d['data']
            for path in (parent+'/'+name, d['staging']+'/'+name):
                script += f'if test -e {path} || test -L {path}; then\n'+hash_guard(path, digest)+'fi\n'
        for suffix in ('.service', '-expiry.timer', '-expiry.service'):
            u = d['unit']+suffix
            script += f'if test "$(systemctl show {u} -p LoadState --value)" != not-found; then systemctl stop {u}; systemctl reset-failed {u} || true; fi\n'
        for name in d['files']:
            parent = d['code'] if name == 'collector' else d['data']
            script += f'rm -f {parent}/{name} {d["staging"]}/{name}\n'
        # Runtime belongs exclusively to this isolated pilot, never the production lease.
        script += f'rm -f {d["runtime"]}/pid {d["runtime"]}/status.json {d["runtime"]}/lock\n'
        for path in (d['runtime'], d['code'], d['data'], d['base'], d['staging']):
            script += f'test ! -L {path}\nif test -d {path}; then rmdir {path}; fi\ntest ! -e {path}\n'
        if 'PILOT_CLEAN' not in self.tv.root(script+'echo PILOT_CLEAN\n'):
            raise Refused('Pilot cleanup unconfirmed')
        d['phase'] = 'rolled-back'; self.save()
