"""Boot-mode predicate shared by the private dispatch and cancellation monitor.

Mode is a readiness signal, not admission. The host still requires the exact ISP
source/owner, screen on, empty foreground, compositor and bounded boot window.
Do not suppress the fallback and then wait exclusively for background mode:
remote cold restarts can produce normal mode even with the ISP source selected.
"""
from pathlib import PurePosixPath
from shlex import quote


def mode_ready(directory='/tmp'):
    path = PurePosixPath(directory)
    if not path.is_absolute() or '..' in path.parts or any(c in directory for c in '\n\r\0'):
        raise ValueError('Expected an absolute boot-marker directory')
    background = quote(str(path / 'init_mode_background'))
    normal = quote(str(path / 'init_mode_normal'))
    return f'{{ test -e {background} || test -e {normal}; }}'
