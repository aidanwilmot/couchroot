"""Execute generated staging/cleanup locally; no device transport is loaded."""
import os
from pathlib import Path
import shutil
import sys
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from tvsetup import root

STAT_ADAPTER = ('stat() { if test "$2" = %u; then /usr/bin/stat -f %u "$3"; '
                'else /usr/bin/stat -f "%Su:%Sg:%Lp" "$3"; fi; }\n') if sys.platform == 'darwin' else ''


class StagingTests(unittest.TestCase):
    def stage(self, base, native=False):
        with patch.object(root, 'BASE', str(base) + '/'):
            script = root.staging_script(str(base/'probe'), native)
        self.assertNotRegex(script, r"mkdir\s+[^\n]*-m\b|chmod\b")
        # Only the result subdirectory has a restrictive umask, in a subshell.
        self.assertIn("(umask 077; mkdir " + root.Q(str(base/'probe/private')),script)
        self.assertIn("stat -c '%U:%G:%a' " + root.Q(str(base/'probe')), script)
        # macOS uses -f; only adapt stat for this local shell fixture.
        return subprocess.run(['sh', '-c', 'set -eu\n' + STAT_ADAPTER + script], capture_output=True)

    def test_upload_traverses_stage_and_keeps_agent_archives(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            archives = base/'on-demand'; archives.mkdir()
            retained = archives/'archive-root-agent.tar.gz'; retained.write_bytes(b'agent archive')
            self.assertEqual(self.stage(base).returncode, 0)
            stage = base/'probe'
            payload = base/'upload'; payload.write_bytes(b'payload')
            shutil.copyfile(payload, stage/'operation.sh')
            self.assertEqual((stage/'operation.sh').read_bytes(), b'payload')
            self.assertEqual(retained.read_bytes(), b'agent archive')

    def test_partial_stage_rolls_back_without_touching_existing_objects(self):
        for kind in ('file', 'symlink', 'prefix', 'code-failure'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as tmp:
                base = Path(tmp); archives = base/'on-demand'
                if kind == 'file': archives.write_text('keep')
                elif kind == 'symlink': archives.symlink_to(base, target_is_directory=True)
                elif kind == 'prefix':
                    (base/'probe').mkdir(); (base/'probe/keep').write_text('keep')
                if kind == 'code-failure':
                    with patch.object(root, 'BASE', str(base)+'/'):
                        script=root.staging_script(str(base/'probe'), True)
                    # Fail the final mkdir after both top-level mkdirs succeeded.
                    script=script.replace("mkdir "+root.Q(str(base/'probe/code')), 'false')
                    result=subprocess.run(['sh','-c','set -eu\n'+STAT_ADAPTER+script],capture_output=True)
                else: result=self.stage(base)
                self.assertNotEqual(result.returncode, 0, result.stderr)
                if kind != 'prefix': self.assertFalse((base/'probe').exists())
                else: self.assertEqual((base/'probe/keep').read_text(), 'keep')
                if kind == 'file': self.assertEqual(archives.read_text(), 'keep')
                if kind == 'symlink': self.assertTrue(archives.is_symlink())
                if kind == 'code-failure': self.assertEqual(list(archives.iterdir()), [])

    def test_shared_leftovers_are_not_touched_by_sdk_staging(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp); (base/'on-demand').mkdir()
            (base/'on-demand/probe.tar.gz').symlink_to(base/'missing')
            self.assertEqual(self.stage(base).returncode, 0)
            self.assertTrue((base/'on-demand/probe.tar.gz').is_symlink())

    def test_stale_uploads_are_discarded_and_unknown_files_are_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp); self.assertEqual(self.stage(base).returncode,0)
            stale=base/'probe/RootIdentity.dll'; stale.write_text('never execute this')
            (base/'probe/private/result.txt').write_text('stale secret')
            self.assertEqual(self.stage(base).returncode,0)
            self.assertFalse(stale.exists())
            self.assertEqual((base/'probe/private/result.txt').read_bytes(),b'')
            unknown=base/'probe/not-ours'; unknown.write_text('preserve')
            self.assertNotEqual(self.stage(base).returncode,0)
            self.assertEqual(unknown.read_text(),'preserve')

    def test_cleanup_attempts_other_paths_after_one_failure_and_refuses_symlink_parent(self):
        for substitute in ('directory','symlink'):
            with self.subTest(substitute=substitute),tempfile.TemporaryDirectory() as tmp:
                base=Path(tmp);self.assertEqual(self.stage(base).returncode,0)
                prefix=base/'probe'; bad=prefix/'RootIdentity.dll';bad.mkdir()
                later=prefix/'operation.sh';later.write_text('remove me')
                protected=base/'keep';protected.mkdir();(protected/'libacquire.so').write_text('keep')
                if substitute=='symlink':(prefix/'code').symlink_to(protected,target_is_directory=True)
                with patch.object(root,'BASE',str(base)+'/'):
                    script=root.cleanup_script(str(prefix),'probe')
                adapter='stat() { /usr/bin/stat -f %u "$3"; }\n' if sys.platform=='darwin' else ''
                result=subprocess.run(['sh','-c',adapter+script],capture_output=True)
                self.assertNotEqual(result.returncode,0)
                self.assertFalse(later.exists())
                self.assertEqual((protected/'libacquire.so').read_text(),'keep')
