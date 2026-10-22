"""Structured identity refusals use only synthetic profile values."""

import io
import json
import unittest
from unittest.mock import patch

from tvsetup.common import Refused
from tvsetup.native_cli import identity
from tvsetup.transport import (
    compare_identity_probe,
    identity_probe_script,
    refusal_for_differences,
)


class RefusalDiagnosticsTests(unittest.TestCase):
    def test_real_profile_probe_values_pass_and_firmware_delimiter_is_stripped(self):
        from tvsetup.config import profile

        self.assertIn("s/;$//", identity_probe_script())
        for device in ("s90d", "qn90a"):
            pinned = profile(device)
            output = "\n".join(
                (
                    "TVSETUP_PROBE:firmware:" + pinned["firmware"],
                    "TVSETUP_PROBE:architecture:" + pinned["architecture"],
                    "TVSETUP_PROBE:runtime:present",
                    "TVSETUP_PROBE:dotnet_sha256:" + pinned["host_sha256"],
                    "TVSETUP_PROBE:dotnet_launcher_sha256:" + pinned["launcher_sha256"],
                )
            )
            compare_identity_probe(pinned, output)

    def test_each_pinned_field_has_a_stable_code_and_diff(self):
        cases = {
            "firmware": "CR-ID-FIRMWARE",
            "architecture": "CR-ID-ARCH",
            "runtime": "CR-ID-RUNTIME",
            "dotnet_sha256": "CR-ID-HASH",
            "dotnet_launcher_sha256": "CR-ID-HASH",
        }
        for field, code in cases.items():
            with self.subTest(field=field):
                with self.assertRaises(Refused) as caught:
                    raise refusal_for_differences(
                        [(field, "expected-safe", "found-safe")]
                    )
                refusal = caught.exception
                self.assertEqual(refusal.code, code)
                self.assertEqual(
                    refusal.fields,
                    [
                        {
                            "field": field,
                            "expected": "expected-safe",
                            "found": "found-safe",
                        }
                    ],
                )
                self.assertEqual(refusal.as_json()["code"], code)
                self.assertIn("expected expected-safe, found found-safe", str(refusal))

    def test_probe_reports_all_mismatches(self):
        profile = {
            "firmware": "T-EXAMPLE-1",
            "architecture": "armv7l",
            "runtime": "6.0.9",
            "host_sha256": "a" * 64,
            "launcher_sha256": "b" * 64,
        }
        observed = {
            "firmware": "T-EXAMPLE-2",
            "architecture": "x86_64",
            "runtime": "absent",
            "dotnet_sha256": "absent",
            "dotnet_launcher_sha256": "c" * 64,
        }
        output = "\n".join(
            f"TVSETUP_PROBE:{key}:{value}" for key, value in observed.items()
        )
        with self.assertRaises(Refused) as caught:
            compare_identity_probe(profile, output)
        self.assertEqual(
            [item["field"] for item in caught.exception.fields],
            [
                "firmware",
                "architecture",
                "runtime",
                "dotnet_sha256",
                "dotnet_launcher_sha256",
            ],
        )
        self.assertEqual(caught.exception.code, "CR-ID-FIRMWARE")

    def test_probe_redacts_unrecognized_values(self):
        profile = {
            "firmware": "T-EXAMPLE-1-1.0",
            "architecture": "armv7l",
            "runtime": "6.0.9",
            "host_sha256": "a" * 64,
            "launcher_sha256": "b" * 64,
        }
        output = "\n".join(
            (
                "TVSETUP_PROBE:firmware:192.0.2.44",
                "TVSETUP_PROBE:architecture:SERIAL-123456789",
                "TVSETUP_PROBE:runtime:present",
                "TVSETUP_PROBE:dotnet_sha256:serial-123456789",
                "TVSETUP_PROBE:dotnet_launcher_sha256:" + "c" * 64,
            )
        )
        with self.assertRaises(Refused) as caught:
            compare_identity_probe(profile, output)
        public = json.dumps(caught.exception.as_json())
        self.assertNotIn("192.0.2.44", public)
        self.assertNotIn("SERIAL-123456789", public)
        self.assertEqual(caught.exception.fields[0]["found"], "[redacted]")

    def test_native_identity_names_fields_and_redacts_device_id(self):
        profile = {
            "host": "192.0.2.8",
            "model": "MODEL-A",
            "platform": "PLAT-A",
            "device_id": "uuid:expected-secret",
        }
        response = {
            "device": {
                "modelName": "MODEL-B",
                "model": "PLAT-B",
                "id": "uuid:found-secret",
            }
        }
        stream = io.BytesIO(json.dumps(response).encode())

        class Opener:
            def open(self, *args, **kwargs):
                return stream

        with patch("tvsetup.native_cli.build_opener", return_value=Opener()):
            with self.assertRaises(Refused) as caught:
                identity(profile)
        refusal = caught.exception
        self.assertEqual(refusal.code, "CR-ID-DEVICE")
        self.assertIn("modelName", str(refusal))
        self.assertIn("model:", str(refusal))
        self.assertIn("id does not match site.json", str(refusal))
        serialized = json.dumps(refusal.as_json())
        self.assertNotIn("uuid:expected-secret", serialized)
        self.assertNotIn("uuid:found-secret", serialized)

    def test_agent_binding_names_fields_without_printing_host_values(self):
        from pathlib import Path

        from tvsetup.native_cli import agent_binding

        record = {
            "device": "private-device-id",
            "host": "192.0.2.45",
        }
        site = {"devices": {"qn90a": {"host": "192.0.2.46"}}}
        with patch(
            "tvsetup.native_cli.read_bounded",
            return_value=json.dumps(record).encode(),
        ):
            with self.assertRaises(Refused) as caught:
                agent_binding(site, "qn90a", Path("synthetic-agent.json"))
        refusal = caught.exception
        public = json.dumps(refusal.as_json())
        self.assertEqual(refusal.code, "CR-ID-DEVICE")
        self.assertTrue(
            str(refusal).startswith("Agent enrollment differs from site identity")
        )
        self.assertIn("device", public)
        self.assertIn("host", public)
        self.assertNotIn("private-device-id", public)
        self.assertNotIn("192.0.2.45", public)
        self.assertNotIn("192.0.2.46", public)


if __name__ == "__main__":
    unittest.main()
