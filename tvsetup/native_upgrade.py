"""Explicit native worker review, upgrade and recovery; never retries a mutation."""

import argparse
import json
import uuid
from pathlib import Path

from agent.client import request
from .common import STATE, Refused, atomic_json, read_json


def invoke(
    device,
    credentials,
    operation,
    *,
    target="package",
    reviewed=None,
    yes=False,
    evidence=None,
    call=request,
):
    if credentials.get("device") != device:
        raise Refused("Credentials do not match the device")
    if target not in ("package", "previous"):
        raise Refused("Unknown native upgrade target")
    if operation == "review":
        return call(
            credentials,
            "GET",
            "/v1/native/upgrade" + ("?target=previous" if target == "previous" else ""),
        )
    if operation == "status":
        return call(credentials, "GET", "/v1/native/status")
    if operation not in ("apply", "recover") or not yes or evidence is None:
        raise Refused("A reviewed operation, --yes and private evidence are required")
    evidence = Path(evidence)
    evidence.mkdir(mode=0o700, parents=True, exist_ok=False)
    operation_id = uuid.uuid4().hex
    if operation == "apply":
        review = invoke(device, credentials, "review", target=target, call=call)
        if not reviewed or review.get("sha256") != reviewed:
            raise Refused("Native upgrade review changed; inspect again")
        atomic_json(evidence / "review.json", review)
        endpoint = "/v1/native/upgrade"
        body = dict(id=operation_id, target=target, review_sha256=reviewed)
    else:
        endpoint = "/v1/native/upgrade/recover"
        body = dict(id=operation_id)
    # Durable local intent is written before the one authenticated submission.
    # A missing result is unknown, never a reason to resubmit.
    atomic_json(
        evidence / "intent.json", dict(device=device, endpoint=endpoint, body=body)
    )
    result = call(credentials, "POST", endpoint, body)
    atomic_json(evidence / "response.json", result)
    return dict(
        submission=result,
        evidence=str(evidence),
        next_step="Read status; submission is not acceptance",
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("review", "apply", "recover", "status"))
    parser.add_argument("--device", required=True, choices=("qn90a", "s90d"))
    parser.add_argument(
        "--credentials",
        required=True,
        type=Path,
        help="Authenticated enrollment client.json, not the package-trial folder",
    )
    parser.add_argument("--target", choices=("package", "previous"), default="package")
    parser.add_argument("--review-sha256")
    parser.add_argument("--yes", action="store_true")
    parser.add_argument("--evidence", type=Path)
    args = parser.parse_args(argv)
    evidence = args.evidence or STATE / "native-upgrades" / uuid.uuid4().hex
    try:
        result = invoke(
            args.device,
            read_json(args.credentials),
            args.operation,
            target=args.target,
            reviewed=args.review_sha256,
            yes=args.yes,
            evidence=evidence,
        )
    except (Refused, FileExistsError) as error:
        parser.exit(2, str(error) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
