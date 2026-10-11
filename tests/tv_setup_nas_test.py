import copy
import json
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from tvsetup.common import Refused,sha
from tvsetup.nas import NAS,FILES,BASE
from tvsetup.planner import Plan,Action
from tvsetup.cli import verification
from tv_setup_planner_test import accepted
from tvsetup.config import profile

class MemoryNAS(NAS):
    def __init__(self,folder):
        super().__init__(folder,dict(ssh_target='test-nas',dashboard_url='http://nas.example.invalid:20491'));self.commands=[];self.restarts=0
        self.state=dict(files={n:sha(b'old') for n in FILES},compose_sha256='compose',registry={},containers='')
    def snapshot(self):return copy.deepcopy(self.state)
    def remote(self,script):
        self.commands.append(script)
        if script.startswith('sha256sum '):return 'a'*64+'  file\n'
        if script.startswith('test "$(sha256sum '):return ''
        if '\nmv ' in script:
            for target in FILES:
                if BASE+'/'+target in script:self.state['files'][target]=sha(FILES[target].read_bytes())
        return ''
    def restart(self):self.restarts+=1

class NASTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.folder=Path(self.tmp.name)
        self.n=MemoryNAS(self.folder);self.action=Action('nas','dashboard','nas',copy.deepcopy(self.n.state['files']),{n:sha(p.read_bytes()) for n,p in FILES.items()},dict(compose_sha256='compose'))

    def test_private_netdata_origin_is_staged_without_editing_sources(self):
        self.n.settings['netdata_url']='http://192.0.2.9:20489'
        originals={target:source.read_bytes() for target,source in FILES.items()}
        info=self.n.prepare(self.action)
        staged=Path(info['source'])
        server=(staged/'s90d-dashboard/server.py').read_bytes()
        self.assertIn(b"'http://192.0.2.9:20489'",server)
        compile(server,'server.py','exec')
        self.assertIn(b'http://192.0.2.9:20489/',(staged/'s90d-dashboard/index.html').read_bytes())
        for target,source in FILES.items():
            self.assertEqual(source.read_bytes(),originals[target])
            self.assertEqual((staged/target).read_bytes(),self.n.source_bytes(target,source))

    def test_shared_update_preserves_compose_pairing_and_registry(self):
        info=self.n.prepare(self.action);info=self.n.backup(self.action,info)
        with patch('tvsetup.nas.run',return_value=''):self.n.execute(self.action,info)
        commands='\n'.join(self.n.commands)
        self.assertNotIn('app.update',commands);self.assertNotIn('app.create',commands)
        self.assertNotIn('> '+BASE+'/s90d-receiver/receiver.json',commands)
        self.assertNotIn('devices.json.new',commands)
        self.assertNotIn('latest.json',commands);self.assertNotIn('qn90a.json',commands)
        self.assertEqual(self.n.restarts,1);self.assertEqual(self.n.state['files'],self.action.after)

    def test_concurrent_compose_change_stops_before_replacement(self):
        info=self.n.prepare(self.action);info=self.n.backup(self.action,info)
        self.n.state['compose_sha256']='changed'
        with self.assertRaisesRegex(Refused,'compose changed'):self.n.execute(self.action,info)
        self.assertEqual(self.n.restarts,0)

    def test_shared_flag_required_for_nas_drift(self):
        p=Plan('qn90a',states={'dashboard':'already correct'})
        self.n.add_plan(p,False)
        self.assertTrue(any('--shared-nas' in issue for issue in p.issues))

    def test_boot_verification_rejects_stale_boot_and_manual_foreground(self):
        s=accepted('qn90a')
        s['boot_status']=json.dumps(dict(boot='old',accepted=True,outcome='foreground-confirmed',entered=10))
        s['telemetry_status']=json.dumps(dict(boot='old',sent=5,uptime=99,monitoring=True))
        r=verification(profile('qn90a'),s)
        self.assertIn('not established',r['startup']);self.assertIn('not observed',r['telemetry'])
        s['boot_status']=json.dumps(dict(boot=s['boot'],accepted=False,outcome='already-foreground',entered=10))
        self.assertIn('not established',verification(profile('qn90a'),s)['startup'])
        s['boot_status']=json.dumps(dict(boot=s['boot'],accepted=True,outcome='foreground-confirmed',entered=10))
        s['telemetry_status']=json.dumps(dict(boot=s['boot'],sent=5,uptime=99,monitoring=True))
        r=verification(profile('qn90a'),s)
        self.assertIn('independently',r['startup']);self.assertIn('fresh, sending',r['telemetry'])

if __name__=='__main__':unittest.main()

class RebootTests(unittest.TestCase):
    def test_reboot_submits_once_and_never_launches_hub(self):
        from tvsetup.cli import reboot_verify
        before=accepted('qn90a');after=copy.deepcopy(before);after['boot']='new-boot'
        after['boot_status']=json.dumps(dict(boot='new-boot',accepted=True,outcome='foreground-confirmed',entered=10))
        after['telemetry_status']=json.dumps(dict(boot='new-boot',sent=5,uptime=99,monitoring=True))
        calls=[]
        class Initial:
            def snapshot(self,**kwargs):return before
            def root(self,script):calls.append(script)
        class Observer:
            def __init__(self,*args):pass
            def snapshot(self,**kwargs):return after
        with tempfile.TemporaryDirectory() as folder, patch('tvsetup.cli.observe',return_value={'boot':after['boot'],'verification':verification(profile('qn90a'),after)}), patch('tvsetup.cli.time.sleep'):
            result=reboot_verify(profile('qn90a'),Initial(),Path(folder),30)
        self.assertIn('independently',result['startup']);self.assertEqual(len(calls),1)
        self.assertIn('Reboot',calls[0]);self.assertNotIn('app_launcher',calls[0]);self.assertNotIn('systemctl start',calls[0])

class DashboardVerificationTests(unittest.TestCase):
    def test_receiver_requires_matching_fresh_boot_and_both_devices(self):
        import io
        value=dict(device='qn90a',server_time=100,latest=dict(boot='current',received_at=95),devices=[dict(id='qn90a'),dict(id='s90d')],charts={str(i):dict(labels=['time','value']) for i in range(9)})
        with tempfile.TemporaryDirectory() as folder:
            nas=NAS(Path(folder),dict(ssh_target='test-nas',dashboard_url='http://nas.example.invalid:20491'))
            def observe(data):
                with patch('urllib.request.urlopen',return_value=io.BytesIO(json.dumps(data).encode())):
                    return nas.verify('qn90a','current')
            self.assertEqual(observe(value)['receiver'],'fresh current-boot ingestion')
            stale=copy.deepcopy(value);stale['latest']['received_at']=50
            self.assertIn('not verified',observe(stale)['receiver'])
            wrong=copy.deepcopy(value);wrong['latest']['boot']='old'
            self.assertIn('not verified',observe(wrong)['receiver'])
            missing=copy.deepcopy(value);missing['devices']=[dict(id='qn90a')]
            with self.assertRaises(Refused):observe(missing)

    def test_failed_collector_does_not_claim_current_sends(self):
        s=accepted('qn90a');s['telemetry_status']=json.dumps(dict(boot=s['boot'],uptime=100,sent=20,monitoring=True,last_error='receiver down'))
        self.assertIn('not observed',verification(profile('qn90a'),s)['telemetry'])

class NASRecoveryTests(unittest.TestCase):
    def test_partial_batch_rollback_preserves_other_device_state(self):
        with tempfile.TemporaryDirectory() as folder:
            nas=MemoryNAS(Path(folder));before=copy.deepcopy(nas.state['files'])
            after={n:sha(p.read_bytes()) for n,p in FILES.items()}
            action=Action('nas','dashboard','nas',before,after,dict(compose_sha256='compose'))
            info=nas.backup(action,nas.prepare(action))
            targets=list(FILES);nas.state['files'][targets[0]]=after[targets[0]]
            # Emulate the checked remote restore, leaving every other file untouched.
            original=nas.remote
            def remote(script):
                result=original(script)
                if '.restore' in script and '\nmv ' in script:
                    for target in targets:
                        if BASE+'/'+target in script:nas.state['files'][target]=before[target]
                return result
            nas.remote=remote;nas.rollback(action,info)
            self.assertEqual(nas.state['files'],before)
            self.assertEqual(nas.restarts,1)
            mutations='\n'.join(s for s in nas.commands if '\nmv ' in s or 'rm -f ' in s)
            self.assertNotIn('receiver.json',mutations);self.assertNotIn('devices.json',mutations)
            self.assertNotIn('latest.json',mutations);self.assertNotIn('qn90a.json',mutations)
    def test_registry_drift_and_corrupt_backup_block_restore(self):
        for problem in ('registry','backup'):
            with self.subTest(problem=problem),tempfile.TemporaryDirectory() as folder:
                nas=MemoryNAS(Path(folder));before=copy.deepcopy(nas.state['files'])
                after={n:sha(p.read_bytes()) for n,p in FILES.items()}
                action=Action('nas','dashboard','nas',before,after,dict(compose_sha256='compose'))
                info=nas.backup(action,nas.prepare(action));nas.state['files']=copy.deepcopy(after)
                original=nas.remote
                def remote(script):
                    if problem=='registry' and script.startswith('sha256sum ') and 'devices.json' in script:return 'b'*64+'  file\n'
                    if problem=='backup' and '.restore' in script:raise Refused('backup checksum mismatch')
                    return original(script)
                nas.remote=remote
                with self.assertRaises(Refused):nas.rollback(action,info)
                self.assertEqual(nas.restarts,0);self.assertEqual(nas.state['files'],after)
