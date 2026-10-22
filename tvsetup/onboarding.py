"""Read-only onboarding diagnostics and private local trust/site creation."""

import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import socket
import stat
import subprocess

from .common import Refused
from .registry import profile as load_profile
from .survey import describe, read_identity, validate_host

DEFAULT_SITE = Path.home() / ".config/samsung-tv-hub/site.json"
DEVICE_ID = re.compile(r"uuid:[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}\Z")


def _routed_address(host):
    """Return the source IPv4 selected for SDB, without sending a packet."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as route:
        route.settimeout(5)
        route.connect((host, 26101))
        return route.getsockname()[0]


def _check(name, status, hint):
    return {"name": name, "status": status, "hint": hint}


def doctor(host):
    """Check identity, Developer Mode and SDB reachability without credentials."""
    validate_host(host)
    checks = []
    identity = None
    try:
        identity = read_identity(host)
        checks.append(
            _check(
                "identity endpoint (:8001)",
                "passed",
                "No fix needed.",
            )
        )
    except Refused:
        checks.append(
            _check(
                "identity endpoint (:8001)",
                "failed",
                "Power on the TV and make sure it is reachable on port 8001.",
            )
        )

    if identity is None:
        mode_status = "unknown"
        mode_hint = "Restore access to the identity endpoint, then enable Developer Mode on the TV."
    else:
        mode = str(identity.get("developerMode"))
        mode_status = (
            "passed" if mode == "1" else "failed" if mode == "0" else "unknown"
        )
        mode_hint = (
            "No fix needed."
            if mode_status == "passed"
            else "Enable Developer Mode on the TV."
        )
    checks.append(_check("Developer Mode", mode_status, mode_hint))

    # The routed address belongs to this computer and is needed for setup.
    # Never echo the TV's configured developerIP, even when it differs.
    developer_ip = identity.get("developerIP") if identity is not None else None
    try:
        routed = str(ipaddress.IPv4Address(_routed_address(host)))
        route_status = (
            "unknown"
            if not isinstance(developer_ip, str) or not developer_ip
            else "passed"
            if developer_ip == routed
            else "failed"
        )
        route_hint = f"Set Developer Mode's host IP to {routed} (this computer)"
    except (OSError, ipaddress.AddressValueError):
        route_status = "unknown"
        route_hint = "Check this computer's route to the TV, then set Developer Mode's host to its routed address."
    checks.append(_check("Developer Mode host", route_status, route_hint))

    try:
        with socket.create_connection((host, 26101), timeout=5):
            pass
        checks.append(_check("SDB port (:26101)", "passed", "No fix needed."))
    except OSError:
        checks.append(
            _check(
                "SDB port (:26101)",
                "failed",
                "Enable Developer Mode and allow SDB traffic to the TV on port 26101.",
            )
        )
    return {
        "ok": all(check["status"] == "passed" for check in checks),
        "checks": checks,
        "read_only": True,
    }


def _ipv4_host(host):
    validate_host(host)
    try:
        address = ipaddress.IPv4Address(host)
    except ipaddress.AddressValueError:
        raise Refused(
            "init requires an IPv4 address; run survey with a hostname first"
        ) from None
    if address.is_loopback or address.is_multicast or address.is_unspecified:
        raise Refused("init requires a usable IPv4 TV address")
    return str(address)


def _ensure_private_parent(parent):
    """Create missing directory components without following symlinks."""
    parent = Path(os.path.abspath(parent))
    missing = []
    current = parent
    while True:
        try:
            mode = current.lstat().st_mode
        except FileNotFoundError:
            missing.append(current)
            if current.parent == current:
                raise Refused(
                    "Cannot create the private configuration directory"
                ) from None
            current = current.parent
            continue
        if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
            raise Refused("Private configuration path must contain real directories")
        break
    for directory in reversed(missing):
        try:
            directory.mkdir(mode=0o700)
        except FileExistsError:
            mode = directory.lstat().st_mode
            if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
                raise Refused(
                    "Private configuration path must contain real directories"
                ) from None
    final_mode = parent.lstat().st_mode
    if stat.S_IMODE(final_mode) != 0o700:
        raise Refused("Private configuration directory must have mode 0700")


def _preflight_private_parent(parent):
    """Fail before a TV request when an existing destination directory is unsafe."""
    parent = Path(os.path.abspath(parent))
    current = parent
    while True:
        try:
            mode = current.lstat().st_mode
        except FileNotFoundError:
            if current.parent == current:
                raise Refused(
                    "Cannot create the private configuration directory"
                ) from None
            current = current.parent
            continue
        if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
            raise Refused("Private configuration path must contain real directories")
        break
    try:
        final_mode = parent.lstat().st_mode
    except FileNotFoundError:
        return
    if stat.S_ISLNK(final_mode) or not stat.S_ISDIR(final_mode):
        raise Refused("Private configuration path must contain real directories")
    if stat.S_IMODE(final_mode) != 0o700:
        raise Refused("Private configuration directory must have mode 0700")


def init(host, destination=None):
    """Survey one IPv4 TV and exclusively write a private site.json."""
    host = _ipv4_host(host)
    path = Path(destination).expanduser() if destination else DEFAULT_SITE
    if not path.is_absolute():
        path = Path.cwd() / path
    try:
        path.lstat()
    except FileNotFoundError:
        pass
    else:
        raise Refused("site.json already exists; it will not be overwritten")
    # Resolve symlinked ancestors once, then use the resolved parent exclusively.
    # This supports aliases such as /var -> /private/var while preventing the
    # final open from following a user-supplied parent symlink.
    path = path.parent.resolve(strict=False) / path.name
    _preflight_private_parent(path.parent)
    identity = read_identity(host)
    result = describe(identity)
    if result["verdict"] != "exact_model" or not result["nearest_profile"]:
        raise Refused("Unsupported TV model; no site configuration was written")
    device_id = identity.get("id")
    if not isinstance(device_id, str) or not DEVICE_ID.fullmatch(device_id):
        raise Refused(
            "TV identity did not contain a valid device ID; no site configuration was written"
        )
    profile_id = result["nearest_profile"]
    load_profile(profile_id)
    _ensure_private_parent(path.parent)
    payload = {
        "devices": {
            profile_id: {"host": host, "device_id": device_id},
        }
    }
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags, 0o600)
    except FileExistsError:
        raise Refused("site.json already exists; choose a new path") from None
    except OSError:
        raise Refused("Cannot create private site.json") from None
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            json.dump(payload, output, indent=2)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        dirfd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(dirfd)
        finally:
            os.close(dirfd)
    except BaseException:
        try:
            path.unlink()
        except OSError:
            pass
        raise Refused("Could not finish writing private site.json") from None
    return {
        "device": profile_id,
        "path": str(path),
        "firmware_check_required": True,
        "written": True,
    }


def _certificate_der(path):
    path = Path(path).expanduser()
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 1024 * 1024:
            raise ValueError()
        data = path.read_bytes()
        if not data:
            raise ValueError()
        form = "PEM" if b"-----BEGIN CERTIFICATE-----" in data else "DER"
        if form == "PEM" and data.count(b"-----BEGIN CERTIFICATE-----") != 1:
            raise ValueError()
        result = subprocess.run(
            ["openssl", "x509", "-inform", form, "-in", str(path), "-outform", "DER"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=5,
            check=False,
        )
        if result.returncode or not result.stdout:
            raise ValueError()
        return result.stdout
    except (OSError, ValueError, subprocess.SubprocessError):
        raise Refused("Could not read a local X.509 certificate") from None


def trust_entry(device, signing_profile, author_certificate, distributor_certificate):
    """Return one trust.json entry from explicitly selected local certificates."""
    load_profile(device)
    if not isinstance(signing_profile, str) or not re.fullmatch(
        r"[A-Za-z0-9_.-]{1,80}", signing_profile
    ):
        raise Refused("Invalid signing profile name")
    author = hashlib.sha256(_certificate_der(author_certificate)).hexdigest()
    distributor = hashlib.sha256(_certificate_der(distributor_certificate)).hexdigest()
    return {
        device: {
            "signing_profile": signing_profile,
            "author_cert_sha256": author,
            "distributor_cert_sha256": distributor,
        }
    }
