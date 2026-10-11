"""Recover only a complete, hash-verified temporary payload owned by this run."""
from .transport import Q, hash_guard


def clear_verified_stage(path,digest):
    # Unknown bytes and all symlinks are preserved for inspection, never deleted.
    # Recreate verified leftovers so interrupted chmod/chown/label work is repeated.
    return (f'if test -e {Q(path)} || test -L {Q(path)}; then\n'+
            hash_guard(path,digest)+f'rm -f {Q(path)}\nfi\n'+hash_guard(path,None))
