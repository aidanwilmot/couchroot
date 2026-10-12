"""Removal scope/protection guards; no TV access."""
import importlib.util
from pathlib import Path
import sqlite3
import unittest

spec = importlib.util.spec_from_file_location('cleanup', Path(__file__).resolve().parents[1] / 'tools/qn90a/cleanup.py')
cleanup = importlib.util.module_from_spec(spec); spec.loader.exec_module(cleanup)


def fixture():
    db = sqlite3.connect(':memory:')
    db.executescript('''
      CREATE TABLE package_info(package TEXT,package_type TEXT,package_removable TEXT,
        package_preload TEXT,package_readonly TEXT,package_system TEXT,package_version TEXT,mainapp_id TEXT);
      CREATE TABLE package_app_info(app_id TEXT,package TEXT);
      CREATE TABLE package_dependency_info(package TEXT,depends_on TEXT);
      INSERT INTO package_info VALUES ('9FhM0cODbY','wgt','true','false','false','false','1.1.8','9FhM0cODbY.TikTokTV');
      INSERT INTO package_info VALUES ('kIciSQlYEM','wgt','true','false','false','false','1','kIciSQlYEM.plex');
      INSERT INTO package_app_info VALUES ('9FhM0cODbY.TikTokTV','9FhM0cODbY');
      INSERT INTO package_app_info VALUES ('kIciSQlYEM.plex','kIciSQlYEM');
      ATTACH DATABASE ':memory:' AS was;
      CREATE TABLE was.widgetinfo(id TEXT,pkgname TEXT,tizen_id TEXT,is_removable INT,is_system INT,is_lock INT,install_state INT,is_app_available INT,is_need_reset INT);
      INSERT INTO was.widgetinfo VALUES ('3202008021577','9FhM0cODbY','9FhM0cODbY.TikTokTV',1,0,0,3,1,0);
      INSERT INTO was.widgetinfo VALUES ('plex-store-id','kIciSQlYEM','kIciSQlYEM.plex',1,0,0,3,1,0);
    ''')
    return db


class CleanupGuards(unittest.TestCase):
    def setUp(self): self.before, self.after = fixture(), fixture()
    def test_streaming_app_is_never_eligible(self):
        with self.assertRaises(ValueError): cleanup.validate_target(self.after,self.before,'kIciSQlYEM')
    def test_changed_system_flags_refuse_removal(self):
        self.after.execute("UPDATE package_info SET package_system='true' WHERE package='9FhM0cODbY'")
        with self.assertRaises(ValueError): cleanup.validate_target(self.after,self.before,'9FhM0cODbY')
    def test_dependency_refuses_removal(self):
        self.after.execute("INSERT INTO package_dependency_info VALUES ('other','9FhM0cODbY')")
        with self.assertRaises(ValueError): cleanup.validate_target(self.after,self.before,'9FhM0cODbY')
    def test_version_change_refuses_removal(self):
        self.after.execute("UPDATE package_info SET package_version='2' WHERE package='9FhM0cODbY'")
        with self.assertRaises(ValueError): cleanup.validate_target(self.after,self.before,'9FhM0cODbY')
    def test_only_target_removed_passes(self):
        cleanup.validate_target(self.after,self.before,'9FhM0cODbY')
        for t in ['package_info','package_app_info']: self.after.execute('DELETE FROM '+t+" WHERE package='9FhM0cODbY'")
        cleanup.verify_scope(self.before,self.after,'9FhM0cODbY')
    def test_unrelated_removal_is_detected(self):
        for t in ['package_info','package_app_info']: self.after.execute('DELETE FROM '+t)
        with self.assertRaises(RuntimeError): cleanup.verify_scope(self.before,self.after,'9FhM0cODbY')
    def test_package_left_installed_is_not_success(self):
        with self.assertRaises(RuntimeError): cleanup.verify_scope(self.before,self.after,'9FhM0cODbY')
    def test_wrong_main_app_refuses_removal(self):
        self.after.execute("UPDATE package_info SET mainapp_id='wrong' WHERE package='9FhM0cODbY'")
        with self.assertRaises(ValueError): cleanup.validate_target(self.after,self.before,'9FhM0cODbY')
    def test_unrelated_app_changed_with_package_intact_is_detected(self):
        for t in ['package_info','package_app_info']: self.after.execute('DELETE FROM '+t+" WHERE package='9FhM0cODbY'")
        self.after.execute("UPDATE package_app_info SET app_id='changed' WHERE package='kIciSQlYEM'")
        with self.assertRaises(RuntimeError): cleanup.verify_scope(self.before,self.after,'9FhM0cODbY')
    def test_catalog_requires_unlocked_removable_app(self):
        cleanup.validate_catalog(self.after,self.before,'9FhM0cODbY')
        self.after.execute("UPDATE was.widgetinfo SET is_lock=1 WHERE pkgname='9FhM0cODbY'")
        with self.assertRaises(ValueError): cleanup.validate_catalog(self.after,self.before,'9FhM0cODbY')
    def test_catalog_identity_change_refuses_removal(self):
        self.after.execute("UPDATE was.widgetinfo SET id='different' WHERE pkgname='9FhM0cODbY'")
        with self.assertRaises(ValueError): cleanup.validate_catalog(self.after,self.before,'9FhM0cODbY')
    def test_catalog_removal_verifies_only_target(self):
        self.after.execute("DELETE FROM was.widgetinfo WHERE pkgname='9FhM0cODbY'")
        cleanup.verify_catalog(self.before,self.after,'9FhM0cODbY')
        self.after.execute("DELETE FROM was.widgetinfo WHERE pkgname='kIciSQlYEM'")
        with self.assertRaises(RuntimeError): cleanup.verify_catalog(self.before,self.after,'9FhM0cODbY')

if __name__ == '__main__': unittest.main()
