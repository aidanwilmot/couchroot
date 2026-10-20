"""Execute generated staging/cleanup locally; no device transport is loaded."""
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from tvsetup import root


class StagingTests(unittest.TestCase):
    def stage(self, base, native=False):
        with patch.object(root, 'BASE', str(base) + '/'):
            script = root.staging_script(str(base/'probe'), [str(base/'on-demand/probe.tar.gz')], native)
        return subprocess.run(['sh', '-c', 'set -eu\numask 022\n' + script], capture_output=True)

    def test_upload_traverses_stage_and_keeps_agent_archives(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            archives = base/'on-demand'; archives.mkdir()
            retained = archives/'archive-root-agent.tar.gz'; retained.write_bytes(b'agent archive')
            self.assertEqual(self.stage(base).returncode, 0)
            stage = base/'probe'
            # SDB/WRT is not the staging owner's UID. The old 0700 regression
            # prevents its path traversal before the upload can finish.
            self.assertTrue(stage.stat().st_mode & stat.S_IXOTH)
            payload = base/'upload'; payload.write_bytes(b'payload')
            shutil.copyfile(payload, stage/'operation.sh')
            self.assertEqual((stage/'operation.sh').read_bytes(), b'payload')
            self.assertEqual(retained.read_bytes(), b'agent archive')

    def test_partial_stage_rolls_back_without_touching_existing_objects(self):
        for kind in ('file', 'symlink', 'archive', 'prefix', 'code-failure'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as tmp:
                base = Path(tmp); archives = base/'on-demand'
                if kind == 'file': archives.write_text('keep')
                elif kind == 'symlink': archives.symlink_to(base, target_is_directory=True)
                elif kind == 'archive':
                    archives.mkdir(); (archives/'probe.tar.gz').write_text('keep')
                elif kind == 'prefix':
                    (base/'probe').mkdir(); (base/'probe/keep').write_text('keep')
                if kind == 'code-failure':
                    with patch.object(root, 'BASE', str(base)+'/'):
                        script=root.staging_script(str(base/'probe'), [], True)
                    # Fail the final mkdir after both top-level mkdirs succeeded.
                    script=script.replace("mkdir "+root.Q(str(base/'probe/code')), 'false')
                    result=subprocess.run(['sh','-c','set -eu\n'+script],capture_output=True)
                else: result=self.stage(base)
                self.assertNotEqual(result.returncode, 0, result.stderr)
                if kind != 'prefix': self.assertFalse((base/'probe').exists())
                else: self.assertEqual((base/'probe/keep').read_text(), 'keep')
                if kind == 'file': self.assertEqual(archives.read_text(), 'keep')
                if kind == 'symlink': self.assertTrue(archives.is_symlink())
                if kind == 'archive': self.assertEqual((archives/'probe.tar.gz').read_text(), 'keep')
                if kind == 'code-failure': self.assertEqual(list(archives.iterdir()), [])

    def test_setup_archive_reservation_rejects_dangling_symlinks(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp); (base/'on-demand').mkdir()
            (base/'on-demand/probe.tar.gz').symlink_to(base/'missing')
            self.assertNotEqual(self.stage(base).returncode, 0)
            self.assertFalse((base/'probe').exists())
