"""Exercise the rollback script's actual filesystem behavior without TV access."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from tvsetup.native_trial import restore_script


class NativeTrialRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.data = self.root/'trial'; self.data.mkdir()
        (self.root/'config.json').write_text('{}')
        self.launcher = self.root/'app_launcher'
        self.launcher.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> '+str(self.root/'launches')+'\n')
        self.launcher.chmod(0o700)
        with patch('tvsetup.native_trial.DATA', str(self.root)):
            self.script = restore_script(str(self.data)).replace('/usr/bin/app_launcher', str(self.launcher))

    def tearDown(self):
        self.tmp.cleanup()

    def run_restore(self, *args):
        return subprocess.run(['/bin/sh', '-c', self.script, 'restore', *args], capture_output=True)

    def test_rehearsal_does_not_touch_production_marker_or_launch_hub(self):
        (self.root/'enabled').write_text('original')
        (self.data/'restore-test').touch()
        self.assertEqual(self.run_restore('--probe').returncode, 0)
        self.assertTrue((self.data/'restore-tested').exists())
        self.assertEqual((self.root/'enabled').read_text(), 'original')
        self.assertFalse((self.root/'launches').exists())

    def test_restore_returns_marker_without_crossing_into_app_launch_context(self):
        (self.data/'managed-enabled').write_text('original')
        self.assertEqual(self.run_restore().returncode, 0)
        self.assertEqual((self.root/'enabled').read_text(), 'original')
        self.assertFalse((self.data/'managed-enabled').exists())
        self.assertFalse((self.root/'launches').exists())
        self.assertTrue((self.data/'restored').exists())

    def test_restore_does_not_overwrite_a_new_marker(self):
        (self.root/'enabled').write_text('new')
        (self.data/'managed-enabled').write_text('original')
        self.assertNotEqual(self.run_restore().returncode, 0)
        self.assertEqual((self.root/'enabled').read_text(), 'new')
        self.assertEqual((self.data/'managed-enabled').read_text(), 'original')
        self.assertFalse((self.root/'launches').exists())

    def test_recovery_after_marker_restore_is_idempotent(self):
        (self.root/'enabled').write_text('original')
        self.assertEqual(self.run_restore().returncode, 0)
        self.assertTrue((self.data/'restored').exists())

    def test_missing_marker_and_backup_does_not_claim_success(self):
        self.assertNotEqual(self.run_restore().returncode, 0)
        self.assertFalse((self.data/'restored').exists())


if __name__ == '__main__': unittest.main()
