"""All reboot callers use the same hardware-reviewed systemd timer."""

import ast
from pathlib import Path
import shlex
import unittest

from tvsetup.common import REPO
from tvsetup.reboot import reboot_command


class RebootTests(unittest.TestCase):
    def test_every_submission_uses_reviewed_form(self):
        expected_callers = {
            "tvsetup/cli.py",
            "tvsetup/native_bootstrap_trial.py",
            "research/qn90a-hub-boot/manage.py",
        }
        found = set()
        for base in (REPO / "tvsetup", REPO / "research/qn90a-hub-boot"):
            for path in base.rglob("*.py"):
                tree = ast.parse(path.read_text())
                for node in ast.walk(tree):
                    if isinstance(node, ast.Constant) and isinstance(node.value, str):
                        self.assertNotRegex(node.value, r"nohup|systemctl\s+reboot")
                        if "Reboot s " in node.value:
                            self.assertEqual(path, REPO / "tvsetup/reboot.py")
                    if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                            and node.func.id == "reboot_command"):
                        continue
                    found.add(path.relative_to(REPO).as_posix())
                    unit, reason = [ast.literal_eval(arg) for arg in node.args]
                    self.assertEqual(shlex.split(reboot_command(unit, reason)), [
                        "systemd-run", "--unit=" + unit, "--on-active=10s",
                        "--timer-property=AccuracySec=1s", "-p", "Type=oneshot",
                        "-p", "User=0", "-p", "Group=0", "-p", "SmackProcessLabel=System",
                        "--setenv=DBUS_SYSTEM_BUS_ADDRESS=kernel:path=/sys/fs/kdbus/0-system/bus",
                        "/usr/bin/busctl", "--timeout=5", "--system", "call",
                        "org.tizen.system.deviced", "/Org/Tizen/System/DeviceD/Power",
                        "org.tizen.system.deviced.power", "Reboot", "s", reason,
                    ])
        self.assertEqual(found, expected_callers)
