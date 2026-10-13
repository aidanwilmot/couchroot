"""Exercise the production worker operations on the local .NET runtime."""
from pathlib import Path
import subprocess
import unittest

class RootAgentWorkerTests(unittest.TestCase):
    def test_native_transfer_and_log_harness(self):
        root=Path(__file__).resolve().parents[1]
        result=subprocess.run(['dotnet','run','--project',str(root/'tests/root-agent-harness/Harness.csproj')],cwd=root,text=True,capture_output=True,timeout=60)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertIn('PASS large transfer',result.stdout)
