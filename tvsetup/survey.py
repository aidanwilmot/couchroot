"""Read-only, toolkit-free discovery. Survey results never authorize installation."""

import ipaddress
import json
import re
from urllib.error import URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, build_opener

from .common import Refused
from .registry import profiles

LIMIT = 65536
FAMILY_RULE = (
    "Same model-year and platform token (the first two underscore-separated "
    "tokens, followed by an underscore); informational only, never support."
)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise Refused("TV identity endpoint redirected; no survey completed")


def validate_host(host):
    """Accept a host only, never URL credentials, paths, ports or control bytes."""
    if not isinstance(host, str) or len(host) > 253:
        raise Refused("Supply a TV hostname or IPv4 address, without a URL or port")
    try:
        address = ipaddress.IPv4Address(host)
    except ValueError:
        if not re.fullmatch(
            r"(?=.{1,253}\Z)[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?", host
        ) or any(
            not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label)
            for label in host.split(".")
        ):
            raise Refused("Supply a TV hostname or IPv4 address, without a URL or port")
    else:
        if address.is_multicast or address.is_unspecified:
            raise Refused("Supply a unicast TV host")
    return host


def read_identity(host):
    """One GET, no proxies/redirects/retries, 5 s timeout and 64 KiB body cap.

    The return value is private: only describe() may construct public output.
    init uses its id locally; never serialize the raw response into a report.
    """
    validate_host(host)
    try:
        opener = build_opener(ProxyHandler({}), NoRedirect())
        with opener.open("http://" + host + ":8001/api/v2/", timeout=5) as response:
            raw = response.read(LIMIT + 1)
        if len(raw) > LIMIT:
            raise Refused("Oversized TV identity response (maximum 64 KiB)")
        value = json.loads(raw)
        if not isinstance(value, dict) or not isinstance(value.get("device"), dict):
            raise ValueError()
        return value["device"]
    except (OSError, URLError):
        # Network exception strings can include the destination or credentials.
        raise Refused(
            "TV identity endpoint unavailable; check power, network and port 8001"
        ) from None
    except (ValueError, UnicodeError, RecursionError):
        raise Refused(
            "Invalid TV identity response; expected a JSON device object"
        ) from None


def platform_family(value):
    if isinstance(value, str) and re.fullmatch(r"[0-9]{2}_[A-Z0-9]+_[A-Z0-9_]+", value):
        return "_".join(value.split("_")[:2]) + "_"
    return None


def public_value(data, key):
    """Allow only known non-identifying fields with their bounded code grammar."""
    value = data.get(key)
    if value is None:
        return None
    pattern = {
        "modelName": r"[A-Z]{2}[0-9]{2,3}[A-Z0-9]{5,20}",
        "model": r"[0-9]{2}_[A-Z0-9]+_[A-Z0-9_]+",
    }[key]
    if (
        not isinstance(value, str)
        or len(value) > 64
        or not re.fullmatch(pattern, value)
    ):
        return "[redacted]"

    # An adversarial response must not smuggle a named identifier via a display field.
    def sensitive_values(obj):
        if isinstance(obj, dict):
            for name, item in obj.items():
                if name not in ("modelName", "model", "developerMode") and isinstance(
                    item, str
                ):
                    yield item
                elif isinstance(item, (dict, list)):
                    yield from sensitive_values(item)
        elif isinstance(obj, list):
            for item in obj:
                yield from sensitive_values(item)

    if any(secret and secret in value for secret in sensitive_values(data)):
        return "[redacted]"
    return value


def developer_state(data):
    # These are the exact field names/semantics in tools/toolkit/samsung_tv.py.
    mode = str(data.get("developerMode"))
    return {
        "mode": "enabled" if mode == "1" else "disabled" if mode == "0" else "unknown",
        "host": "configured (redacted)"
        if isinstance(data.get("developerIP"), str) and data["developerIP"]
        else "unknown",
    }


def describe(data):
    registry = profiles()
    model, platform = public_value(data, "modelName"), public_value(data, "model")
    exact = [
        p
        for p in registry.values()
        if model == p["model"] and platform == p["platform"]
    ]
    family = platform_family(platform)
    relatives = [
        p
        for p in registry.values()
        if family and platform_family(p["platform"]) == family
    ]
    model_only = [p for p in registry.values() if model == p["model"]]
    verdict = (
        "exact_model" if exact else "same_platform_family" if relatives else "unknown"
    )
    candidates = exact or model_only or relatives
    nearest = candidates[0] if len(candidates) == 1 else None
    comparison = []
    for field, found, expected in (
        ("modelName", model, nearest["model"] if nearest else None),
        ("model", platform, nearest["platform"] if nearest else None),
    ):
        comparison.append(
            {
                "field": field,
                "expected": expected,
                "found": found,
                "status": "match"
                if expected is not None and expected == found
                else "different"
                if expected is not None
                else "no_profile",
            }
        )
    for field in (
        "firmware",
        "architecture",
        "runtime",
        "host_sha256",
        "launcher_sha256",
    ):
        comparison.append(
            {
                "field": field,
                "expected": nearest[field] if nearest else None,
                "found": None,
                "status": "requires_sdb_check",
            }
        )
    return {
        "schema": 1,
        "verdict": verdict,
        "nearest_profile": nearest["id"] if nearest else None,
        "nearest_basis": "exact_model"
        if exact
        else "model_only"
        if model_only
        else "platform_family"
        if relatives
        else None,
        "comparison": comparison,
        "capabilities": dict(nearest["capabilities"]) if nearest else {},
        "capability_scope": "Recorded profile evidence only; firmware and all installation gates still require independent checks.",
        "developer_mode": developer_state(data),
        "platform_family_rule": FAMILY_RULE,
        "firmware_verified": False,
        "installation_authorized": False,
        "next_steps": [
            "Model and platform match. Firmware still needs the exact SDB-level check; no installation has been authorized.",
            "Follow docs/guides/universal-installer.md to enroll site/signing trust and prepare the toolkit.",
        ]
        if exact
        else [
            "Unsupported: nothing will be installed. A family resemblance is informational only.",
            "Contribute a redacted report using docs/guides/porting-to-a-new-tv.md; never copy an existing firmware or hash pin.",
        ],
    }


def survey(host):
    return describe(read_identity(host))


def emit(result, as_json=False):
    if as_json:
        print(json.dumps(result, indent=2))
        return
    print("Survey: " + result["verdict"])
    print("Nearest profile: " + (result["nearest_profile"] or "none"))
    for row in result["comparison"]:
        print(
            f"  {row['field']}: expected {row['expected'] or 'unknown'}, found {row['found'] or 'not observed'} ({row['status']})"
        )
    print("Profile capabilities (recorded evidence, not authorization):")
    for key, value in result["capabilities"].items():
        print("  " + key + ": " + value)
    print(
        "Developer Mode: "
        + result["developer_mode"]["mode"]
        + "; host: "
        + result["developer_mode"]["host"]
    )
    for step in result["next_steps"]:
        print(step)
