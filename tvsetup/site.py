"""Private installation settings. Model and firmware safety profiles stay immutable."""
import ipaddress
import os
from pathlib import Path
import re
from urllib.parse import urlsplit
from .common import Refused, read_json, sha
from .config import profile


def load_site(path=None):
    path = Path(path or os.environ.get('TV_SETUP_SITE', '~/.config/samsung-tv-hub/site.json')).expanduser()
    if not path.is_file():
        raise Refused('Create a private site.json from examples/site.json and pass --site PATH; see docs/guides/tv-setup.md')
    data = read_json(path)
    if not isinstance(data, dict) or set(data) - {'devices', 'nas', 'trust_file'}:
        raise Refused('Site accepts devices, nas and trust_file only; safety profiles cannot be overridden')
    devices = data.get('devices', {})
    if not isinstance(devices, dict) or not devices or set(devices) - {'qn90a', 's90d'}:
        raise Refused('Site devices must contain qn90a and/or s90d')
    hosts = []
    for name, entry in devices.items():
        if not isinstance(entry, dict) or set(entry) != {'host', 'device_id'}:
            raise Refused('Each site device requires host (IPv4) and device_id from its read-only API identity')
        try:
            address = ipaddress.IPv4Address(entry['host'])
            if address.is_multicast or address.is_unspecified or address.is_loopback: raise ValueError()
        except (ValueError, TypeError): raise Refused('Invalid TV IPv4 address in site configuration')
        if not isinstance(entry['device_id'],str) or not re.fullmatch(r'uuid:[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}',entry['device_id']):
            raise Refused('device_id must be the exact uuid identity returned by the TV API')
        hosts.append(str(address))
    if len(hosts) != len(set(hosts)): raise Refused('TV addresses must be distinct')
    if len({entry['device_id'] for entry in devices.values()})!=len(devices):raise Refused('Physical TV identities must be distinct')
    nas = data.get('nas')
    if nas is not None:
        required = {'ssh_target', 'base', 'receiver_url', 'dashboard_url'}
        if not isinstance(nas, dict) or not required <= set(nas) or set(nas) - required - {'netdata_url'}: raise Refused('NAS requires ssh_target, base, receiver_url and dashboard_url; netdata_url is optional')
        if not isinstance(nas['ssh_target'], str) or not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_.@-]{0,252}', nas['ssh_target']):
            raise Refused('Use an SSH config alias or user@host for nas.ssh_target')
        if not isinstance(nas['base'], str) or not re.fullmatch(r'/[a-zA-Z0-9_./-]+', nas['base']) or '..' in nas['base'].split('/') or nas['base'].endswith('/'):
            raise Refused('NAS base must be an absolute directory without traversal or trailing slash')
        for key in ('receiver_url', 'dashboard_url', *(['netdata_url'] if 'netdata_url' in nas else [])):
            try:
                u = urlsplit(nas[key]); port = u.port
                valid = u.scheme in (('https',) if key == 'receiver_url' else ('http', 'https')) and u.hostname and not (u.username or u.password or u.query or u.fragment) and u.path in ('', '/') and port != 0
            except (TypeError, ValueError): valid = False
            if not valid: raise Refused('NAS URLs must be credential-free origins; receiver requires HTTPS')
            nas[key] = nas[key].rstrip('/')
    trust_path = data.get('trust_file')
    if trust_path is not None:
        if not isinstance(trust_path, str): raise Refused('trust_file must be a path')
        trust_path = Path(trust_path).expanduser()
        if not trust_path.is_absolute(): trust_path = path.parent / trust_path
        if not trust_path.is_file(): raise Refused('Signing trust file does not exist')
        trust = read_json(trust_path)
        if not isinstance(trust, dict) or set(trust) - {'qn90a', 's90d'}: raise Refused('Invalid signing trust devices')
        for entry in trust.values():
            if not isinstance(entry, dict) or set(entry) != {'signing_profile', 'author_cert_sha256', 'distributor_cert_sha256'}:
                raise Refused('Trust entries require signing_profile and both certificate SHA256 pins')
            if not isinstance(entry['signing_profile'], str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,80}', entry['signing_profile']): raise Refused('Invalid signing profile name')
            for key in ('author_cert_sha256', 'distributor_cert_sha256'):
                if not isinstance(entry[key], str) or not re.fullmatch('[a-f0-9]{64}', entry[key]) or entry[key] == '0'*64: raise Refused('Trust requires real, independently reviewed certificate fingerprints')
        data['_trust'] = trust
    return data


def configured_profile(device, site):
    if device not in site['devices']: raise Refused('Selected device is missing from site configuration')
    return {**profile(device), **site['devices'][device], **site.get('_trust', {}).get(device, {})}


def binding(site, device):
    """Bind recovery to the same destination and trust; unrelated TV settings may change."""
    import json
    return sha(json.dumps({'device': site['devices'][device], 'nas': site.get('nas'),
                           'trust': site.get('_trust', {}).get(device)}, sort_keys=True).encode())
