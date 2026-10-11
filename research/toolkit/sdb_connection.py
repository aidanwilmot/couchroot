"""Serialize and safely reuse SDB connections for one exact device serial."""
from __future__ import annotations

import fcntl
import hashlib
import os
from pathlib import Path
import time
from typing import Any


def _listed_state(output: str, serial: str) -> str | None:
    for line in output.splitlines():
        fields = line.split()
        if fields and fields[0] == serial:
            return fields[1] if len(fields) > 1 else "unknown"
    return None


def connect_if_needed(client: Any, lock_dir: Path, connector: Any, *, lock_timeout: float = 10.0) -> None:
    """Ensure ``client.serial`` is ready, issuing connect only when necessary.

    Listing/connect/verification failures propagate from the transport, with a
    clear error for a successful connect that does not yield a ready serial.
    The advisory lock coordinates separate toolkit processes for this serial.
    """
    serial = client.serial
    lock_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    key = hashlib.sha256(serial.encode("utf-8")).hexdigest()
    lock_path = lock_dir / f"sdb-connect-{key}.lock"
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        deadline = time.monotonic() + lock_timeout
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"Timed out waiting for SDB connection lock for {serial}")
                time.sleep(min(0.05, max(0.0, deadline - time.monotonic())))
        # check=True deliberately makes devices/list errors visible; treating
        # them as an empty list could create another leaking connect session.
        listing = client.run(("devices",), check=True)
        state = _listed_state(listing.stdout, serial)
        if state == "device":
            return
        connector()
        # Re-query under the same lock: exit status from `connect` alone does
        # not prove the serial reached the ready state.
        listing = client.run(("devices",), check=True)
        state = _listed_state(listing.stdout, serial)
        if state != "device":
            detail = f"SDB device {serial} is not listed" if state is None else f"SDB device {serial} is {state}, not ready"
            raise RuntimeError(f"sdb connect succeeded but {detail}")
    finally:
        os.close(fd)
