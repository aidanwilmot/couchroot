"""The client submits once and retains an uncertain request for inspection."""
import tempfile
import unittest
from pathlib import Path
from tvsetup.common import Refused, read_json
from tvsetup.native_upgrade import invoke


class NativeUpgradeClientTests(unittest.TestCase):
    def test_read_only_review_and_status(self):
        calls = []
        def call(*args):
            calls.append(args)
            return {"sha256": "a" * 64}
        for device in ("qn90a", "s90d"):
            invoke(device, {"device": device}, "review", target="previous", call=call)
            invoke(device, {"device": device}, "status", call=call)
        self.assertTrue(all(row[1] == "GET" for row in calls))
        self.assertEqual(calls[0][2], "/v1/native/upgrade?target=previous")

    def test_wrong_device_and_missing_approval_never_contact(self):
        def forbidden(*args):
            self.fail("Unexpected device contact")
        for credentials, yes in (({"device": "qn90a"}, True), ({"device": "s90d"}, False)):
            with self.assertRaises(Refused):
                invoke("s90d", credentials, "apply", yes=yes, call=forbidden)

    def test_changed_review_refuses_before_post(self):
        with tempfile.TemporaryDirectory() as root:
            calls = []
            def call(*args):
                calls.append(args)
                return {"sha256": "b" * 64}
            with self.assertRaises(Refused):
                invoke("s90d", {"device": "s90d"}, "apply", yes=True,
                       reviewed="a" * 64, evidence=Path(root)/"attempt", call=call)
            self.assertEqual([row[1] for row in calls], ["GET"])

    def test_lost_reply_is_durable_and_never_replayed(self):
        with tempfile.TemporaryDirectory() as root:
            evidence = Path(root)/"attempt"
            posts = []
            def call(*args):
                if args[1] == "GET":
                    return {"sha256": "a" * 64}
                posts.append(args)
                self.assertEqual(read_json(evidence/"intent.json")["body"], args[3])
                raise TimeoutError("reply lost")
            for expected in (TimeoutError, FileExistsError):
                with self.assertRaises(expected):
                    invoke("s90d", {"device": "s90d"}, "apply", yes=True,
                           reviewed="a" * 64, evidence=evidence, call=call)
            self.assertEqual(len(posts), 1)
            self.assertFalse((evidence/"response.json").exists())
