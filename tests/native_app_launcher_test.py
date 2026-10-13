"""Compile and exercise the prototype's fail-closed privilege transitions."""
from pathlib import Path
import subprocess
import tempfile
import unittest


class NativeAppLauncherTests(unittest.TestCase):
    def test_failed_transition_never_executes_a_command(self):
        source = Path(__file__).resolve().parents[1] / 'research/autonomous-root/native-launcher/test-launcher.c'
        with tempfile.TemporaryDirectory() as folder:
            binary = Path(folder) / 'launcher-test'
            subprocess.run(['cc', '-std=c99', '-Wall', '-Wextra', '-Werror',
                            str(source), '-o', str(binary)], check=True, capture_output=True)
            result = subprocess.run([str(binary)], check=True, capture_output=True, text=True)
            self.assertIn('PASS fail-closed transitions', result.stdout)


if __name__ == '__main__':
    unittest.main()
