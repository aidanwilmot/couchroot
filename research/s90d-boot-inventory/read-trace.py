"""Read private boot archives and correlate JS relative timing using a late clock pair."""
import argparse
import json
from pathlib import Path
import re
import struct
import tarfile


def log_records(data):
    pending = bytearray()
    for start in range(0, len(data), 32768):
        block = data[start:start+32768]
        offset = 0
        while offset+7 <= len(block):
            length = int.from_bytes(block[offset+4:offset+6], 'little')
            kind = block[offset+6]
            offset += 7
            if length == 0 and kind == 0:
                break
            if offset+length > len(block):
                break  # A live snapshot may have a partial final record.
            payload = block[offset:offset+length]
            offset += length
            if kind == 1:
                yield payload
            elif kind == 2:
                pending = bytearray(payload)
            elif kind == 3:
                pending.extend(payload)
            elif kind == 4:
                pending.extend(payload)
                yield bytes(pending)
                pending.clear()


def dashboard_reports(data):
    for record in log_records(data):
        for match in re.finditer(b'BOOTTRACEv1:', record):
            try:
                report, _ = json.JSONDecoder().raw_decode(record[match.end():].decode('utf-8', errors='replace'))
                if report.get('schema') == 1:
                    yield report
            except (ValueError, AttributeError):
                continue


def analyze(path):
    traces = {}
    reports = {}
    helpers = []
    with tarfile.open(path) as archive:
        for entry in archive.getmembers():
            if not entry.isfile():
                continue
            if entry.name.endswith('trace.jsonl'):
                data = archive.extractfile(entry).read()
                rows = []
                for line in data.splitlines():
                    try: rows.append(json.loads(line))
                    except ValueError: pass
                traces[entry.name] = rows
            elif 'leveldb/' in entry.name and entry.name.endswith('.log'):
                for report in dashboard_reports(archive.extractfile(entry).read()):
                    reports[report['id']] = report
            elif entry.name.endswith('helper.log'):
                helpers.append(archive.extractfile(entry).read().decode())
    result = {'helper_spans': helpers, 'boots': []}
    for name, rows in traces.items():
        pairs = []
        for row in rows:
            if row['kind'] == 'clocks':
                match = re.search(r'monotonic=([\d.]+) realtime_ms=(\d+)', row['value'])
                if match: pairs.append((float(match[1]), int(match[2])))
        boot = {'source': name, 'start': rows[0]['mono'] if rows else None,
                'end': rows[-1] if rows else None,
                'foreground': [r for r in rows if r['kind'] == 'foreground'],
                'markers': [r for r in rows if r['kind'].startswith('marker')], 'dashboard': []}
        for report in reports.values():
            end = next((e for e in report['events'] if e['name'] == 'trace-end'), None)
            if not end or not pairs or report['clock'] != 'performance.now': continue
            pair = min(pairs, key=lambda p: abs(p[1]-end['wall']))
            if abs(pair[1]-end['wall']) > 2000: continue
            # Do not bridge a clock step: require adjacent anchors within 2 s
            # to agree on the wall-to-monotonic offset within 100 ms.
            nearby = [p for p in pairs if abs(p[0]-pair[0]) < 2]
            offsets = [wall/1000-mono for mono,wall in nearby]
            if len(offsets)<2 or max(offsets)-min(offsets)>.1: continue
            origin = pair[0]+(end['wall']-pair[1])/1000-end['ms']/1000
            boot['dashboard'].append({'id':report['id'],'estimated_origin_s':origin,
              'alignment':'late stable wall/monotonic anchor; JS performance deltas; conservative ±0.1 s, not physical visibility',
              'events':[dict(e,estimated_boot_s=round(origin+e['ms']/1000,3)) for e in report['events']]})
        result['boots'].append(boot)
    return result


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('archive',type=Path);args=p.parse_args()
    print(json.dumps(analyze(args.archive),indent=2))
