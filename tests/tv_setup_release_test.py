"""Isolated public-installation, CLI and interrupted-run checks; no device proof."""
import contextlib
import copy
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from tvsetup import cli
from tvsetup.common import Refused, atomic_json, lock, read_json, sha
from tvsetup.config import profile, resolve
from tvsetup.engine import Engine
from tvsetup.planner import Action, Plan, plan
from tvsetup.site import load_site, configured_profile, binding
from tvsetup.root import operation_source
from tv_setup_engine_test import FakeDriver
from tv_setup_planner_test import accepted


class SiteTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.folder=Path(self.tmp.name);self.path=self.folder/'site.json'
        self.data={'devices':{'qn90a':{'host':'192.0.2.11','device_id':'uuid:00000000-0000-4000-8000-000000000001'},'s90d':{'host':'192.0.2.12','device_id':'uuid:00000000-0000-4000-8000-000000000002'}}}
    def load(self):
        self.path.write_text(json.dumps(self.data));return load_site(self.path)
    def test_profiles_contain_no_installation_identity(self):
        for name in ('qn90a','s90d'):
            self.assertFalse({'host','signing_profile','author_cert_sha256','distributor_cert_sha256'} & set(profile(name)))
            p=configured_profile(name,self.load())
            self.assertEqual(p['host'],self.data['devices'][name]['host'])
            self.assertEqual(p['firmware'],profile(name)['firmware'])
    def test_site_cannot_override_model_firmware_or_resource_guards(self):
        for key in ('model','firmware','host_sha256','cleanup','author_cert_sha256'):
            self.data['devices']['qn90a'][key]='override'
            with self.assertRaises(Refused):self.load()
            del self.data['devices']['qn90a'][key]
    def test_bad_hosts_duplicate_hosts_and_ssh_option_injection_rejected(self):
        for host in ('-oProxyCommand=bad','127.0.0.1','0.0.0.0','192.0.2.12',None):
            self.data['devices']['qn90a']['host']=host
            with self.assertRaises(Refused):self.load()
        self.data['devices']['qn90a']['host']='192.0.2.11'
        self.data['nas']=dict(ssh_target='-oProxyCommand=bad',base='/srv/tv',receiver_url='https://nas.example.invalid',dashboard_url='http://nas.example.invalid')
        with self.assertRaises(Refused):self.load()
    def test_optional_netdata_origin_is_validated_and_normalized(self):
        self.data['nas']=dict(ssh_target='test-nas',base='/srv/tv',receiver_url='https://nas.example.invalid',dashboard_url='http://nas.example.invalid')
        self.assertNotIn('netdata_url',self.load()['nas'])
        self.data['nas']['netdata_url']='http://192.0.2.9:20489/'
        self.assertEqual(self.load()['nas']['netdata_url'],'http://192.0.2.9:20489')
        for value in ('file:///tmp/data','http://user:secret@example.invalid','http://example.invalid/path','http://example.invalid?x=1',None):
            self.data['nas']['netdata_url']=value
            with self.assertRaises(Refused):self.load()

    def test_missing_site_never_falls_back_to_personal_network(self):
        with self.assertRaisesRegex(Refused,'Create a private site'):load_site(self.folder/'missing')
    def test_trust_file_requires_both_pins_and_refuses_placeholders(self):
        self.data['trust_file']='trust.json';path=self.folder/'trust.json'
        entry=dict(signing_profile='MyTV',author_cert_sha256='a'*64,distributor_cert_sha256='b'*64)
        path.write_text(json.dumps({'qn90a':entry}))
        self.assertEqual(configured_profile('qn90a',self.load())['author_cert_sha256'],'a'*64)
        entry['author_cert_sha256']='0'*64;path.write_text(json.dumps({'qn90a':entry}))
        with self.assertRaises(Refused):self.load()
    def test_recovery_binding_tracks_target_nas_and_signing_trust(self):
        site=self.load();original=binding(site,'qn90a')
        site['devices']['s90d']['host']='192.0.2.30'
        self.assertEqual(original,binding(site,'qn90a'))
        site['devices']['qn90a']['host']='192.0.2.31'
        self.assertNotEqual(original,binding(site,'qn90a'))
    def test_first_telemetry_setup_has_no_implicit_recipient_or_opt_in(self):
        for device in ('qn90a','s90d'):
            s=accepted(device);s['preferences']=None
            result=plan(profile(device),resolve(device,overrides={'components':['telemetry']}),s)
            self.assertTrue(any('explicit --endpoint' in issue for issue in result.issues))
            preference=next(a for a in result.actions if a.kind=='preferences')
            self.assertFalse(preference.after['enabled'])


class CLITests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.site=self.root/'site.json'
        self.site.write_text(json.dumps({'devices':{name:{'host':ip,'device_id':'uuid:00000000-0000-4000-8000-'+ip.split('.')[-1].zfill(12)} for name,ip in [('qn90a','192.0.2.11'),('s90d','192.0.2.12')]}}))
        self.addCleanup(patch.stopall);patch('tvsetup.cli.STATE',self.root/'state').start()
        self.calls=[];calls=self.calls
        class FixtureTransport:
            def __init__(self,p,evidence):self.profile=p;calls.append(('connect',p['host']))
            def snapshot(self,privileged=False):calls.append(('snapshot',privileged));return accepted(self.profile['id'])
            def close(self):calls.append(('close',self.profile['id']))
        patch('tvsetup.cli.Transport',FixtureTransport).start()
    def invoke(self,*args):
        out=io.StringIO();err=io.StringIO()
        with contextlib.redirect_stdout(out),contextlib.redirect_stderr(err):
            code=cli.main([*args,'--site',str(self.site)])
        return code,out.getvalue(),err.getvalue()
    def test_plan_and_status_json_both_profiles_need_no_private_toolkit(self):
        for device in ('qn90a','s90d'):
            for command in ('plan','status'):
                code,out,err=self.invoke(command,'--device',device,'--components','hub','--json')
                self.assertEqual(code,0,err);self.assertEqual(json.loads(out)['actions'],[])
        self.assertFalse(any(c==('snapshot',True) for c in self.calls))
        self.assertEqual(sum(c[0]=='close' for c in self.calls),4)
    def test_recommended_cli_uses_journal_completion_before_saved_broad_choices(self):
        saved = resolve('qn90a')
        atomic_json(self.root/'state/qn90a-choices.json', saved)
        with patch('tvsetup.cli.resolve', wraps=resolve) as resolved:
            code,out,err=self.invoke('plan','--device','qn90a','--json')
        self.assertIn(code,(0,2),err)
        self.assertTrue(resolved.call_args.kwargs['first_run'])
        self.assertNotIn('cleanup',json.loads(out)['states'])
        self.assertNotIn('telemetry',json.loads(out)['states'])
        atomic_json(self.root/'state/runs/completed/journal.json', {
            'schema':2,'device':'qn90a','target_binding':binding(load_site(self.site),'qn90a'),
            'phase':'complete','actions':[],
        })
        with patch('tvsetup.cli.resolve', wraps=resolve) as resolved:
            code,out,err=self.invoke('plan','--device','qn90a','--json')
        self.assertFalse(resolved.call_args.kwargs['first_run'])
        self.assertIn('cleanup',json.loads(out)['states'])
        self.assertIn('telemetry',json.loads(out)['states'])

    def test_noninteractive_mutation_requires_yes_before_transport(self):
        code,out,err=self.invoke('apply','--device','qn90a','--json')
        self.assertEqual(code,1);self.assertEqual(self.calls,[]);self.assertIn('--yes',err)
    def test_unexpected_errors_are_private(self):
        sentinel='sensitive-transport-payload'
        with patch('tvsetup.cli.Transport',side_effect=RuntimeError(sentinel)):
            code,out,err=self.invoke('plan','--device','qn90a','--components','hub')
        self.assertEqual(code,1);self.assertNotIn(sentinel,out+err)
        self.assertTrue(list((self.root/'state').rglob('error.json')))
    def test_noop_apply_is_repeatable_both_models_and_does_not_mutate(self):
        for device in ('qn90a','s90d'):
            for _ in range(2):
                code,out,err=self.invoke('apply','--device',device,'--components','hub','--non-interactive','--yes','--json')
                self.assertEqual(code,0,err);self.assertEqual(json.loads(out)['actions'],[])
    def test_other_target_cannot_resume_or_rollback_journal(self):
        folder=self.root/'state/runs/test'
        atomic_json(folder/'journal.json',dict(device='qn90a',target_binding='another-target'))
        for command,args in [('apply',['--resume','test']),('rollback',['--run','test'])]:
            code,out,err=self.invoke(command,'--device','qn90a',*args,'--yes')
            self.assertEqual(code,1);self.assertIn('destination/trust',err);self.assertEqual(self.calls,[])
    def test_accept_noninteractive_never_reads_stdin(self):
        args=cli.parser().parse_args(['apply','--device','s90d','--non-interactive'])
        with patch('builtins.input',side_effect=AssertionError('unexpected prompt')):
            with self.assertRaises(Refused):cli.accept(args)


    def pending_local_run(self):
        state_dir=self.root/'state';folder=state_dir/'runs'/'local-finalization'
        device='qn90a';choices=resolve(device,overrides={'components':['hub']})
        e=Engine(FakeDriver(),folder,device,choices,state_dir=state_dir,target_binding=binding(load_site(self.site),device))
        e.start(Plan(device,actions=[]),{})
        return e

    def test_resume_local_finalization_works_with_transport_unavailable(self):
        e=self.pending_local_run()
        with patch('tvsetup.cli.Transport',side_effect=AssertionError('contacted TV')):
            code,out,err=self.invoke('apply','--device','qn90a','--resume',e.folder.name,'--yes','--json')
        self.assertEqual(code,0,err);self.assertEqual(json.loads(out)['phase'],'complete')

    def test_new_apply_is_blocked_before_privileged_inspection_when_finalization_is_pending(self):
        e=self.pending_local_run()
        with patch('tvsetup.cli.Transport',side_effect=AssertionError('contacted TV')):
            code,out,err=self.invoke('apply','--device','qn90a','--components','hub','--yes')
        self.assertEqual(code,1);self.assertIn('Unfinished run',err)

    def test_rollback_local_only_run_works_without_transport(self):
        e=self.pending_local_run();e.finalize()
        with patch('tvsetup.cli.Transport',side_effect=AssertionError('contacted TV')):
            code,out,err=self.invoke('rollback','--device','qn90a','--run',e.folder.name,'--yes','--json')
        self.assertEqual(code,0,err);self.assertEqual(json.loads(out)['phase'],'rolled-back')
        self.assertFalse((self.root/'state/qn90a-choices.json').exists())


class RecoveryTests(unittest.TestCase):
    def test_source_change_refuses_reconciliation_before_any_device_call(self):
        with tempfile.TemporaryDirectory() as folder:
            d=FakeDriver();e=Engine(d,Path(folder),'qn90a',{})
            e.prepare(Plan('qn90a',actions=[Action('1','home','file',None,'after',{'path':'/test'})]),d.snapshot())
            with patch('tvsetup.engine.source_revision',return_value='changed'),patch.object(d,'snapshot',side_effect=AssertionError('contacted TV')):
                with self.assertRaisesRegex(Refused,'Source changed'):e.reconcile()
    def test_both_models_lost_reply_reconcile_and_rollback_preserve_external_change(self):
        for device in ('qn90a','s90d'):
            with self.subTest(device=device),tempfile.TemporaryDirectory() as folder:
                d=FakeDriver();d.fail='after';e=Engine(d,Path(folder),device,{})
                p=Plan(device,actions=[Action('1','telemetry','file',None,'new',{'path':'/test'})])
                with self.assertRaises(Refused):e.start(p,d.snapshot())
                e.reconcile();e.apply();self.assertEqual(d.executions,1)
                d.state['files']['/test']='later-user-edit'
                with self.assertRaises(Refused):e.rollback()
                self.assertEqual(d.state['files']['/test'],'later-user-edit')
                with self.assertRaisesRegex(Refused,'cannot resume'):e.reconcile()
    def test_backup_failure_never_submits_mutation(self):
        for device in ('qn90a','s90d'):
            with tempfile.TemporaryDirectory() as folder:
                d=FakeDriver();e=Engine(d,Path(folder),device,{})
                with patch.object(d,'backup',side_effect=Refused('checksum failure')):
                    with self.assertRaises(Refused):e.start(Plan(device,actions=[Action('1','home','file',None,'new',{'path':'/test'})]),d.snapshot())
                self.assertEqual(d.executions,0)
    def test_manual_managed_app_recovery_does_not_stop_configuration_restore(self):
        with tempfile.TemporaryDirectory() as folder:
            d=FakeDriver();d.state['files']['/test']='new'
            d.state['packages']=[['MiniHub001']]
            d.state['files']['/app']='installed'
            e=Engine(d,Path(folder),'qn90a',{})
            e.prepare(Plan('qn90a',actions=[Action('1','home','file',None,'new',{'path':'/test'}),Action('2','hub','package',{'/app':'old'},{'/app':'installed'},{'package':'MiniHub001'})]),d.snapshot())
            for row in e.doc['actions']:row['phase']='applied'
            e.doc['phase']='complete'
            self.assertEqual(e.rollback(),['MiniHub001']);self.assertIsNone(d.state['files']['/test'])
            self.assertEqual(e.doc['phase'],'rolled-back-manual-recovery')
    def test_lock_excludes_another_process(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'lock'
            with lock(path):
                code='from pathlib import Path;from tvsetup.common import lock;\nwith lock(Path(__import__("sys").argv[1])):pass'
                result=subprocess.run([sys.executable,'-c',code,str(path)],text=True,capture_output=True)
                self.assertNotEqual(result.returncode,0);self.assertIn('Another setup operation',result.stderr)
    def test_root_payload_never_runs_as_baseline_owner_and_has_a_deadline(self):
        source=operation_source('sensitive command')
        self.assertIn('if(getuid()!=0)return 0',source)
        self.assertIn('WaitForExit(25000)',source);self.assertIn('c.Kill(true)',source)
        self.assertNotIn('sensitive command',source)


if __name__=='__main__':unittest.main()

class OutputPrivacyTests(unittest.TestCase):
    def test_preference_extension_is_preserved_internally_but_never_in_summary(self):
        value={'schema':1,'enabled':False,'endpoint':'https://nas.example.invalid/v1/devices/qn90a','extension_secret':'private-value'}
        result=Plan('qn90a',actions=[Action('prefs','telemetry','preferences',value,{**value,'enabled':True})])
        self.assertNotIn('private-value',json.dumps(result.json()))
        self.assertEqual(result.actions[0].after['extension_secret'],'private-value')

class NewAppRecoveryTests(unittest.TestCase):
    def test_new_app_and_later_preferences_are_retained_during_configuration_rollback(self):
        for device in ('qn90a','s90d'):
            with tempfile.TemporaryDirectory() as folder:
                d=FakeDriver();d.state.update(packages=[['MiniHub001']],preferences={'favorites':['later-user-choice']})
                d.state['files'].update({'/test':'new','/app':'installed'})
                e=Engine(d,Path(folder),device,{})
                e.prepare(Plan(device,actions=[Action('1','home','file',None,'new',{'path':'/test'}),Action('2','hub','package',None,{'/app':'installed'},{'package':'MiniHub001'})]),d.snapshot())
                for row in e.doc['actions']:row['phase']='applied'
                e.doc['phase']='complete'
                self.assertEqual(e.rollback(),['MiniHub001'])
                self.assertIsNone(d.state['files']['/test'])
                self.assertEqual(d.state['files']['/app'],'installed')
                self.assertEqual(d.state['preferences']['favorites'],['later-user-choice'])

class DistributionTests(unittest.TestCase):
    def test_tracked_site_template_is_loadable_without_private_files(self):
        from tvsetup.common import REPO
        site=load_site(REPO/'docs/examples/site.json')
        self.assertEqual(set(site['devices']),{'qn90a','s90d'})
        self.assertNotIn('_trust',site)
