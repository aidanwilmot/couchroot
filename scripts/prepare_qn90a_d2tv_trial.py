#!/usr/bin/env python3
"""Prepare signed, manifest-only QN90A Hub D2TV trial and inverse packages.

This is an offline artifact builder. It never connects to or writes to a TV.
The source WGT must match the exact read-only package snapshot and enrolled
Samsung signing pins. Output is private signed material plus a hash manifest.
"""
import argparse
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import sys
import xml.etree.ElementTree as ET
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tvsetup.artifacts import Builder, verify_package
from tvsetup.common import PRIVATE, Refused, sha
from tvsetup.site import configured_profile, load_site

PACKAGE = 'MiniHub001'
APP_ID = 'MiniHub001.Hub'
METADATA_KEY = 'http://samsung.com/tv/metadata/D2TV'
METADATA_VALUE = 'ISPBound'
BASE_VERSION = '0.4.11'
VERSION_RE = re.compile(rb'(<widget\b[^>]*\bversion=")[^\"]+(\")')
APP_NS = 'http://tizen.org/ns/widgets'
WIDGET_NS = 'http://www.w3.org/ns/widgets'



def snapshot_payload(snapshot):
    if not isinstance(snapshot, dict) or snapshot.get('device') != 'qn90a':
        raise Refused('Baseline snapshot is not the pinned QN90A snapshot')
    rows = [row for row in snapshot.get('packages', []) if isinstance(row, list) and row and row[0] == PACKAGE]
    if len(rows) != 1 or len(rows[0]) < 4 or rows[0][1:4] != [APP_ID, 'wgt', BASE_VERSION]:
        raise Refused('Baseline package identity/type/version differs from the pinned Hub 0.4.11 target')
    files = snapshot.get('files')
    if not isinstance(files, dict):
        raise Refused('Baseline has no package file hashes')
    prefix = f'/opt/usr/apps/{PACKAGE}/res/wgt/'
    members = {path[len(prefix):]: digest for path, digest in files.items() if isinstance(path, str) and path.startswith(prefix)}
    if 'config.xml' not in members or len(members) < 2 or any(not re.fullmatch(r'[0-9a-f]{64}', str(d)) for d in members.values()):
        raise Refused('Baseline package member hash set is incomplete or malformed')
    if 'hub.js' not in members or 'index.html' not in members:
        raise Refused('Baseline does not describe the expected Minimal Hub package')
    return members


def parse_config(data):
    try:
        root = ET.fromstring(data)
    except ET.ParseError as error:
        raise Refused('Hub config.xml is not valid XML') from error
    if root.tag != f'{{{WIDGET_NS}}}widget':
        raise Refused('Unexpected widget manifest namespace')
    app = root.find(f'{{{APP_NS}}}application')
    if app is None or app.get('package') != PACKAGE or app.get('id') != APP_ID:
        raise Refused('Unexpected Hub application identity in config.xml')
    metadata = root.findall(f'{{{APP_NS}}}metadata')
    matches = [item for item in metadata if item.get('key') == METADATA_KEY]
    if len(matches) > 1:
        raise Refused('Duplicate D2TV metadata entries')
    return root, matches


def transform_config(data, version, bind):
    """Change only widget version and the single D2TV metadata entry."""
    root, matches = parse_config(data)
    if matches:
        if bind:
            raise Refused('Base config already contains D2TV metadata; refusing to overwrite it')
        root.remove(matches[0])
    if bind:
        node = ET.Element(f'{{{APP_NS}}}metadata', {'key': METADATA_KEY, 'value': METADATA_VALUE})
        root.append(node)
    if not re.fullmatch(r'\d+\.\d+\.\d+', version):
        raise Refused('Invalid trial package version')
    # Preserve the signed base XML byte-for-byte except the version attribute
    # and one appended metadata element. This also preserves its formatting.
    changed, count = VERSION_RE.subn(lambda m: m.group(1) + version.encode('ascii') + m.group(2), data, count=1)
    if count != 1:
        raise Refused('Could not update exactly one widget version attribute')
    if bind:
        closing = b'</widget>'
        if changed.count(closing) != 1:
            raise Refused('Could not identify the unique widget close tag')
        changed = changed.replace(closing,
            f'<tizen:metadata key="{METADATA_KEY}" value="{METADATA_VALUE}"/>'.encode() + closing, 1)
    elif matches:
        # We only support inverse generation from the approved base, whose
        # metadata is absent; don't serialize/reformat an unexpected config.
        raise Refused('Inverse generation only accepts a base without D2TV metadata')
    final, final_matches = parse_config(changed)
    if final.get('version') != version:
        raise Refused('Updated widget version did not parse back exactly')
    if bind and (len(final_matches) != 1 or final_matches[0].get('value') != METADATA_VALUE):
        raise Refused('Trial D2TV metadata did not parse back exactly')
    if not bind and final_matches:
        raise Refused('Inverse config still contains D2TV metadata')
    return changed


def verify_base(path, profile, snapshot):
    expected = snapshot_payload(snapshot)
    members, version = verify_package(path, profile, PACKAGE)
    if version != BASE_VERSION:
        raise Refused('Signed source artifact is not version '+BASE_VERSION)
    payload = {name: data for name, data in members.items() if name not in ('author-signature.xml', 'signature1.xml')}
    if set(payload) != set(expected):
        raise Refused('Signed source member set differs from the exact installed snapshot')
    wrong = [name for name, data in payload.items() if sha(data) != expected[name]]
    if wrong:
        raise Refused('Signed source bytes differ from readback for '+', '.join(sorted(wrong)))
    _, d2tv = parse_config(payload['config.xml'])
    if d2tv:
        raise Refused('Pinned source already has D2TV metadata; inverse semantics are not established')
    return payload, expected


def sign_stage(stage, profile, builder):
    builder.command([builder.cli, 'package', '-t', 'wgt', '-s', profile['signing_profile'], '-o', stage, '--', stage])
    candidates = list(stage.glob('*.wgt'))
    if len(candidates) != 1:
        raise Refused('Signer did not produce exactly one WGT in '+str(stage))
    return candidates[0]


def package_version(path, profile):
    _, version = verify_package(path, profile, PACKAGE)
    return version


def verify_variant(path, profile, base_payload, expected_version, should_bind):
    members, version = verify_package(path, profile, PACKAGE)
    if version != expected_version:
        raise Refused(f'{path.name} version is {version}, expected {expected_version}')
    payload = {name: data for name, data in members.items() if name not in ('author-signature.xml', 'signature1.xml')}
    if set(payload) != set(base_payload):
        raise Refused('Signed output member set differs from the baseline WGT')
    for name, data in payload.items():
        if name != 'config.xml' and data != base_payload[name]:
            raise Refused('Signed output changed non-manifest member '+name)
    root, d2tv = parse_config(payload['config.xml'])
    if root.get('version') != expected_version:
        raise Refused('Signed output config version differs from expected version')
    if should_bind:
        if len(d2tv) != 1 or d2tv[0].get('value') != METADATA_VALUE:
            raise Refused('Signed output does not contain exactly the requested D2TV role')
    elif d2tv:
        raise Refused('Signed inverse still contains D2TV role metadata')
    return members


def build(base_path, snapshot_path, out_dir, site):
    base_path = Path(base_path).expanduser().resolve(strict=True)
    snapshot_path = Path(snapshot_path).expanduser().resolve(strict=True)
    out_dir = Path(out_dir).expanduser().absolute()
    if out_dir.exists() or out_dir.is_symlink():
        raise Refused('Output directory already exists; choose a fresh private path')
    out_dir.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    out_dir.mkdir(mode=0o700)
    profile = configured_profile('qn90a', site)
    snapshot_bytes = snapshot_path.read_bytes()
    snapshot = json.loads(snapshot_bytes)
    base_payload, expected = verify_base(base_path, profile, snapshot)
    trial_version = '0.4.12'
    restore_version = '0.4.13'
    if package_version(base_path, profile) != BASE_VERSION:
        raise Refused('Source package version changed during validation')
    builder = Builder(profile, {'artifacts': {}}, out_dir/'signing-work')
    outputs = []
    for kind, version, bind in [('trial', trial_version, True), ('restore', restore_version, False)]:
        stage = out_dir/(kind+'-stage')
        stage.mkdir(mode=0o700)
        for name, data in base_payload.items():
            target = stage/name
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            target.write_bytes(transform_config(data, version, bind) if name == 'config.xml' else data)
        unsigned = {p.name: sha(p.read_bytes()) for p in stage.iterdir() if p.is_file()}
        if set(unsigned) != set(base_payload):
            raise Refused('Staged package member set changed unexpectedly')
        for name in unsigned:
            if name != 'config.xml' and unsigned[name] != sha(base_payload[name]):
                raise Refused('Staging changed baseline member '+name)
        candidate = sign_stage(stage, profile, builder)
        destination = out_dir/(kind+'-MiniHub001.wgt')
        shutil.copyfile(candidate, destination)
        os.chmod(destination, 0o600)
        signed_members = verify_variant(destination, profile, base_payload, version, bind)
        outputs.append({
            'kind': kind,
            'path': str(destination),
            'sha256': sha(destination.read_bytes()),
            'version': version,
            'd2tv': {'key': METADATA_KEY, 'value': METADATA_VALUE} if bind else None,
            'member_count': len(signed_members)-2,
            'changed_payload_members': ['config.xml'],
            'non_config_payloads_identical_to_installed_baseline': True,
            'signature_verification': 'verify_package passed against QN90A author/distributor pins',
        })
    manifest = {
        'schema': 1,
        'scope': 'qn90a-hub-d2tv-manifest-only-trial',
        'device': 'qn90a',
        'package': PACKAGE,
        'app_id': APP_ID,
        'baseline_version': BASE_VERSION,
        'baseline_wgt': {'path': str(base_path), 'sha256': sha(base_path.read_bytes())},
        'baseline_snapshot': {'path': str(snapshot_path), 'sha256': sha(snapshot_bytes)},
        'baseline_payload_members': {name: expected[name] for name in sorted(expected)},
        'signing_pins': {'author_cert_sha256': profile['author_cert_sha256'], 'distributor_cert_sha256': profile['distributor_cert_sha256']},
        'artifacts': outputs,
        'device_mutation_performed': False,
        'limitations': [
            'Package signature and local member bytes are verified; installer acceptance and runtime role behavior remain untested.',
            'Readback must verify installed config.xml contains exactly one D2TV=ISPBound metadata entry for the trial and none after inverse.',
            'This manifest does not claim boot/source activation; root owns any separate activation observation or journal.',
        ],
    }
    (out_dir/'manifest.json').write_text(json.dumps(manifest, indent=2, sort_keys=True)+'\n')
    os.chmod(out_dir/'manifest.json', 0o600)
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-wgt', type=Path, required=True)
    parser.add_argument('--snapshot', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args(argv)
    result = build(args.base_wgt, args.snapshot, args.output_dir, load_site())
    print(json.dumps(result, sort_keys=True), flush=True)


if __name__ == '__main__':
    main()
