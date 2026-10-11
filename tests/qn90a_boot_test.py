"""Run deployed boot-routing SQL against realistic local fixtures; never a TV."""
from pathlib import Path
import sqlite3
import unittest

SQL_ROOT = Path(__file__).resolve().parents[1] / 'research/qn90a-hub-boot'
TABLES = ('key_filter', 'managed_app', 'task_filter')
BOOT = 'MiniHubBoot.Start'
HUB = 'MiniHub001.Hub'


def fixture():
    db = sqlite3.connect(':memory:')
    db.executescript('''
      CREATE TABLE managed_app(appid TEXT NOT NULL, ui_type TEXT, source TEXT,
        UNIQUE(appid,ui_type,source));
      CREATE TABLE key_filter(appid TEXT NOT NULL,key TEXT NOT NULL,longpress TEXT,
        override TEXT,on_selector TEXT,request TEXT NOT NULL,target_selector TEXT NOT NULL,
        args TEXT,UNIQUE(appid,key,longpress,override,on_selector,request,target_selector,args));
      CREATE TABLE task_filter(appid TEXT NOT NULL,source_selector TEXT NOT NULL,
        source_event TEXT NOT NULL,request TEXT NOT NULL,target_selector TEXT,target TEXT,
        args TEXT,UNIQUE(appid,source_selector,source_event,request,target_selector,target,args));
      INSERT INTO managed_app VALUES ('MiniHub001.Hub',NULL,NULL);
      INSERT INTO managed_app VALUES ('com.samsung.tv.csfs','partial',NULL);
      INSERT INTO key_filter(rowid,appid,key,on_selector,request,target_selector)
        VALUES (82,'com.samsung.tv.csfs','XF86Home','','launch','package:MiniHub001.Hub');
      INSERT INTO key_filter VALUES ('org.tizen.remote-management','XF86Home','5300',NULL,
        '~with-package:org.tizen.remote-management','launch','package:org.tizen.remote-management',NULL);
      INSERT INTO task_filter VALUES ('MiniHub001.Hub',
        'package:NRi6kdBYJ0.AirPlayWebApp,~context:standby,vconf:(ready=memory/menu/network/airplay_status)',
        'pause','launch','package:MiniHub001.Hub',NULL,NULL);
      INSERT INTO task_filter VALUES ('MiniHub001.Hub',
        'package:com.samsung.tv.airplay-app,~context:standby,vconf:(ready=memory/menu/network/airplay_status)',
        'deactivate','launch','package:MiniHub001.Hub',NULL,NULL);
      INSERT INTO task_filter VALUES ('unrelated','package:unrelated','stop','launch',
        'package:unrelated',NULL,NULL);
    ''')
    return db


class BootRouting(unittest.TestCase):
    def setUp(self):
        self.db = fixture()

    def tearDown(self):
        self.db.close()

    def rows(self):
        return tuple(tuple(self.db.execute('SELECT rowid,* FROM '+table+' ORDER BY rowid'))
                     for table in TABLES)

    def run_sql(self, name):
        try:
            self.db.executescript((SQL_ROOT / (name+'.sql')).read_text())
        except sqlite3.Error:
            self.db.rollback()
            raise

    def rejected_unchanged(self, name):
        self.db.commit()
        before = self.rows()
        with self.assertRaises(sqlite3.IntegrityError):
            self.run_sql(name)
        self.assertEqual(self.rows(), before)
        self.assertFalse(self.db.in_transaction)

    def test_install_preserves_every_existing_row_and_rollback_is_exact(self):
        before = self.rows()
        self.run_sql('install')
        after = self.rows()
        self.assertEqual(after[0], before[0])
        self.assertEqual(after[1][:-1], before[1])
        self.assertEqual(after[2][:-1], before[2])
        self.assertEqual(after[1][-1][1:], (BOOT,None,None))
        # Read the installed rule, so the tested exact rollback follows the
        # selected boot event if live firmware evidence requires changing it.
        row = after[2][-1]
        self.assertEqual(row[1], BOOT)
        self.assertEqual('package:org.tizen.welcome-mode', row[2])
        self.assertEqual('start', row[3])
        self.assertEqual(row[4:], ('launch','package:'+BOOT,None,None))
        self.run_sql('rollback')
        self.assertEqual(self.rows(), before)
        self.assertEqual(self.db.execute('PRAGMA quick_check').fetchone()[0], 'ok')

    def test_repeat_install_and_rollback_refuse_without_changes(self):
        self.run_sql('install')
        self.rejected_unchanged('install')
        self.run_sql('rollback')
        self.rejected_unchanged('rollback')

    def test_home_shape_conflicts_refuse_install(self):
        fields = {'appid':'other','key':'XF86Display','longpress':'5000',
                  'override':'true','on_selector':None,'request':'pause',
                  'target_selector':'package:other','args':'entry_point:other'}
        for field,value in fields.items():
            with self.subTest(field=field):
                self.db.close(); self.db = fixture()
                self.db.execute('UPDATE key_filter SET '+field+'=? WHERE rowid=82',(value,))
                self.rejected_unchanged('install')

    def test_duplicate_home_refuses_install(self):
        self.db.execute('INSERT INTO key_filter SELECT * FROM key_filter WHERE rowid=82')
        self.rejected_unchanged('install')

    def test_each_cast_rule_shape_conflict_refuses_install(self):
        fields = {'source_selector':'package:other','source_event':'stop','request':'pause',
                  'target_selector':'package:other','target':'self','args':'other'}
        for event in ('pause','deactivate'):
            for field,value in fields.items():
                with self.subTest(event=event,field=field):
                    self.db.close(); self.db = fixture()
                    self.db.execute('UPDATE task_filter SET '+field+'=? WHERE appid=? AND source_event=?',
                                    (value,HUB,event))
                    self.rejected_unchanged('install')

    def test_missing_or_extra_cast_rule_refuses_install(self):
        self.db.execute('DELETE FROM task_filter WHERE appid=? AND source_event=?',(HUB,'pause'))
        self.rejected_unchanged('install')
        self.db.close(); self.db = fixture()
        self.db.execute('INSERT INTO task_filter SELECT * FROM task_filter WHERE appid=? AND source_event=?',
                        (HUB,'pause'))
        self.rejected_unchanged('install')

    def test_missing_or_conflicting_hub_registration_refuses_install(self):
        self.db.execute('DELETE FROM managed_app WHERE appid=?',(HUB,))
        self.rejected_unchanged('install')
        self.db.close(); self.db = fixture()
        self.db.execute('UPDATE managed_app SET ui_type=? WHERE appid=?',('partial',HUB))
        self.rejected_unchanged('install')

    def test_existing_boot_registration_or_rule_refuses_install(self):
        self.db.execute('INSERT INTO managed_app VALUES (?,?,?)',(BOOT,'partial','other'))
        self.rejected_unchanged('install')
        self.db.close(); self.db = fixture()
        self.db.execute('INSERT INTO task_filter VALUES (?,?,?,?,?,?,?)',
                        (BOOT,'package:other','run','launch','package:'+BOOT,None,None))
        self.rejected_unchanged('install')

    def test_partial_install_failure_rolls_back_registration(self):
        self.db.executescript("CREATE TRIGGER fail_boot BEFORE INSERT ON task_filter "
                             "WHEN NEW.appid='MiniHubBoot.Start' BEGIN SELECT RAISE(ABORT,'probe'); END;")
        self.rejected_unchanged('install')

    def test_conflicting_extra_managed_row_is_never_deleted(self):
        self.run_sql('install')
        self.db.execute('INSERT INTO managed_app VALUES (?,?,?)',(BOOT,'partial','other'))
        self.rejected_unchanged('rollback')

    def test_changed_managed_registration_refuses_rollback(self):
        self.run_sql('install')
        self.db.execute('UPDATE managed_app SET source=? WHERE appid=?',('other',BOOT))
        self.rejected_unchanged('rollback')

    def test_changed_or_duplicate_boot_rule_refuses_rollback(self):
        fields = {'source_selector':'package:other','source_event':'stop','request':'pause',
                  'target_selector':'package:other','target':'self','args':'other'}
        for field,value in fields.items():
            with self.subTest(field=field):
                self.db.close(); self.db = fixture(); self.run_sql('install')
                self.db.execute('UPDATE task_filter SET '+field+'=? WHERE appid=?',(value,BOOT))
                self.rejected_unchanged('rollback')
        self.db.close(); self.db = fixture(); self.run_sql('install')
        self.db.execute('INSERT INTO task_filter SELECT * FROM task_filter WHERE appid=?',(BOOT,))
        self.rejected_unchanged('rollback')

    def test_rollback_keeps_unrelated_changes_made_after_install(self):
        self.run_sql('install')
        self.db.execute("UPDATE key_filter SET args='new-user-setting' WHERE rowid!=82")
        self.db.execute("UPDATE task_filter SET args='new-user-setting' WHERE appid='unrelated'")
        self.db.commit()
        before = self.rows()
        self.run_sql('rollback')
        self.assertEqual(self.rows(),tuple(tuple(row for row in rows if row[1]!=BOOT) for rows in before))


if __name__ == '__main__':
    unittest.main()
