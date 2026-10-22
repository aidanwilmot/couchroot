"""Exercise the exact embedded SQL against a synthetic routing DB, never the TV."""
from pathlib import Path
import sqlite3
import unittest

ROOT = Path(__file__).resolve().parents[1] / 'native/qn90a-home-route'

class HomeRouting(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(':memory:')
        self.db.executescript('''
          CREATE TABLE key_filter(appid TEXT, key TEXT, longpress TEXT, override TEXT,
            on_selector TEXT, request TEXT, target_selector TEXT, args TEXT);
          CREATE TABLE managed_app(appid TEXT, ui_type TEXT, source TEXT);
          CREATE TABLE task_filter(appid TEXT);
          INSERT INTO managed_app VALUES ('com.samsung.tv.csfs','partial',NULL);
          INSERT INTO key_filter VALUES ('com.samsung.tv.csfs','XF86Home',NULL,NULL,'',
            'launch','package:com.samsung.tv.csfs','entry_point:smarthub_key');
          INSERT INTO key_filter VALUES ('com.samsung.tv.csfs','XF86Display',NULL,NULL,'',
            'launch','package:com.samsung.tv.csfs','entry_point:source_key');
          INSERT INTO key_filter VALUES ('org.tizen.remote-management','XF86Home','5300',NULL,
            '~with-package:org.tizen.remote-management','launch','package:org.tizen.remote-management',NULL);
        ''')

    def rows(self):
        return tuple(list(self.db.execute('SELECT rowid,* FROM '+table)) for table in ('key_filter','managed_app'))

    def run_sql(self, mode):
        try:
            self.db.executescript((ROOT / (mode+'.sql')).read_text())
        except sqlite3.Error:
            self.db.rollback()
            raise

    def test_only_short_home_changes_and_restore_is_exact(self):
        before = self.rows()
        self.run_sql('apply')
        after = self.rows()
        self.assertEqual(before[0][1:], after[0][1:])
        self.assertEqual(after[0][0][-2:], ('package:MiniHub001.Hub', None))
        self.assertEqual(after[1][-1][1:], ('MiniHub001.Hub',None,None))
        self.run_sql('restore')
        self.assertEqual(self.rows(), before)

    def test_unknown_home_state_fails_without_partial_write(self):
        self.db.execute("UPDATE key_filter SET on_selector=NULL WHERE appid='com.samsung.tv.csfs' AND key='XF86Home'")
        self.db.commit()
        before = self.rows()
        with self.assertRaises(sqlite3.IntegrityError): self.run_sql('apply')
        self.assertEqual(self.rows(),before)

    def test_existing_hub_registration_is_not_overwritten(self):
        self.db.execute("INSERT INTO managed_app VALUES ('MiniHub001.Hub','partial',NULL)")
        self.db.commit()
        before = self.rows()
        with self.assertRaises(sqlite3.IntegrityError): self.run_sql('apply')
        self.assertEqual(self.rows(),before)

    def test_restore_requires_cast_rule_removal_first(self):
        self.run_sql('apply')
        self.db.execute("INSERT INTO task_filter VALUES ('MiniHub001.Hub')")
        self.db.commit(); before = self.rows()
        with self.assertRaises(sqlite3.IntegrityError): self.run_sql('restore')
        self.assertEqual(self.rows(), before)

    def test_restore_rejects_conflicting_changes(self):
        self.run_sql('apply')
        self.db.execute("UPDATE managed_app SET source='other' WHERE appid='MiniHub001.Hub'")
        self.db.commit()
        before = self.rows()
        with self.assertRaises(sqlite3.IntegrityError): self.run_sql('restore')
        self.assertEqual(self.rows(),before)

if __name__ == '__main__': unittest.main()
