"""Run shared vectors through the actual C worker wire primitives on Linux."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]

@unittest.skipUnless(os.environ.get('NATIVE_WORKER'),'native CI fixture required')
class NativeProtocolVectors(unittest.TestCase):
    def test_shared_vectors(self):
        v=json.loads((ROOT/'tests/fixtures/root-protocol.json').read_text())
        with tempfile.TemporaryDirectory() as tmp:
            exe=Path(tmp)/'vectors'
            subprocess.run(['gcc','-std=c99','-Wall','-Wextra','-Werror','-Wno-unused-function',str(ROOT/'tests/native-protocol-vectors.c'),'-ldl','-o',str(exe)],check=True)
            def run(mode,wire,limit=0):
                return subprocess.run([str(exe),mode,v['secret_hex'],v['nonce_hex'],str(limit)],input=wire.encode(),capture_output=True,timeout=20)
            for case in v['frames']:
                with self.subTest(case=case['name']):
                    result=run('mac',case['wire']);self.assertEqual(result.returncode==0,case['mac_valid'])
                    if case['mac_valid']:self.assertEqual(result.stdout.decode().rstrip('\n'),case['payload'])
            for case in v['lines']:
                with self.subTest(case=case['name']):
                    result=run('line','x'*case['bytes']+'\n',case['limit']);self.assertEqual(result.returncode==0,case['accepted'])

            for case in v['exec_timeouts']:
                with self.subTest(timeout=case['ms']):self.assertEqual(run('timeout','',case['ms']).returncode==0,case['accepted'])
