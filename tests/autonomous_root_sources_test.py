"""Fail closed before packaging changed tracked upstream/adapted sources."""
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
from tvsetup import autonomous_root
from tvsetup.common import Refused

class SourceHashes(unittest.TestCase):
    def test_recorded_local_hashes_match(self):
        manifest=autonomous_root.verify_sources()
        adapted=[e for e in manifest['files'] if e.get('modified')]
        self.assertEqual(len(adapted),2)
        self.assertTrue(all(e['upstream_sha256']!=e['sha256'] for e in adapted))
        self.assertIn('service/root-agent.js',[e['path'] for e in adapted])

    def test_modified_source_refuses_before_profile_or_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=autonomous_root.SOURCE
            shutil.copyfile(source/'UPSTREAM.json',root/'UPSTREAM.json')
            for e in json.loads((root/'UPSTREAM.json').read_text())['files']:
                p=root/e['path'];p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source/e['path'],p)
            p=root/'service/root-agent.js';p.write_text(p.read_text()+'\n// changed\n')
            with patch.object(autonomous_root,'SOURCE',root),patch.object(autonomous_root,'configured_profile',side_effect=AssertionError('started preparation')):
                with self.assertRaisesRegex(Refused,'source hash mismatch'):autonomous_root.prepare('qn90a',{})
