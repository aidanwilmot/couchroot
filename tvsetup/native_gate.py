"""Read-only pre-deploy gate for the native-only agent; never repairs or retries."""

import argparse
import base64
import json
from pathlib import Path
import shlex
import uuid

from .common import Refused

STATE = "/opt/usr/home/owner/apps_rw/MiniRoot01/data/worker-state"
MARKERS = (
    "native-upgrade.pending",
    "retirement-launch.pending",
    "production-launch.pending",
    "state-install.pending",
    "managed-restore.pending",
    "managed-launch.pending",
)
END = "COUCHROOT_NATIVE_GATE_COMPLETE"


def marker_script(directory=STATE):
    names = " -o ".join(
        "-name " + shlex.quote(name) for name in (*MARKERS, "*.activation.json.pending")
    )
    return (
        f"set -eu\ntest ! -L {shlex.quote(str(directory))}\n"
        f"cd {shlex.quote(str(directory))}\n"
        f"find . -maxdepth 1 \\( {names} \\) -print\n"
        f"printf '%s\\n' {END}\n"
    )


def inspect(device, credentials, request):
    if not isinstance(credentials, dict) or credentials.get("device") != device:
        raise Refused("Credentials do not match the selected device")
    status = request(credentials, "GET", "/v1/status")
    if not isinstance(status, dict) or status.get("device") != device:
        raise Refused("Authenticated status does not match the selected device")
    selected = status.get("worker_selection")
    if not isinstance(selected, dict):
        raise Refused("Worker selection is unavailable")
    identity = status.get("identity")
    checks = {
        "root_ready": status.get("connected") is True
        and status.get("worker_ready") is True
        and isinstance(identity, dict)
        and identity.get("uid") == 0,
        "stable": selected.get("phase") == "stable",
        "pending_null": "pending" in selected and selected["pending"] is None,
        "native_selected": selected.get("selected_implementation")
        == "native-prototype",
        "markers_absent": None,
        "selection_unchanged": None,
    }
    report = dict(
        device=device,
        ok=False,
        checks=checks,
        markers=None,
        selection={
            key: selected.get(key, "missing")
            for key in ("phase", "pending", "selected_implementation")
        },
    )
    if not all(
        checks[key]
        for key in ("root_ready", "stable", "pending_null", "native_selected")
    ):
        return report
    # Same shell-byte encoding as AgentTransport; this fixed script only lists names.
    encoded = base64.b64encode(marker_script().encode()).decode()
    body = dict(
        id=str(uuid.uuid4()),
        command=f"printf %s {encoded} | base64 -d | /bin/sh",
        timeout_ms=10000,
    )
    result = request(credentials, "POST", "/v1/exec", body)
    if (
        not isinstance(result, dict)
        or result.get("id") != body["id"]
        or type(result.get("exit_code")) is not int
        or result["exit_code"] != 0
        or result.get("timed_out") is not False
        or result.get("stderr")
        or not isinstance(result.get("stdout"), str)
    ):
        raise Refused("Marker listing failed or is unconfirmed; do not deploy")
    lines = result["stdout"].splitlines()
    if not lines or lines[-1] != END:
        raise Refused("Incomplete marker listing; do not deploy")
    markers = []
    for line in lines[:-1]:
        name = line.removeprefix("./")
        if (
            not line.startswith("./")
            or "/" in name
            or not (name in MARKERS or name.endswith(".activation.json.pending"))
        ):
            raise Refused("Unexpected marker listing; do not deploy")
        markers.append(name)
    report["markers"] = markers
    checks["markers_absent"] = not markers
    after = request(credentials, "GET", "/v1/status")
    checks["selection_unchanged"] = (
        isinstance(after, dict)
        and after.get("device") == device
        and after.get("worker_selection") == selected
        and after.get("worker_ready") is True
        and after.get("connected") is True
    )
    report["ok"] = all(checks.values())
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", required=True, choices=("qn90a", "s90d"))
    parser.add_argument("--credentials", required=True, type=Path)
    args = parser.parse_args()
    try:
        from agent.client import request

        report = inspect(args.device, json.loads(args.credentials.read_text()), request)
        print(json.dumps(report, indent=2))
        return 0 if report["ok"] else 1
    except (OSError, ValueError, RuntimeError, KeyError) as error:
        print(json.dumps(dict(ok=False, error=str(error))))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
