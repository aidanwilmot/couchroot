#!/usr/bin/env python3
"""Prepare an exact-length AT-HUB cache edit for this inspected firmware only."""
import hashlib
from pathlib import Path
import sys

EXPECTED = '3ffa26a62b1550c3e85993953bb59cf3cc38d688ddfd4f9d500cc37b6db15123'
source = Path(sys.argv[1]).read_bytes()
assert hashlib.sha256(source).hexdigest() == EXPECTED, 'Unexpected service cache; inspect before patching'
end = source.index(b'_EOF')
old = source[:end]
assert b'ExecStart=/opt/etc/parseinfo.sh &' in old and end == 209
new = b'''[Unit]
After=buxton2.service systemd-udevd.service connman.service net-config.service deviced.service
[Service]
ExecStart=/usr/bin/dotnet /opt/minimal-saver/Boot.dll
'''
assert len(new) + 2 <= end
new += b'#' + b' ' * (end - len(new) - 2) + b'\n'
result = new + source[end:]
assert len(result) == len(source) and result[end:] == source[end:]
out = Path(__file__).parent / 'bin/oneservice.patched'
out.write_bytes(result)
print(f'Changed only bytes 0..{end-1}; size and all following unit offsets unchanged')
print(hashlib.sha256(result).hexdigest())
