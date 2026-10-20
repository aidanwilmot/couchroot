"""The native acquisition build must leave private outputs readable by its caller."""

import os
from pathlib import Path
import struct
import tempfile
import unittest

from tvsetup.config import profile
from tvsetup.native_root import FILES, build


class AcquisitionBuildTests(unittest.TestCase):
    def test_container_build_uses_callers_identity_for_private_outputs(self):
        calls = []

        def command(args):
            calls.append(args)
            if args[:3] == ["docker", "image", "inspect"]:
                return "sha256:" + "a" * 64
            if args[0] == "docker":
                self.assertIn("--user", args)
                self.assertEqual(args[args.index("--user") + 1],
                                 f"{os.getuid()}:{os.getgid()}")
                if "-dumpfullversion" in args:
                    return "10.2.1"
                if "arm-linux-gnueabi-readelf" in args:
                    return "(NEEDED) Shared library: [libc.so.6]\nGLIBC_2.17\n"
                output = Path(next(a[:-5] for a in args if a.endswith(":/out"))) / "native"
                output.mkdir(mode=0o700)
                data = bytearray(52)
                data[:7] = b"\x7fELF\x01\x01\x01"
                struct.pack_into("<HH", data, 16, 3, 40)
                struct.pack_into("<I", data, 36, 5 << 24)
                (output / "libacquire.so").write_bytes(data)
            else:
                self.assertEqual(args[0], "dotnet")
                output = Path(args[args.index("-o") + 1])
                output.mkdir()
                for name in FILES:
                    if not name.endswith(".so"):
                        (output / name).write_bytes(b"entry fixture")
            return ""

        for model in ("qn90a", "s90d"):
            with tempfile.TemporaryDirectory() as temp:
                output = Path(temp) / "bundle"
                manifest = build(profile(model), output, command, service=True)
                self.assertEqual(manifest["reproducible_builds"], 2)
                self.assertEqual(set(manifest["artifacts"]), set(FILES))
                for name in FILES:
                    self.assertTrue((output / "artifacts" / name).is_file())
        self.assertEqual(sum("/src/build.sh" in call for call in calls), 4)
