#!/usr/bin/env python3
"""Fixed, temporary root identity diagnostic for the owner’s QN90A / 2301.1."""
import fcntl
import hashlib
import io
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys
import tarfile
import tempfile

PROBE = 'codex-qn90a-root-proof'
BASE = '/home/owner/share/tmp/sdk_tools/'
GUARD = """set -eu
grep -q '^Version=T-NKM2AKUC-2301.1;' /etc/prd_info.ini
test "$(uname -m)" = armv7l
test "$(sha256sum /usr/sbin/sdbd-tarlauncher | cut -d ' ' -f 1)" = 3580e6dcf5d9c6d5d0a606d43a3d878641f35eeac07317a405fb45bbed69a653
test "$(sha256sum /usr/bin/dotnet | cut -d ' ' -f 1)" = d2a35114d788c22d22d329acdb2f379c17b75b7099997fb8252cbd6dd940702e
"""
ORIGINALS = """
test "$(sha256sum /etc/passwd | cut -d ' ' -f 1)" = 610fe3305c96f9101c0ca5f65ae8eaa7111a9c8b8ced673f01d9e2553ba2ffad
test "$(sha256sum /usr/share/sdbd/public.pem | cut -d ' ' -f 1)" = c83cab64331f092ba99f666b8bb20a49dd1fff04030336c2ea34f6b55ca09d09
sha256sum /etc/passwd /usr/share/sdbd/public.pem
"""


def run(home_mode=None, telemetry_project=None, telemetry_config=None):
    if home_mode not in (None, 'telemetry', 'apply', 'restore', 'key', 'cast-apply', 'cast-restore', 'cast-early-apply', 'cast-early-restore') + tuple('cleanup-' + str(i) for i in range(10)) + ('saver-script-probe', 'saver-apply', 'saver-inspect', 'saver-capture', 'saver-wake', 'saver-memory-apply', 'saver-memory-restore', 'saver-module-restore', 'saver-idle-trial', 'saver-restore', 'saver-timeout-restore', 'saver-timeout-five-minutes'):
        raise ValueError('Unknown fixed QN90A operation')
    os.umask(0o077)
    repo = Path(__file__).resolve().parents[2]
    toolkit = Path.home() / '.local/share/samsung-tv-research'
    sys.path.insert(0, str(toolkit))
    from samsung_tv import device, capture, SdbClient
    cfg = {'tv_host': '192.0.2.11', 'expected_model': 'QN85QN90AAFXZA',
           'expected_platform': '21_NIKEM2_QTV'}
    if telemetry_config is not None:
        if home_mode != 'telemetry': raise ValueError('Device overrides are telemetry-only')
        cfg = telemetry_config
    with (toolkit / 'qn90a-root-check.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        callback = device(cfg)
        capture(cfg, callback, GUARD + ORIGINALS +
                f'test ! -e {BASE}{PROBE}\ntest ! -e {BASE}on-demand\n',
                20, 'qn90a-root-preflight')
        with tempfile.TemporaryDirectory(prefix='qn90a-root-', dir=toolkit) as folder:
            folder = Path(folder)
            artifacts = {}
            for assembly in ('NamespaceRootProbe', 'RootIdentity'):
                out = folder / assembly
                project = 'research/qn90a-home-route' if home_mode and assembly == 'RootIdentity' else 'research/qn90a-root-probe'
                if home_mode and home_mode.startswith('cleanup-') and assembly == 'RootIdentity':
                    project = 'research/qn90a-app-cleanup'
                if home_mode and home_mode.startswith('saver-') and assembly == 'RootIdentity':
                    project = 'research/qn90a-screensaver'
                if home_mode == 'telemetry' and assembly == 'RootIdentity':
                    project = telemetry_project
                defines = ['-p:DefineConstants=HOME_' + home_mode.upper().replace('-', '_')] if home_mode and assembly == 'RootIdentity' else []
                subprocess.run(['dotnet', 'build', str(repo / project / (assembly + '.csproj')),
                                '-c', 'Release', '--nologo', '-v', 'quiet', '-o', str(out),
                                '-p:BaseIntermediateOutputPath=' + str(out / 'obj') + '/'] + defines, check=True)
                artifacts[out / (assembly + '.dll')] = PROBE + '/' + assembly + '.dll'
            archive = folder / (PROBE + '.tar.gz')
            payload = b'Owner-authorized, bounded QN90A identity diagnostic.\n'
            with tarfile.open(archive, 'w:gz') as tar:
                entry = tarfile.TarInfo('identity-proof.txt')
                entry.size, entry.mode = len(payload), 0o644
                tar.addfile(entry, io.BytesIO(payload))
            private, public = folder / 'test-private.pem', folder / 'public.pem'
            signature = folder / (archive.name + '.signature')
            subprocess.run(['openssl', 'genpkey', '-algorithm', 'RSA', '-pkeyopt', 'rsa_keygen_bits:2048',
                            '-out', str(private)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            subprocess.run(['openssl', 'pkey', '-in', str(private), '-pubout', '-out', str(public)], check=True)
            subprocess.run(['openssl', 'dgst', '-sha256', '-sign', str(private), '-out', str(signature), str(archive)], check=True)
            subprocess.run(['openssl', 'dgst', '-sha256', '-verify', str(public), '-signature', str(signature), str(archive)], check=True)
            artifacts.update({public: PROBE + '/public.pem', archive: 'on-demand/' + archive.name,
                              signature: 'on-demand/' + signature.name})
            print('Probe DLL hashes:', {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                       for p in artifacts if p.suffix == '.dll'})
            cleanup = '\n'.join('rm -f ' + BASE + p for p in artifacts.values())
            cleanup += f'\nrm -f {BASE}{PROBE}/passwd-view\n'
            cleanup += f'rmdir {BASE}{PROBE} {BASE}on-demand\n'
            capture(cfg, callback, GUARD + ORIGINALS +
                    f'test ! -e {BASE}{PROBE}\ntest ! -e {BASE}on-demand\n'
                    f'mkdir {BASE}{PROBE} {BASE}on-demand\n', 20, 'qn90a-root-stage')
            try:
                client = SdbClient(toolkit / 'bin/sdb', cfg['tv_host'])
                client.connect()
                client.require_device()
                for source, target in artifacts.items():
                    client.push(source, PurePosixPath(BASE) / target)
                script = 'cleanup() {\n' + cleanup + '}\ntrap cleanup EXIT\n' + GUARD + ORIGINALS
                script += f'/usr/bin/dotnet {BASE}{PROBE}/NamespaceRootProbe.dll {BASE}{PROBE}\n'
                capture(cfg, callback, script, 45, 'qn90a-root-' + ('home-' + home_mode if home_mode else 'identity'))
            finally:
                # Do not retry an uncertain identity run. Inspect and remove only known artifacts.
                cleanup = cleanup.replace(f'rmdir {BASE}{PROBE} {BASE}on-demand',
                    f'if test -d {BASE}{PROBE}; then rmdir {BASE}{PROBE}; fi\n'
                    f'if test -d {BASE}on-demand; then rmdir {BASE}on-demand; fi')
                capture(cfg, callback, 'set -eu\n' + cleanup + ORIGINALS +
                        f'test ! -e {BASE}{PROBE}\ntest ! -e {BASE}on-demand\n'
                        'id\ngrep -E "^(Uid|Gid|Cap|Seccomp)" /proc/self/status\n'
                        'head -n 3 /proc/self/mountinfo\n'
                        f'if ps -eo args | grep -E "[N]amespaceRootProbe.dll|[R]ootIdentity.dll"; then exit 1; fi\n',
                        20, 'qn90a-root-cleanup-verify')


if __name__ == '__main__':
    if len(sys.argv) != 1:
        raise SystemExit('This fixed diagnostic accepts no commands or arguments.')
    run()
