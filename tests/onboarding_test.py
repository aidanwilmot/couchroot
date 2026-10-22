"""Onboarding actions use mocks and synthetic reserved addresses only."""

import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from tvsetup import onboarding
from tvsetup.common import Refused
from tvsetup.config import profile


def identity(device="s90d"):
    value = profile(device)
    return {
        "modelName": value["model"],
        "model": value["platform"],
        "developerMode": "1",
        "developerIP": "192.0.2.24",
        "id": "uuid:00000000-0000-4000-8000-000000000001",
        "name": "private-tv-name",
        "token": "private-token",
    }


class DoctorTests(unittest.TestCase):
    def test_success_checks_use_one_identity_read_and_show_only_computer_address(self):
        data = identity()
        with (
            patch.object(onboarding, "read_identity", return_value=data) as read,
            patch.object(onboarding, "_routed_address", return_value="192.0.2.24"),
            patch.object(onboarding.socket, "create_connection") as connect,
        ):
            result = onboarding.doctor("192.0.2.20")
        read.assert_called_once_with("192.0.2.20")
        connect.assert_called_once_with(("192.0.2.20", 26101), timeout=5)
        self.assertTrue(result["ok"])
        self.assertEqual(
            [check["status"] for check in result["checks"]], ["passed"] * 4
        )
        encoded = json.dumps(result)
        for private in (
            "192.0.2.20",
            data["id"],
            data["name"],
            data["token"],
        ):
            self.assertNotIn(private, encoded)
        self.assertIn(
            "Set Developer Mode's host IP to 192.0.2.24 (this computer)", encoded
        )

    def test_failed_identity_still_checks_sdb_and_never_discloses_error(self):
        with (
            patch.object(
                onboarding,
                "read_identity",
                side_effect=Refused("private address and token should not escape"),
            ) as read,
            patch.object(onboarding, "_routed_address", return_value="198.51.100.24"),
            patch.object(
                onboarding.socket,
                "create_connection",
                side_effect=OSError("192.0.2.20"),
            ),
        ):
            result = onboarding.doctor("192.0.2.20")
        read.assert_called_once()
        self.assertFalse(result["ok"])
        self.assertEqual(
            [check["status"] for check in result["checks"]],
            ["failed", "unknown", "unknown", "failed"],
        )
        self.assertNotIn("private address", json.dumps(result))
        self.assertNotIn("192.0.2.20", json.dumps(result))
        self.assertIn(
            "Set Developer Mode's host IP to 198.51.100.24 (this computer)",
            json.dumps(result),
        )

    def test_developer_host_mismatch_shows_computer_address_and_redacts_tv_identity(
        self,
    ):
        data = {**identity(), "developerMode": "0", "developerIP": "192.0.2.99"}
        with (
            patch.object(onboarding, "read_identity", return_value=data),
            patch.object(onboarding, "_routed_address", return_value="192.0.2.24"),
            patch.object(onboarding.socket, "create_connection"),
        ):
            result = onboarding.doctor("192.0.2.20")
        self.assertEqual(
            [check["status"] for check in result["checks"]],
            ["passed", "failed", "failed", "passed"],
        )
        self.assertNotIn("192.0.2.99", json.dumps(result))
        self.assertNotIn(data["id"], json.dumps(result))
        self.assertNotIn("192.0.2.20", json.dumps(result))
        self.assertEqual(
            result["checks"][2]["hint"],
            "Set Developer Mode's host IP to 192.0.2.24 (this computer)",
        )

    def test_missing_developer_ip_is_unknown_not_a_mismatch(self):
        data = identity()
        data.pop("developerIP")
        with (
            patch.object(onboarding, "read_identity", return_value=data),
            patch.object(
                onboarding, "_routed_address", return_value="192.0.2.24"
            ) as route,
            patch.object(onboarding.socket, "create_connection"),
        ):
            result = onboarding.doctor("192.0.2.20")
        self.assertEqual(result["checks"][2]["status"], "unknown")
        route.assert_called_once_with("192.0.2.20")
        self.assertIn("192.0.2.24 (this computer)", result["checks"][2]["hint"])

    def test_route_lookup_failure_keeps_host_unknown_without_leaking_errors(self):
        with (
            patch.object(onboarding, "read_identity", return_value=identity()),
            patch.object(
                onboarding,
                "_routed_address",
                side_effect=OSError("private route 192.0.2.20"),
            ),
            patch.object(onboarding.socket, "create_connection"),
        ):
            result = onboarding.doctor("192.0.2.20")
        self.assertEqual(result["checks"][2]["status"], "unknown")
        self.assertNotIn("192.0.2.", json.dumps(result))


class InitTests(unittest.TestCase):
    def test_exact_model_writes_private_site_once_and_never_returns_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary) / "private"
            destination = folder / "site.json"
            old_umask = os.umask(0)
            try:
                with patch.object(
                    onboarding, "read_identity", return_value=identity("qn90a")
                ) as read:
                    result = onboarding.init("192.0.2.21", destination)
            finally:
                os.umask(old_umask)
            read.assert_called_once_with("192.0.2.21")
            self.assertTrue(result["written"])
            self.assertEqual(result["device"], "qn90a")
            self.assertTrue(result["firmware_check_required"])
            self.assertEqual(stat.S_IMODE(folder.stat().st_mode), 0o700)
            self.assertEqual(stat.S_IMODE(destination.stat().st_mode), 0o600)
            self.assertEqual(
                json.loads(destination.read_text()),
                {
                    "devices": {
                        "qn90a": {
                            "host": "192.0.2.21",
                            "device_id": identity("qn90a")["id"],
                        }
                    }
                },
            )
            self.assertNotIn(identity("qn90a")["id"], json.dumps(result))
            with patch.object(
                onboarding, "read_identity", return_value=identity("qn90a")
            ):
                with self.assertRaisesRegex(Refused, "already exists"):
                    onboarding.init("192.0.2.21", destination)

    def test_init_refuses_nonmatching_model_and_hostname_without_writing(self):
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "private" / "site.json"
            unsupported = {**identity(), "modelName": "QN77S89CBFXZA"}
            with patch.object(onboarding, "read_identity", return_value=unsupported):
                with self.assertRaisesRegex(Refused, "Unsupported TV model"):
                    onboarding.init("192.0.2.21", destination)
            self.assertFalse(destination.exists())
            with patch.object(onboarding, "read_identity") as read:
                with self.assertRaisesRegex(Refused, "IPv4 address"):
                    onboarding.init("tv.example.invalid", destination)
            read.assert_not_called()

    def test_init_refuses_symlink_parent_and_invalid_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            real = root / "real"
            real.mkdir(mode=0o700)
            link = root / "link"
            link.symlink_to(real, target_is_directory=True)
            with (
                patch.object(onboarding, "read_identity", return_value=identity()),
                patch.object(onboarding, "DEFAULT_SITE", link / "site.json"),
            ):
                result = onboarding.init("192.0.2.21")
            self.assertEqual(Path(result["path"]).parent, real.resolve())
            self.assertTrue((real.resolve() / "site.json").is_file())
            with patch.object(
                onboarding,
                "read_identity",
                return_value={**identity(), "id": "secret-id"},
            ):
                with self.assertRaisesRegex(Refused, "already exists"):
                    onboarding.init("192.0.2.21", real / "site.json")

    def test_existing_site_path_is_refused_before_identity_read(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "site.json"
            path.write_text("already here")
            with patch.object(onboarding, "read_identity") as read:
                with self.assertRaisesRegex(Refused, "will not be overwritten"):
                    onboarding.init("192.0.2.21", path)
            read.assert_not_called()


class TrustEntryTests(unittest.TestCase):
    def test_explicit_local_certificates_are_hashed_as_der(self):
        with tempfile.TemporaryDirectory() as temporary:
            author = Path(temporary) / "author.pem"
            distributor = Path(temporary) / "distributor.cer"
            author.write_text("synthetic author certificate")
            distributor.write_text("synthetic distributor certificate")
            der = {
                str(author): b"author DER bytes",
                str(distributor): b"distributor DER bytes",
            }

            def openssl(args, **kwargs):
                return SimpleNamespace(
                    returncode=0, stdout=der[args[args.index("-in") + 1]]
                )

            with patch.object(onboarding.subprocess, "run", side_effect=openssl) as run:
                entry = onboarding.trust_entry(
                    "s90d", "profile-one", author, distributor
                )
            self.assertEqual(
                entry,
                {
                    "s90d": {
                        "signing_profile": "profile-one",
                        "author_cert_sha256": hashlib.sha256(
                            der[str(author)]
                        ).hexdigest(),
                        "distributor_cert_sha256": hashlib.sha256(
                            der[str(distributor)]
                        ).hexdigest(),
                    }
                },
            )
            self.assertEqual(run.call_count, 2)
            self.assertNotIn("synthetic author certificate", json.dumps(entry))

    def test_invalid_certificate_or_profile_is_refused(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "invalid.pem"
            path.write_text("not a certificate")
            with patch.object(
                onboarding.subprocess,
                "run",
                return_value=SimpleNamespace(returncode=1, stdout=b""),
            ):
                with self.assertRaisesRegex(Refused, "local X.509"):
                    onboarding.trust_entry("s90d", "profile-one", path, path)
            with self.assertRaisesRegex(Refused, "signing profile"):
                onboarding.trust_entry("s90d", "../unsafe", path, path)

    @unittest.skipUnless(shutil.which("openssl"), "local OpenSSL is required")
    def test_generated_local_certificates_hash_their_der_encoding(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            certs = []
            expected_hashes = []
            for name in ("author", "distributor"):
                key = root / f"{name}.key"
                pem = root / f"{name}.pem"
                subprocess.run(
                    [
                        "openssl",
                        "req",
                        "-x509",
                        "-newkey",
                        "rsa:2048",
                        "-nodes",
                        "-keyout",
                        str(key),
                        "-out",
                        str(pem),
                        "-days",
                        "1",
                        "-subj",
                        f"/CN=synthetic-{name}",
                    ],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                der = subprocess.run(
                    ["openssl", "x509", "-in", str(pem), "-outform", "DER"],
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                ).stdout
                der_path = root / f"{name}.der"
                der_path.write_bytes(der)
                certs.append((pem, der_path))
                expected_hashes.append(hashlib.sha256(der).hexdigest())
            entry = onboarding.trust_entry(
                "qn90a", "synthetic-profile", certs[0][0], certs[1][1]
            )
            self.assertEqual(entry["qn90a"]["author_cert_sha256"], expected_hashes[0])
            self.assertEqual(
                entry["qn90a"]["distributor_cert_sha256"], expected_hashes[1]
            )


if __name__ == "__main__":
    unittest.main()
