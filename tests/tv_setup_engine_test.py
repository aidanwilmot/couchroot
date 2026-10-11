import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from tvsetup.common import Refused,read_json,sha
from tvsetup.engine import Engine,pending
from tvsetup.planner import Plan,Action
from tvsetup.operations import observed

class FakeDriver:
    def __init__(self):self.state={'files':{'/test':None}};self.executions=0;self.backups=0;self.fail=None;self.before_rollback=None
    def snapshot(self):return copy.deepcopy(self.state)
    def prepare(self,a):return {'artifact':'private'}
    def backup(self,a,info,s):self.backups+=1;return info
    def execute(self,a,info,s):
        self.executions+=1
        if self.fail=='before':raise Refused('transport failed before submit')
        self.state['files']['/test']=a.after
        if self.fail=='after':raise Refused('transport lost after mutation')
    def verify(self,a,b,s):
        if observed(a,s)!=a.after:raise Refused('readback')
    def rollback(self,a,info,s):
        if observed(a,s) not in (a.before,a.after):raise Refused('drift')
        self.state['files']['/test']=a.before
    def control_call(self,*args,**kw):pass

class EngineTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.folder=self.root/'runs/run-1';self.d=FakeDriver();self.e=Engine(self.d,self.folder,'qn90a',{},state_dir=self.root)
        self.plan=Plan('qn90a',actions=[Action('1','telemetry','file',None,sha(b'payload'),dict(path='/test',artifact='empty'))])

    def test_complete_durable_and_private(self):
        self.e.start(self.plan,self.d.snapshot());self.e.finalize();doc=read_json(self.e.path)
        self.assertEqual(doc['phase'],'complete');self.assertEqual(self.d.backups,1);self.assertEqual(self.d.executions,1)
        self.assertEqual(self.e.path.stat().st_mode&0o777,0o600);self.assertFalse(pending(self.root,'qn90a'))
        self.e.rollback();self.assertIsNone(self.d.state['files']['/test'])

    def test_lost_completion_reconciles_without_resubmission(self):
        self.d.fail='after'
        with self.assertRaises(Refused):self.e.start(self.plan,self.d.snapshot())
        self.assertEqual(read_json(self.e.path)['actions'][0]['phase'],'uncertain')
        self.assertEqual(len(pending(self.root,'qn90a')),1)
        self.e.load();self.e.reconcile();self.e.apply();self.e.finalize()
        self.assertEqual(self.d.executions,1);self.assertEqual(self.e.doc['phase'],'complete')

    def test_unchanged_uncertain_needs_explicit_retry(self):
        self.d.fail='before'
        with self.assertRaises(Refused):self.e.start(self.plan,self.d.snapshot())
        with self.assertRaisesRegex(Refused,'retry-unchanged'):self.e.reconcile()
        self.assertEqual(self.d.executions,1)
        self.e.reconcile(True);self.d.fail=None;self.e.apply();self.assertEqual(self.d.executions,2)

    def test_external_drift_blocks_retry_and_rollback(self):
        self.d.fail='after'
        with self.assertRaises(Refused):self.e.start(self.plan,self.d.snapshot())
        self.d.state['files']['/test']=sha(b'unrelated')
        with self.assertRaises(Refused):self.e.reconcile(True)
        with self.assertRaises(Refused):self.e.rollback()
        self.assertEqual(self.d.state['files']['/test'],sha(b'unrelated'))

    def test_source_change_refuses_partial_resume(self):
        self.d.fail='after'
        with self.assertRaises(Refused):self.e.start(self.plan,self.d.snapshot())
        self.e.reconcile()
        with patch('tvsetup.engine.source_revision',return_value='changed'):
            with self.assertRaisesRegex(Refused,'Source changed'):self.e.apply()

    def test_preparation_failure_never_touches_target(self):
        with patch.object(self.d,'prepare',side_effect=Refused('certificate mismatch')):
            with self.assertRaises(Refused):self.e.start(self.plan,self.d.snapshot())
        self.assertEqual(self.d.executions,0);self.assertEqual(self.d.backups,0)
        self.assertFalse(pending(self.root,'qn90a'))

    def test_before_mutation_intent_is_persisted(self):
        original=self.d.execute
        def inspect(a,info,state):
            self.assertEqual(read_json(self.e.path)['actions'][0]['phase'],'applying');original(a,info,state)
        self.d.execute=inspect;self.e.start(self.plan,self.d.snapshot())

if __name__=='__main__':unittest.main()
