"""Private subprocess boundary for the tracked, bounded root transport."""
import argparse
import json
from pathlib import Path
from .root import execute
from .common import Refused, atomic_json
from .secrets import pairing_record


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('profile', type=Path)
    parser.add_argument('script', type=Path)
    parser.add_argument('cleanup_index', type=int, nargs='?')
    parser.add_argument('--native-bundle', type=Path)
    parser.add_argument('--session', type=Path)
    parser.add_argument('--result', type=Path)
    parser.add_argument('--json-reads', action='store_true')
    args = parser.parse_args(argv)
    output=execute(json.loads(args.profile.read_text()), args.script.read_text(),
            args.cleanup_index, native_bundle=args.native_bundle, session=args.session, capture_result=args.result is not None)
    if args.result is not None:
        if args.json_reads:
            try:
                raw=json.loads(output)
                data={name:bytes.fromhex(value).decode() for name,value in raw.items()}
                for name in ('pairing_config','legacy_pairing_config'):
                    if name in data:data[name]=pairing_record(json.loads(data[name]) if data[name].strip() else None)
            except (ValueError,AttributeError,TypeError):raise Refused('Malformed privileged read result') from None
        else:data={'output':output}
        atomic_json(args.result,data)


if __name__ == '__main__':
    main()
