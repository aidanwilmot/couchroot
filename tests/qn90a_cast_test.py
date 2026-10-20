"""Exercise the deployed casting SQL and exact rollback without contacting a TV."""
from pathlib import Path
import sqlite3
import unittest

ROOT = Path(__file__).resolve().parents[1] / 'setup/qn90a-home-route'

class CastRouting(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(':memory:')
        self.db.executescript('''
          CREATE TABLE managed_app(appid TEXT, ui_type TEXT, source TEXT);
          CREATE TABLE task_filter(appid TEXT, source_selector TEXT, source_event TEXT,
            request TEXT, target_selector TEXT, target TEXT, args TEXT);
          INSERT INTO managed_app VALUES ('MiniHub001.Hub',NULL,NULL);
          INSERT INTO task_filter VALUES ('other','package:other','stop','launch',
            'package:other',NULL,NULL);
        ''')

    def rows(self):
        return tuple(list(self.db.execute('SELECT rowid,* FROM '+table))
                     for table in ('managed_app','task_filter'))

    def run_sql(self, mode):
        try:
            self.db.executescript((ROOT / ('cast-'+mode+'.sql')).read_text())
        except sqlite3.Error:
            self.db.rollback()
            raise

    def test_scoped_pause_rule_and_exact_restore(self):
        before = self.rows()
        self.run_sql('apply')
        after = self.rows()
        self.assertEqual(after[0], before[0])
        self.assertEqual(after[1][:-1], before[1])
        self.assertEqual(after[1][-1][2:], (
            'package:NRi6kdBYJ0.AirPlayWebApp,~context:standby,vconf:(ready=memory/menu/network/airplay_status)',
            'pause','launch','package:MiniHub001.Hub',None,None))
        self.run_sql('restore')
        self.assertEqual(self.rows(), before)

    def test_early_rule_preserves_confirmed_return_and_restores_exactly(self):
        self.run_sql('apply'); before = self.rows()
        self.run_sql('early-apply')
        after = self.rows()
        self.assertEqual(after[1][:-1], before[1])
        self.assertEqual(after[1][-1][2:], (
            'package:com.samsung.tv.airplay-app,~context:standby,vconf:(ready=memory/menu/network/airplay_status)',
            'deactivate','launch','package:MiniHub001.Hub',None,None))
        with self.assertRaises(sqlite3.IntegrityError): self.run_sql('restore')
        self.assertEqual(self.rows(), after)
        self.run_sql('early-restore')
        self.assertEqual(self.rows(), before)

    def test_early_rule_requires_confirmed_return(self):
        before = self.rows()
        with self.assertRaises(sqlite3.IntegrityError): self.run_sql('early-apply')
        self.assertEqual(self.rows(), before)

    def test_early_restore_refuses_changed_rule(self):
        self.run_sql('apply'); self.run_sql('early-apply')
        self.db.execute("UPDATE task_filter SET source_event='stop' WHERE source_event='deactivate'")
        self.db.commit(); before = self.rows()
        with self.assertRaises(sqlite3.IntegrityError): self.run_sql('early-restore')
        self.assertEqual(self.rows(), before)

    def test_missing_hub_refuses_change(self):
        self.db.execute('DELETE FROM managed_app'); self.db.commit()
        before = self.rows()
        with self.assertRaises(sqlite3.IntegrityError): self.run_sql('apply')
        self.assertEqual(self.rows(), before)

    def test_duplicate_apply_refuses_change(self):
        self.run_sql('apply'); before = self.rows()
        with self.assertRaises(sqlite3.IntegrityError): self.run_sql('apply')
        self.assertEqual(self.rows(), before)

    def test_restore_refuses_conflicting_rule(self):
        self.run_sql('apply')
        self.db.execute("UPDATE task_filter SET source_event='stop' WHERE appid='MiniHub001.Hub'")
        self.db.commit(); before = self.rows()
        with self.assertRaises(sqlite3.IntegrityError): self.run_sql('restore')
        self.assertEqual(self.rows(), before)

if __name__ == '__main__': unittest.main()
