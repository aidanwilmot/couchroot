"""Build the original ARM launcher from source; no TV or credential access."""
from pathlib import Path
import re
from .common import REPO, Refused

IMAGE = 'samsung-native-collector:bullseye'
SOURCE = REPO/'research/autonomous-root/native-launcher'


def build(folder, command):
    folder = Path(folder).resolve(); folder.mkdir(parents=True, exist_ok=True)
    # This is the same source-built toolchain used by the native Hub. No vendor binary.
    command(['docker', 'run', '--rm', '--platform', 'linux/amd64', '--network', 'none',
             '-v', str(SOURCE)+':/src:ro', '-v', str(folder)+':/out', IMAGE,
             'sh', '/src/build.sh', '/out', '--launcher-only'])
    binary = folder/'app-launcher'
    data = binary.read_bytes()
    if len(data) < 52 or len(data) > 1024*1024 or data[:6] != b'\x7fELF\x01\x01' or data[18:20] != b'\x28\x00':
        raise Refused('Native app launcher must be ARM ELF32 little-endian')
    versions = command(['docker', 'run', '--rm', '--platform', 'linux/amd64', '--network', 'none',
                        '-v', str(folder)+':/out:ro', IMAGE,
                        'arm-linux-gnueabi-readelf', '-V', '/out/app-launcher'])
    required = re.findall(r'GLIBC_(\d+)\.(\d+)', versions)
    if not required or any(tuple(map(int, v)) > (2, 17) for v in required):
        raise Refused('Native app launcher has missing or incompatible GLIBC requirements')
    return binary
