"""Boot-mode readiness regression; real admission is covered by test_host.py."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from boot import mode_ready


class BootTests(unittest.TestCase):
    def test_normal_and_background_are_ready_but_missing_markers_are_not(self):
        with tempfile.TemporaryDirectory(prefix='boot markers ') as tmp:
            root = Path(tmp)
            def status():
                return subprocess.run(['/bin/sh', '-c', 'set -eu\n' + mode_ready(tmp)],
                                      capture_output=True, timeout=5).returncode
            self.assertNotEqual(status(), 0)
            for name in ('init_mode_normal', 'init_mode_background'):
                marker = root / name; marker.touch()
                self.assertEqual(status(), 0, name)
                marker.unlink()
            (root / 'init_mode_recovery').touch()
            self.assertNotEqual(status(), 0)


if __name__ == '__main__': unittest.main()
