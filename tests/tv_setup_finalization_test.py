"""Crash boundaries for local state publication and interrupted reverse operations."""
import copy
import errno
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from tvsetup.common import Refused, atomic_json, read_json
from tvsetup.engine import Engine, pending
from tvsetup.planner import Action, Plan
from tv_setup_engine_test import FakeDriver


class FinalizationTests(unittest.TestCase):
    def case(self,root,device):
        driver=FakeDriver()
        engine=Engine(driver,root/'runs'/'test',device,{'keep':['fixture']},state_dir=root)
        plan=Plan(device,actions=[Action('1','telemetry','file',None,'new',{'path':'/test'})])
        engine.start(plan,driver.snapshot())
        return driver,engine

    def test_completed_mutations_remain_pending_until_local_state_is_durable(self):
        for device in ('qn90a','s90d'):
            with self.subTest(device=device),tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);driver,e=self.case(root,device)
                self.assertEqual(read_json(e.path)['phase'],'configuration-applied')
                self.assertEqual(len(pending(root,device)),1)
                resumed=Engine(None,e.folder,device,e.choices,state_dir=root);resumed.load()
                resumed.reconcile();resumed.apply();resumed.finalize()
                self.assertEqual(driver.executions,1);self.assertFalse(pending(root,device))
                self.assertEqual(read_json(root/(device+'-choices.json')),e.choices)

    def test_disk_full_at_every_finalization_write_resumes_without_device_contact(self):
        # Covers transaction intent, choices, ledger and final completion, both sides of replace.
        for device in ('qn90a','s90d'):
            for write_number in range(1,5):
                for after_replace in (False,True):
                    with self.subTest(device=device,write=write_number,after=after_replace),tempfile.TemporaryDirectory() as tmp:
                        root=Path(tmp);driver,e=self.case(root,device);calls=0
                        def disk_full(path,value):
                            nonlocal calls
                            calls+=1
                            if calls==write_number:
                                if after_replace:atomic_json(path,value)
                                raise OSError(errno.ENOSPC,'injected full disk')
                            atomic_json(path,value)
                        with patch('tvsetup.engine.atomic_json',side_effect=disk_full):
                            with self.assertRaises(OSError):e.finalize()
                        # A successful final replacement is already a durable terminal record.
                        resumed=Engine(None,e.folder,device,e.choices,state_dir=root);resumed.load()
                        if resumed.doc['phase']!='complete':
                            self.assertEqual(len(pending(root,device)),1)
                            resumed.reconcile();resumed.apply();resumed.finalize()
                        self.assertEqual(driver.executions,1)
                        self.assertEqual(read_json(root/(device+'-choices.json')),e.choices)
                        self.assertEqual(read_json(root/(device+'-ledger.json'))['files'],{'/test':'new'})
                        self.assertFalse(pending(root,device))

    def test_finalization_and_rollback_preserve_later_local_edits(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);driver,e=self.case(root,'s90d')
            e.finalize();path=root/'s90d-choices.json';later={'keep':['later-user-edit']};atomic_json(path,later)
            with self.assertRaisesRegex(Refused,'Saved choices changed'):e.rollback()
            self.assertEqual(read_json(path),later)

    def test_local_rollback_restores_absence_and_survives_lost_remove_ack(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);driver,e=self.case(root,'qn90a');e.finalize()
            from tvsetup.common import atomic_remove
            def removed(path):
                atomic_remove(path)
                raise OSError(errno.ENOSPC,'lost remove fsync')
            with patch('tvsetup.engine.atomic_remove',side_effect=removed):
                with self.assertRaises(OSError):e.rollback()
            self.assertEqual(e.doc['phase'],'rollback-partial')
            driver.rollback=lambda *a:(_ for _ in ()).throw(AssertionError('repeated completed inverse'))
            e.load();e.rollback()
            self.assertFalse((root/'qn90a-choices.json').exists());self.assertFalse((root/'qn90a-ledger.json').exists())
            self.assertEqual(e.doc['phase'],'rolled-back')

    def test_local_rollback_restores_previous_choices_and_merged_ledger(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            previous={'choices':{'keep':['previous']},'ledger':{'files':{'/other':'old'},'artifact_sources':{}}}
            for name,value in previous.items():atomic_json(root/('s90d-'+name+'.json'),value)
            driver,e=self.case(root,'s90d');e.finalize();e.rollback()
            for name,value in previous.items():self.assertEqual(read_json(root/('s90d-'+name+'.json')),value)

    def test_failure_to_record_intent_never_submits_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);driver=FakeDriver();e=Engine(driver,root/'run','qn90a',{})
            e.prepare(Plan('qn90a',actions=[Action('1','home','file',None,'new',{'path':'/test'})]),driver.snapshot())
            def fail_intent(path,value):
                if any(row['phase']=='applying' for row in value['actions']):raise OSError(errno.ENOSPC,'no space for intent')
                atomic_json(path,value)
            with patch('tvsetup.engine.atomic_json',side_effect=fail_intent):
                with self.assertRaises(OSError):e.apply()
            self.assertEqual(driver.executions,0);self.assertIsNone(driver.state['files']['/test'])

    def test_interrupted_inverse_is_reconciled_and_later_drift_is_preserved(self):
        for device in ('qn90a','s90d'):
            with tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp);driver,e=self.case(root,device);original=driver.rollback
                def lost_reply(*args):original(*args);raise Refused('lost reverse reply')
                driver.rollback=lost_reply
                with self.assertRaises(Refused):e.rollback()
                self.assertIsNone(driver.state['files']['/test'])
                driver.rollback=original;e.load();e.rollback()
                self.assertEqual(e.doc['phase'],'rolled-back')
                driver.state['files']['/test']='later-edit'
                e.rollback();self.assertEqual(driver.state['files']['/test'],'later-edit')
