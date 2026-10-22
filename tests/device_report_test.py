"""Private survey reports expose only allowlisted, redacted observations."""

import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

from tvsetup import device_report, registry
from tvsetup.common import Refused, REPO


def survey_result():
    return {
        "schema": 1,
        "verdict": "same_platform_family",
        "nearest_profile": "s90d",
        "nearest_basis": "platform_family",
        "comparison": [
            {
                "field": "modelName",
                "expected": "QN55S90DAFXZA",
                "found": "QN65S90CAFXZA",
                "status": "different",
            },
            {
                "field": "model",
                "expected": "24_PTM_QD_T09",
                "found": "24_PTM_QD_T99",
                "status": "different",
            },
            {
                "field": "firmware",
                "expected": "T-PTMDAKUC-0090-2130.0",
                "found": None,
                "status": "requires_sdb_check",
            },
        ],
        "capabilities": {
            "transport": "verified",
            "signed_install": "verified",
            "launcher": "verified",
            "home": "verified",
            "startup": "verified",
            "cleanup": "untested",
            "standby": "untested",
        },
        "developer_mode": {"mode": "enabled", "host": "configured (redacted)"},
        # Fields that must never be propagated from caller-controlled input.
        "host": "192.0.2.55",
        "device_id": "UUID-DEVICE-SECRET",
        "raw_response": {
            "id": "UUID-DEVICE-SECRET",
            "developerIP": "192.0.2.55",
            "serial": "SERIAL-SECRET",
            "token": "TOKEN-SECRET",
        },
    }


class DeviceReportTests(unittest.TestCase):
    def test_report_is_private_redacted_and_in_inventory_style(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / "report"
            result = device_report.write_report(
                survey_result(), out, profile_skeleton=True
            )
            self.assertEqual(result, out)
            self.assertEqual(out.stat().st_mode & 0o777, 0o700)
            names = {p.name for p in out.iterdir()}
            self.assertEqual(
                names,
                {"device-report.json", "device-report.md", "profile-skeleton.json"},
            )
            for path in out.iterdir():
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            report = json.loads((out / "device-report.json").read_text())
            self.assertEqual(
                set(report),
                {
                    "schema",
                    "date",
                    "target",
                    "method",
                    "survey",
                    "milestones",
                    "limitations",
                },
            )
            self.assertEqual(report["target"]["model"], "QN65S90CAFXZA")
            self.assertEqual(report["target"]["platform"], "24_PTM_QD_T99")
            self.assertIsNone(report["target"]["firmware"])
            self.assertEqual(
                report["method"]["developer_host"], "configured (redacted)"
            )
            self.assertTrue(
                all(
                    row["result"] == "not tested"
                    for row in report["milestones"].values()
                )
            )
            text = "\n".join(p.read_text() for p in out.iterdir())
            for secret in (
                "192.0.2.55",
                "UUID-DEVICE-SECRET",
                "SERIAL-SECRET",
                "TOKEN-SECRET",
            ):
                self.assertNotIn(secret, text)

    def test_existing_directory_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / "existing"
            out.mkdir()
            marker = out / "keep.txt"
            marker.write_text("unchanged")
            with self.assertRaises(Refused):
                device_report.write_report(survey_result(), out)
            self.assertEqual(marker.read_text(), "unchanged")
            self.assertEqual(list(out.iterdir()), [marker])

    def test_report_cannot_be_written_inside_checkout(self):
        path = REPO / "tests" / "couchroot-device-report-test"
        self.assertFalse(path.exists())
        with self.assertRaises(Refused):
            device_report.write_report(survey_result(), path)
        self.assertFalse(path.exists())

    def test_profile_skeleton_nulls_hashes_and_unverified_fields(self):
        skeleton = device_report._profile_skeleton(survey_result())
        self.assertEqual(skeleton["_marker"], "UNVERIFIED")
        for field in (
            "id",
            "name",
            "firmware",
            "architecture",
            "framework",
            "runtime",
            "host_sha256",
            "launcher_sha256",
            "helper_sha256",
            "collector_sha256",
            "dashboard_config_path",
            "source_hashes",
            "boot_artifacts",
            "service_artifacts",
            "saver_generated",
            "cleanup",
            "reasons",
        ):
            self.assertIsNone(skeleton[field], field)
        self.assertEqual(set(skeleton["capabilities"].values()), {None})
        self.assertTrue(
            all(
                "profile_value" in row and "observed_value" in row
                for row in skeleton["diff"]
            )
        )

    def test_registry_rejects_a_profile_marked_as_unverified_skeleton(self):
        with tempfile.TemporaryDirectory() as temp:
            profile_dir = Path(temp)
            valid = json.loads((REPO / "tvsetup/profiles/qn90a.json").read_text())
            (profile_dir / "qn90a.json").write_text(json.dumps(valid))
            skeleton = device_report._profile_skeleton(survey_result())
            (profile_dir / "s90d.json").write_text(json.dumps(skeleton))
            with patch.object(registry, "PROFILE_DIR", profile_dir):
                with self.assertRaisesRegex(Refused, re.compile("unverified", re.I)):
                    registry.profiles()


if __name__ == "__main__":
    unittest.main()
