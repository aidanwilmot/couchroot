import importlib.util
from pathlib import Path
import sqlite3
import unittest

spec = importlib.util.spec_from_file_location('s90d_cleanup', Path(__file__).resolve().parents[1] / 'research/s90d-app-cleanup/remove.py')
cleanup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cleanup)


def fixture(packages):
    db = sqlite3.connect(':memory:')
    db.executescript('CREATE TABLE package_info(package TEXT); CREATE TABLE package_app_info(app_id TEXT, package TEXT);')
    for package in packages:
        db.execute('INSERT INTO package_info VALUES (?)', (package,))
        db.execute('INSERT INTO package_app_info VALUES (?,?)', (package + '.app', package))
    return db


class CleanupScopeTest(unittest.TestCase):
    def test_single_removal(self):
        cleanup.verify_scope(fixture(['junk', 'plex']), fixture(['plex']), {'junk'})

    def test_collateral_removal_refused(self):
        with self.assertRaises(RuntimeError):
            cleanup.verify_scope(fixture(['junk', 'plex']), fixture([]), {'junk'})

    def test_no_removal_refused(self):
        with self.assertRaises(RuntimeError):
            cleanup.verify_scope(fixture(['junk', 'plex']), fixture(['junk', 'plex']), {'junk'})

    def test_retained_app_registration_loss_refused(self):
        after = fixture(['plex'])
        after.execute('DELETE FROM package_app_info')
        with self.assertRaises(RuntimeError):
            cleanup.verify_scope(fixture(['junk', 'plex']), after, {'junk'})

    def test_keep_apps_excluded(self):
        self.assertFalse({'kIciSQlYEM', 'MCmYXNxgcu', 'org.tizen.primevideo', 'OGLLvqej7u', 'MiniHub001'} & cleanup.TARGETS.keys())


if __name__ == '__main__':
    unittest.main()
