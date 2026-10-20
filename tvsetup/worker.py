"""Private subprocess boundary for the tracked, bounded root transport."""

import argparse
import json
from pathlib import Path
from .root import execute
from .common import Refused, atomic_json
from .secrets import pairing_record


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("profile", type=Path)
    parser.add_argument("script", type=Path)
    parser.add_argument("cleanup_index", type=int, nargs="?")
    parser.add_argument("--native-bundle", type=Path)
    parser.add_argument("--session", type=Path)
    parser.add_argument("--result", type=Path)
    parser.add_argument("--json-reads", action="store_true")
    args = parser.parse_args(argv)
    try:
        output = execute(
            json.loads(args.profile.read_text()),
            args.script.read_text(),
            args.cleanup_index,
            native_bundle=args.native_bundle,
            session=args.session,
            capture_result=args.result is not None,
        )
    except Exception as error:
        if args.result is not None:
            output = getattr(error, "output", "")
            if args.json_reads:
                # Partial read frames can contain hex credentials. Never persist
                # them as failure diagnostics; a complete frame can be redacted.
                try:
                    output = json.dumps(decode_reads(output))
                except Refused:
                    output = "Privileged read failed; incomplete raw output omitted to protect credentials."
            atomic_json(args.result, {"output": output, "failed": True})
        raise
    if args.result is not None:
        atomic_json(
            args.result, decode_reads(output) if args.json_reads else {"output": output}
        )


def decode_reads(output):
    try:
        raw = json.loads(output)
        data = {name: bytes.fromhex(value).decode() for name, value in raw.items()}
    except (ValueError, AttributeError, TypeError):
        raise Refused("Malformed privileged read result") from None
    for name in ("pairing_config", "legacy_pairing_config"):
        if name not in data:
            continue
        try:
            data[name] = pairing_record(
                json.loads(data[name]) if data[name].strip() else None
            )
        except (ValueError, Refused):
            # Keep snapshots/rollback available. Planning rejects this sentinel;
            # never retain the malformed credential-bearing value itself.
            data[name] = {"unsupported": "Malformed private pairing configuration"}
    return data


if __name__ == "__main__":
    main()
