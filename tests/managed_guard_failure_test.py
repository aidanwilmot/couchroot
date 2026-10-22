"""Guard-failure attribution tests use synthetic local outputs only."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tvsetup.common import Refused
from tvsetup.root import completed_managed_guard_failure
from tvsetup.worker import main as worker_main


class ManagedGuardFailureTests(unittest.TestCase):
    def test_root_guard_boundary_requires_completed_failure_before_marker(self):
        marker = "TVSETUP_ROOT_MANAGED_GUARD_OK_fixture"
        self.assertTrue(completed_managed_guard_failure(0, "\n[exit:1]\n", marker))
        self.assertFalse(
            completed_managed_guard_failure(0, "\n" + marker + "\n\n[exit:1]\n", marker)
        )
        self.assertFalse(completed_managed_guard_failure(2, "\n[exit:1]\n", marker))
        self.assertFalse(completed_managed_guard_failure(0, "incomplete", marker))

    def test_worker_persists_only_guard_failure_boolean(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profile = root / "profile.json"
            script = root / "operation.sh"
            result = root / "result.json"
            profile.write_text("{}")
            script.write_text("true\n")
            error = Refused("guard check failed")
            error.guard_failure = True
            with patch("tvsetup.worker.execute", side_effect=error):
                with self.assertRaisesRegex(Refused, "guard check failed"):
                    worker_main([str(profile), str(script), "--result", str(result)])
            saved = json.loads(result.read_text())
            self.assertEqual(saved["guard_failure"], True)
            self.assertEqual(set(saved), {"output", "failed", "guard_failure"})


if __name__ == "__main__":
    unittest.main()
