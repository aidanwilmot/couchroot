"""Diagnostic sampler tests. Process-tree sampling needs Linux /proc."""
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "procsample.c"
FLAGS = ["-std=c99", "-Wall", "-Wextra", "-Werror"]


class ProcsampleTests(unittest.TestCase):
    def test_compiles_cleanly(self):
        subprocess.run(["cc", *FLAGS, "-fsyntax-only", str(SOURCE)], check=True)

    def test_rejects_relative_prefix_and_unbounded_runs(self):
        with tempfile.TemporaryDirectory() as temp:
            binary = Path(temp) / "procsample"
            subprocess.run(["cc", *FLAGS, str(SOURCE), "-o", str(binary)], check=True)
            for args in (["opt/hub", "1", "100"], ["/opt/hub", "0", "100"], ["/opt/hub", "601", "100"],
                         ["/opt/hub", "1", "5"]):
                with self.subTest(args=args):
                    self.assertEqual(subprocess.run([str(binary), temp, *args]).returncode, 2)

    @unittest.skipUnless(sys.platform.startswith("linux"), "needs Linux /proc")
    def test_samples_only_the_hub_tree_and_reports_memory(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            binary, install, out = root / "procsample", root / "hub", root / "out"
            (install / "bin").mkdir(parents=True); out.mkdir()
            subprocess.run(["cc", *FLAGS, str(SOURCE), "-o", str(binary)], check=True)
            hub_shell = install / "bin/native-hub"
            shutil.copy(shutil.which("sh"), hub_shell)
            hub = subprocess.Popen([str(hub_shell), "-c", "sleep 3 & wait"])
            other = subprocess.Popen(["sleep", "3"])
            try:
                time.sleep(0.3)
                subprocess.run([str(binary), str(out), str(install), "0.5", "100", "0.2"], check=True, timeout=10)
                pids = {line.split("\t")[1] for line in (out / "samples").read_text().splitlines()}
                self.assertIn(str(hub.pid), pids)
                self.assertNotIn(str(other.pid), pids)
                self.assertEqual(len(pids), 2)  # The Hub root and its sleep child.
                memory = (out / "memory").read_text()
                self.assertIn("snapshot\tt+0.2\t", memory)
                self.assertIn("snapshot\tend\t", memory)
                self.assertEqual(memory.count("\nprocess\t"), 4)
                system = (out / "system").read_text()
                self.assertRegex(system, r"(?m)^stat\t[0-9.]+\tcpu ")
                self.assertRegex(system, rf"(?m)^proc\t[0-9.]+\t{other.pid}\t")  # Every process, not just the Hub.
            finally:
                hub.kill(); other.kill(); hub.wait(); other.wait()

    @unittest.skipUnless(sys.platform.startswith("linux"), "needs Linux /proc")
    def test_finds_a_process_that_later_execs_the_hub(self):
        # systemd starts the Hub through /bin/sh -c 'exec native-hub ...'.
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            binary, install, out = root / "procsample", root / "hub", root / "out"
            (install / "bin").mkdir(parents=True); out.mkdir()
            subprocess.run(["cc", *FLAGS, str(SOURCE), "-o", str(binary)], check=True)
            hub_sleep = install / "bin/native-hub"
            shutil.copy(shutil.which("sleep"), hub_sleep)
            late = subprocess.Popen(["sh", "-c", f"sleep 0.4; exec {hub_sleep} 3"])
            try:
                subprocess.run([str(binary), str(out), str(install) + "/", "1.6", "100"], check=True, timeout=10)
                lines = [line.split("\t") for line in (out / "samples").read_text().splitlines()]
                self.assertIn(str(late.pid), {line[1] for line in lines})
                self.assertIn("native-hub", {line[4] for line in lines if line[1] == str(late.pid)})
            finally:
                late.kill(); late.wait()


if __name__ == "__main__":
    unittest.main()
