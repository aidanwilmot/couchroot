import multiprocessing
from pathlib import Path
import tempfile
import time
import unittest

from tools.toolkit.sdb_connection import connect_if_needed


class Result:
    def __init__(self, stdout="", returncode=0):
        self.stdout = stdout
        self.returncode = returncode


class FakeClient:
    serial = "192.0.2.15:26101"

    def __init__(self, listing="", connect_error=None, listing_error=None, after_connect=None):
        self.listing = listing
        self.connect_error = connect_error
        self.listing_error = listing_error
        self.after_connect = after_connect
        self.connect_calls = 0
        self.calls = []

    def run(self, args, check=False):
        self.calls.append((args, check))
        if self.listing_error:
            raise self.listing_error
        return Result(self.listing)

    def connect(self):
        self.connect_calls += 1
        if self.connect_error:
            raise self.connect_error
        if self.after_connect is not None:
            self.listing = self.after_connect


def _race_worker(lock_dir, ready, count, barrier):
    class SharedClient:
        serial = "192.0.2.15:26101"

        def run(self, args, check=False):
            return Result(f"{self.serial}\t{'device' if ready.value else 'offline'}\n")

        def connect(self):
            with count.get_lock():
                count.value += 1
            time.sleep(0.15)
            ready.value = 1

    barrier.wait(timeout=5)
    client = SharedClient()
    connect_if_needed(client, Path(lock_dir), client.connect)


class SdbConnectionTest(unittest.TestCase):
    def test_ready_exact_target_is_reused_and_other_target_ignored(self):
        client = FakeClient(listing="List of devices attached\n192.0.2.15:26101 device\n192.0.2.99:26101 offline\n")
        with tempfile.TemporaryDirectory() as directory:
            connect_if_needed(client, Path(directory), client.connect)
        self.assertEqual(client.connect_calls, 0)
        self.assertEqual(client.calls, [(("devices",), True)])

    def test_absent_and_offline_targets_connect_then_verify_ready(self):
        for initial in ("List of devices attached\n", "192.0.2.15:26101 offline\n"):
            client = FakeClient(listing=initial, after_connect="192.0.2.15:26101 device\n")
            with tempfile.TemporaryDirectory() as directory:
                connect_if_needed(client, Path(directory), client.connect)
            self.assertEqual(client.connect_calls, 1)
            self.assertEqual(len(client.calls), 2)

    def test_listing_failure_propagates_without_connect(self):
        client = FakeClient(listing_error=RuntimeError("devices failed"))
        with tempfile.TemporaryDirectory() as directory, self.assertRaisesRegex(RuntimeError, "devices failed"):
            connect_if_needed(client, Path(directory), client.connect)
        self.assertEqual(client.connect_calls, 0)

    def test_connect_failure_propagates(self):
        client = FakeClient(connect_error=RuntimeError("connect failed"))
        with tempfile.TemporaryDirectory() as directory, self.assertRaisesRegex(RuntimeError, "connect failed"):
            connect_if_needed(client, Path(directory), client.connect)

    def test_connect_success_without_ready_target_fails(self):
        client = FakeClient(listing="", after_connect="192.0.2.15:26101 offline\n")
        with tempfile.TemporaryDirectory() as directory, self.assertRaisesRegex(RuntimeError, "offline, not ready"):
            connect_if_needed(client, Path(directory), client.connect)

    def test_separate_processes_serialize_check_connect(self):
        context = multiprocessing.get_context("spawn")
        with tempfile.TemporaryDirectory() as directory:
            ready = context.Value("i", 0)
            count = context.Value("i", 0)
            barrier = context.Barrier(2)
            processes = [context.Process(target=_race_worker, args=(directory, ready, count, barrier)) for _ in range(2)]
            for process in processes:
                process.start()
            for process in processes:
                process.join(10)
            for process in processes:
                if process.is_alive():
                    process.terminate()
                    process.join()
                self.assertEqual(process.exitcode, 0)
            self.assertEqual(ready.value, 1)
            self.assertEqual(count.value, 1)

    def test_lock_wait_is_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            lock_dir = Path(directory)
            import fcntl
            import hashlib
            import os
            lock_path = lock_dir / f"sdb-connect-{hashlib.sha256(FakeClient.serial.encode()).hexdigest()}.lock"
            fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX)
                client = FakeClient(listing=f"{FakeClient.serial} device\n")
                with self.assertRaisesRegex(TimeoutError, "Timed out waiting"):
                    connect_if_needed(client, lock_dir, client.connect, lock_timeout=0.05)
                self.assertEqual(client.calls, [])
            finally:
                os.close(fd)


if __name__ == "__main__":
    unittest.main()
