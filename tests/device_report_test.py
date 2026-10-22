"""Private survey reports expose only allowlisted, redacted observations."""

import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

from tvsetup import device_report, registry, survey
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
        "routed_address": "198.51.100.24",
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
            self.assertNotRegex(text, r"\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b")
            for secret in (
                "192.0.2.55",
                "UUID-DEVICE-SECRET",
                "SERIAL-SECRET",
                "TOKEN-SECRET",
            ):
                self.assertNotIn(secret, text)

    def test_unknown_tv_still_writes_reports_and_rejected_skeleton_without_diff(self):
        unknown = survey.describe(
            {"modelName": "QN65S90CAFXZA", "model": "23_PTM_QD_T09"}
        )
        self.assertEqual(unknown["verdict"], "unknown")
        self.assertIsNone(unknown["nearest_profile"])
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            out = root / "report"
            device_report.write_report(unknown, out, profile_skeleton=True)
            self.assertEqual(
                {path.name for path in out.iterdir()},
                {"device-report.json", "device-report.md", "profile-skeleton.json"},
            )
            for name in ("device-report.json", "device-report.md"):
                self.assertIn(
                    "No reviewed profile is close enough to diff against.",
                    (out / name).read_text(),
                )
            skeleton = json.loads((out / "profile-skeleton.json").read_text())
            self.assertIsNone(skeleton["_diff_against"])
            self.assertEqual(skeleton["diff"], [])
            self.assertEqual(skeleton["_marker"], "UNVERIFIED")
            self.assertEqual(skeleton["model"], "QN65S90CAFXZA")
            self.assertEqual(skeleton["platform"], "23_PTM_QD_T09")
            for key, value in skeleton.items():
                if key not in {"_marker", "model", "platform", "diff", "capabilities"}:
                    self.assertIsNone(value, key)
            self.assertEqual(set(skeleton["capabilities"].values()), {None})
            profile_dir = root / "profiles"
            profile_dir.mkdir()
            (profile_dir / "qn90a.json").write_bytes(
                (REPO / "tvsetup/profiles/qn90a.json").read_bytes()
            )
            (profile_dir / "s90d.json").write_text(json.dumps(skeleton))
            with patch.object(registry, "PROFILE_DIR", profile_dir):
                with self.assertRaisesRegex(Refused, re.compile("unverified", re.I)):
                    registry.profiles()
            for path in out.iterdir():
                self.assertNotRegex(
                    path.read_text(), r"\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b"
                )

    def test_exact_and_family_skeletons_retain_their_profile_diff(self):
        profile = registry.profile("s90d")
        exact = survey.describe(
            {"modelName": profile["model"], "model": profile["platform"]}
        )
        for result, expected_status in (
            (exact, "match"),
            (survey_result(), "different"),
        ):
            with self.subTest(verdict=result["verdict"]):
                skeleton = device_report._profile_skeleton(result)
                self.assertEqual(skeleton["_diff_against"], "s90d")
                self.assertEqual(len(skeleton["diff"]), 2)
                self.assertEqual(
                    {row["status"] for row in skeleton["diff"]}, {expected_status}
                )

    def test_failed_file_write_removes_all_partial_report_output(self):
        write_private = device_report._write_private
        for failing in (
            "device-report.json",
            "device-report.md",
            "profile-skeleton.json",
        ):
            with self.subTest(file=failing), tempfile.TemporaryDirectory() as temp:
                out = Path(temp) / "report"

                def fail_one(path, data):
                    if path.name == failing:
                        raise OSError("synthetic disk failure")
                    write_private(path, data)

                with patch.object(
                    device_report, "_write_private", side_effect=fail_one
                ):
                    with self.assertRaisesRegex(OSError, "synthetic disk failure"):
                        device_report.write_report(
                            survey_result(), out, profile_skeleton=True
                        )
                self.assertFalse(out.exists())

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
