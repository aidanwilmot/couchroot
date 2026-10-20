#!/usr/bin/env python3
"""Verify the ARM launcher and both small native-acquisition entry bridges."""

from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tvsetup.root_launcher import build
from tvsetup.common import run
from tvsetup.config import profile
from tvsetup.native_root import build as build_acquisition

with tempfile.TemporaryDirectory(prefix="couchroot-launcher-") as tmp:
    first = build(Path(tmp) / "first", run).read_bytes()
    second = build(Path(tmp) / "second", run).read_bytes()
    if first != second:
        raise SystemExit("Native launcher builds differ across output paths")
    for device in ("qn90a", "s90d"):
        build_acquisition(profile(device), Path(tmp) / device, run, service=True)
print("PASS ARM launcher and both native acquisition bridges are reproducible")
