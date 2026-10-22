import json
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tvsetup import autonomous_root_trial as trial
from tvsetup.common import Refused, sha


class UpdatePreflightTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.folders = {}
        for name in ("old", "new", "enrolled"):
            folder = self.root / name
            (folder / "provision").mkdir(parents=True)
            package = folder / "package.wgt"
            package.write_bytes(name.encode())
            provisioning = {}
            for filename in trial.PROVISION:
                data = (
                    b'{"enabled":false}' if filename == "config.json" else name.encode()
                )
                (folder / "provision" / filename).write_bytes(data)
                provisioning[filename] = sha(data)
            manifest = dict(
                device="s90d",
                target_binding={"fixture": True},
                package=str(package),
                package_sha256=sha(package.read_bytes()),
                provisioning=provisioning,
            )
            (folder / "manifest.json").write_text(json.dumps(manifest))
            self.folders[name] = folder
        self.enterContext(patch.object(trial, "configured_profile", return_value={}))
        self.enterContext(
            patch.object(trial, "binding", return_value={"fixture": True})
        )
        self.enterContext(
            patch.object(
                trial,
                "verify_package",
                side_effect=[
                    ({"same.js": b"old"}, "0.7.52"),
                    ({"same.js": b"new"}, "0.7.53"),
                ],
            )
        )
        self.transport = self.enterContext(
            patch.object(
                trial, "PilotTransport", side_effect=AssertionError("device accessed")
            )
        )

    def update(self, credentials=None):
        return trial.update(
            "s90d",
            self.folders["new"],
            self.folders["old"],
            {},
            credentials or self.folders["enrolled"],
        )

    def manifest(self, name, change):
        path = self.folders[name] / "manifest.json"
        value = json.loads(path.read_text())
        change(value)
        path.write_text(json.dumps(value))

    def test_client_json_is_not_a_provisioning_baseline(self):
        client = self.folders["enrolled"] / "client.json"
        client.write_text('{"device":"s90d"}')
        with self.assertRaisesRegex(Refused, "directory.*client.json"):
            self.update(client)
        self.transport.assert_not_called()

    def test_cli_reports_wrong_credentials_argument_without_traceback(self):
        client = self.folders["enrolled"] / "client.json"
        client.write_text("{}")
        args = [
            "trial",
            "--device",
            "s90d",
            "--artifact",
            str(self.folders["new"]),
            "--previous",
            str(self.folders["old"]),
            "--credentials",
            str(client),
            "--yes",
        ]
        with (
            patch("sys.argv", args),
            patch.object(trial, "load_site", return_value={}),
            patch("sys.stderr", new_callable=io.StringIO) as error,
        ):
            self.assertEqual(trial.main(), 1)
        self.assertIn("not client.json", error.getvalue())
        self.assertNotIn("Traceback", error.getvalue())
        self.transport.assert_not_called()

    def test_missing_or_non_object_manifest_refused_before_transport(self):
        for name in self.folders:
            path = self.folders[name] / "manifest.json"
            original = path.read_text()
            for text in (None, "null", "[]", '"text"', "{"):
                with self.subTest(name=name, text=text):
                    if text is None:
                        path.unlink()
                    else:
                        path.write_text(text)
                    with self.assertRaises(Refused):
                        self.update()
                    self.transport.assert_not_called()
                    path.write_text(original)

    def test_provisioning_files_must_exist_and_match_manifest(self):
        for filename in trial.PROVISION:
            path = self.folders["enrolled"] / "provision" / filename
            original = path.read_bytes()
            for data in (None, b"changed"):
                with self.subTest(filename=filename, data=data):
                    if data is None:
                        path.unlink()
                    else:
                        path.write_bytes(data)
                    with self.assertRaisesRegex(Refused, "provisioning"):
                        self.update()
                    self.transport.assert_not_called()
                    path.write_bytes(original)

    def test_disabled_config_is_checked_before_transport(self):
        for config in ({"enabled": True}, {}, [], None, {"enabled": 0}):
            with self.subTest(config=config):
                data = json.dumps(config).encode()
                (self.folders["enrolled"] / "provision/config.json").write_bytes(data)
                self.manifest(
                    "enrolled",
                    lambda m: m["provisioning"].update({"config.json": sha(data)}),
                )
                with self.assertRaisesRegex(Refused, "disabled"):
                    self.update()
                self.transport.assert_not_called()

    def test_incomplete_provisioning_record_is_not_synthesized(self):
        self.manifest("enrolled", lambda m: m["provisioning"].pop("client.pem"))
        with self.assertRaisesRegex(Refused, "provisioning"):
            self.update()
        self.transport.assert_not_called()

    def test_target_and_package_checks_are_retained(self):
        self.manifest("enrolled", lambda m: m.update(device="qn90a"))
        with self.assertRaisesRegex(Refused, "target binding"):
            self.update()
        self.manifest("enrolled", lambda m: m.update(device="s90d"))
        (self.folders["enrolled"] / "package.wgt").write_bytes(b"changed")
        with self.assertRaisesRegex(Refused, "Signed package changed"):
            self.update()
        self.transport.assert_not_called()

    def test_valid_separate_enrollment_reaches_transport(self):
        with (
            patch.object(trial, "lock"),
            patch.object(trial, "pending", return_value=[]),
        ):
            with self.assertRaisesRegex(AssertionError, "device accessed"):
                self.update()
        self.transport.assert_called_once()


if __name__ == "__main__":
    unittest.main()
