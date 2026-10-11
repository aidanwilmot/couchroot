#!/usr/bin/env python3
"""Summarize systemd's retained monotonic timestamps; not a critical-path proof."""
import argparse
import json
from pathlib import Path


def parse(text):
    units = []
    for block in text.split('\n\n'):
        values = dict(line.split('=', 1) for line in block.splitlines() if '=' in line and not line.startswith('#'))
        if 'Id' not in values:
            continue
        row = {'unit': values['Id'], 'type': values.get('Type'), 'result': values.get('Result'),
               'after': values.get('After', '').split(), 'requires': values.get('Requires', '').split()}
        for field, key in [('ExecMainStartTimestampMonotonic', 'process_start_s'),
                           ('ExecMainExitTimestampMonotonic', 'process_exit_s'),
                           ('InactiveExitTimestampMonotonic', 'activation_start_s'),
                           ('ActiveEnterTimestampMonotonic', 'active_s')]:
            raw = values.get(field, '')
            row[key] = int(raw) / 1_000_000 if raw.isdigit() and int(raw) > 0 else None
        start, end = row['process_start_s'], row['process_exit_s']
        row['process_lifetime_s'] = round(end - start, 6) if start is not None and end is not None and end >= start else None
        row['readiness_note'] = 'oneshot completion; app visibility unknown' if row['type'] == 'oneshot' else 'active does not establish application readiness'
        units.append(row)
    return units


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('timestamps', type=Path)
    args = p.parse_args()
    units = parse(args.timestamps.read_text())
    if not units:
        raise SystemExit('No unit records: inspect collector stderr; do not treat missing data as zero time')
    print(json.dumps({'warning': 'Retained current-boot timestamps may reflect restarts. Lifetimes overlap; do not sum them. Not a dashboard-ready measurement.', 'units': units}, indent=2))


if __name__ == '__main__':
    main()
