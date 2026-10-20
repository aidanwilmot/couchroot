#!/usr/bin/env python3
"""Run one reviewed script through the existing private root transport."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
root=Path.home()/'.local/share/samsung-tv-research'
assert json.loads((root/'config.json').read_text())['tv_host']=='192.0.2.12'
with tempfile.TemporaryDirectory() as tmp:
    ops=Path(tmp)/'ops.json'
    ops.write_text(json.dumps([dict(name='result.txt',kind='command',timeout=45,command=Path(sys.argv[1]).read_text())]))
    result=subprocess.run(['python3',str(root/'gather-dumps.py')],env=dict(os.environ,DUMP_OPERATIONS_FILE=str(ops)),capture_output=True,text=True)
    print(result.stdout,end='');print(result.stderr,end='',file=sys.stderr)
    dirs=[line.split(' ',1)[1] for line in result.stdout.splitlines() if line.startswith('DUMP_DIRECTORY ')]
    if result.returncode or len(dirs)!=1: raise SystemExit('Inspect transport before retrying')
    evidence=Path(dirs[0]);manifest=json.loads((evidence/'manifest.json').read_text())
    record=manifest['operations'][0]
    print((evidence/record['name']).read_text())
    if not manifest['complete'] or not record['verified'] or record['details'].get('exit')!=0:
        raise SystemExit(record['details'].get('stderr') or 'Operation failed')
