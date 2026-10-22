"""Fault-injected transport boundaries. These tests never connect to hardware."""
import copy
import io
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from tvsetup.common import Refused, sha
from tvsetup.config import profile
from tvsetup.root import execute
from tvsetup.transport import Transport, identity_guard, managed_guard


def pinned_probe(p):
    return '\n'.join((
        'TVSETUP_PROBE:firmware:' + p['firmware'],
        'TVSETUP_PROBE:architecture:' + p['architecture'],
        'TVSETUP_PROBE:runtime:present',
        'TVSETUP_PROBE:dotnet_sha256:' + p['host_sha256'],
        'TVSETUP_PROBE:dotnet_launcher_sha256:' + p['launcher_sha256'],
        '[exit:0]', '',
    ))


class RootTransportTests(unittest.TestCase):
    def test_both_models_lost_operation_reply_cleans_up_without_resubmission(self):
        for device in ('qn90a','s90d'):
            with self.subTest(device=device),tempfile.TemporaryDirectory() as tmp:
                folder=Path(tmp);calls=[];uploads=[]
                p={**profile(device),'host':'192.0.2.11','device_id':'uuid:00000000-0000-4000-8000-000000000001'}
                class Client:
                    def __init__(self,*args):pass
                    def connect(self):pass
                    def require_device(self):pass
                    def capture(self,*args,**kwargs):
                        return SimpleNamespace(transport_returncode=0,output='a'*64+'  /etc/passwd\n'+'b'*64+'  /usr/share/sdbd/public.pem\n[exit:0]\n')
                    def push(self,source,target):uploads.append((source.name,str(target)))
                def capture(cfg,callback,script,timeout,label):
                    calls.append((label,script))
                    if label=='setup-root-operation':raise Refused('lost callback after submission')
                def build(p,work,script,index):
                    out=work/'RootIdentity.dll';out.write_bytes(b'fixture assembly');return {out:'RootIdentity.dll'}
                def command(argv,**kwargs):
                    if '-out' in argv:Path(argv[argv.index('-out')+1]).write_bytes(b'fixture')
                    return ''
                toolkit=SimpleNamespace(device=lambda cfg:'192.0.2.30',SdbClient=Client,capture=capture)
                with patch('tvsetup.root.PRIVATE',folder),patch('tvsetup.root.load',return_value=toolkit),patch('tvsetup.root.build',side_effect=build),patch('tvsetup.root.run',side_effect=command):
                    with self.assertRaisesRegex(Refused,'lost callback'):execute(p,'true\n')
                self.assertEqual([label for label,_ in calls],['setup-root-stage','setup-root-operation','setup-root-cleanup'])
                self.assertNotIn('test-private.pem',[name for name,_ in uploads])
                for label,script in calls:
                    if label != 'setup-root-cleanup':
                        self.assertIn(p['host_sha256'], script)
                        self.assertIn('/usr/share/dotnet/shared/Microsoft.NETCore.App/', script)
                    if device=='qn90a':self.assertNotIn('codex-namespace-proof',script)
                    else:self.assertNotIn('codex-qn90a-root-proof',script)
                self.assertIn('sha256sum /etc/passwd',calls[-1][1])
    def test_local_build_failure_cannot_stage_anything(self):
        with tempfile.TemporaryDirectory() as tmp:
            p={**profile('s90d'),'host':'192.0.2.12','device_id':'uuid:00000000-0000-4000-8000-000000000001'}
            toolkit=SimpleNamespace(device=lambda cfg:(_ for _ in ()).throw(AssertionError('contacted device')))
            with patch('tvsetup.root.PRIVATE',Path(tmp)),patch('tvsetup.root.load',return_value=toolkit),patch('tvsetup.root.build',side_effect=Refused('compiler missing')):
                with self.assertRaisesRegex(Refused,'compiler missing'):execute(p,'true\n')


class IdentityTests(unittest.TestCase):
    def _transport_with_probe(self, folder, profile, *, firmware=None, architecture=None):
        class Client:
            def __init__(self, executable, host): self.calls=[]
            def connect(self): pass
            def require_device(self): pass
            def capture(self, script, **kwargs):
                self.calls.append(script)
                if 'TVSETUP_PROBE:firmware:' in script:
                    values = [
                        'TVSETUP_PROBE:firmware:' + (firmware or profile['firmware']),
                        'TVSETUP_PROBE:architecture:' + (architecture or profile['architecture']),
                        'TVSETUP_PROBE:runtime:present',
                        'TVSETUP_PROBE:dotnet_sha256:' + 'c'*64,
                        'TVSETUP_PROBE:dotnet_launcher_sha256:' + profile['launcher_sha256'],
                        '[exit:0]',
                    ]
                    return SimpleNamespace(transport_returncode=0, output='\n'.join(values)+'\n')
                return SimpleNamespace(transport_returncode=0, output='\n[exit:0]\n')

        toolkit=SimpleNamespace(device=lambda cfg:'192.0.2.30',SdbClient=Client)
        with patch('tvsetup.transport.PRIVATE', folder), patch('tvsetup.toolkit.load', return_value=toolkit):
            return Transport(profile, folder/'evidence')

    def test_runtime_hash_mismatch_is_diagnostic_until_managed_guard_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);p={**profile('s90d'),'host':'192.0.2.11','device_id':'fixture-id'}
            transport=self._transport_with_probe(folder,p)
            self.assertEqual([item[0] for item in transport.identity_diagnostics],['dotnet_sha256'])
            evidence=folder/'evidence/identity-diagnostics.json'
            self.assertTrue(evidence.is_file());self.assertEqual(evidence.stat().st_mode&0o777,0o600)
            self.assertIn('dotnet_sha256',evidence.read_text())
            with patch.object(transport.client,'capture',return_value=SimpleNamespace(transport_returncode=0,output='\n[exit:1]\n')):
                with self.assertRaises(Refused) as caught:transport.sdk(managed_guard(p))
            refusal=caught.exception
            self.assertEqual(refusal.code,'CR-ID-HASH')
            self.assertIn('SDK command incomplete/failed; private evidence:',str(refusal))
            self.assertIn('/usr/bin/dotnet SHA-256',str(refusal))
            self.assertNotIn('No operation was submitted',' '.join(refusal.next_steps))

    def test_firmware_or_architecture_mismatch_still_refuses_at_connect(self):
        for kwargs, code in (({'firmware': 'T-OTHER-0001-1.0'}, 'CR-ID-FIRMWARE'),
                             ({'architecture': 'x86_64'}, 'CR-ID-ARCH')):
            with self.subTest(code=code), tempfile.TemporaryDirectory() as tmp:
                folder=Path(tmp);p={**profile('s90d'),'host':'192.0.2.11','device_id':'fixture-id'}
                with self.assertRaises(Refused) as caught:self._transport_with_probe(folder,p,**kwargs)
                self.assertEqual(caught.exception.code,code)

    def test_unrelated_completed_sdk_failure_keeps_original_refusal(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);p={**profile('s90d'),'host':'192.0.2.11','device_id':'fixture-id'}
            transport=self._transport_with_probe(folder,p)
            with patch.object(transport.client,'capture',return_value=SimpleNamespace(transport_returncode=0,output='\n[exit:1]\n')):
                with self.assertRaises(Refused) as caught:transport.sdk('printf unrelated-failure\\n')
            self.assertIsNone(caught.exception.code)
            self.assertTrue(str(caught.exception).startswith('SDK command incomplete/failed; private evidence:'))

    def test_completed_sdk_failure_after_guard_success_is_not_misclassified(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);p={**profile('s90d'),'host':'192.0.2.11','device_id':'fixture-id'}
            transport=self._transport_with_probe(folder,p)
            def fail_after_guard(script,**kwargs):
                import re
                marker=re.search(r'TVSETUP_MANAGED_GUARD_OK_[a-f0-9]+',script)
                self.assertIsNotNone(marker)
                return SimpleNamespace(transport_returncode=0,output='\n'+marker[0]+'\n\n[exit:1]\n')
            with patch.object(transport.client,'capture',side_effect=fail_after_guard):
                with self.assertRaises(Refused) as caught:transport.sdk(managed_guard(p)+'false\n')
            self.assertIsNone(caught.exception.code)

    def test_sdk_removes_guard_marker_without_losing_command_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);p={**profile('s90d'),'host':'192.0.2.11','device_id':'fixture-id'}
            transport=self._transport_with_probe(folder,p)
            def success_after_guard(script,**kwargs):
                import re
                marker=re.search(r'TVSETUP_MANAGED_GUARD_OK_[a-f0-9]+',script)
                self.assertIsNotNone(marker)
                return SimpleNamespace(transport_returncode=0,output=marker[0]+'\ncommand-payload\n[exit:0]\n')
            with patch.object(transport.client,'capture',side_effect=success_after_guard):
                output=transport.sdk(managed_guard(p)+'printf command-payload\n')
            self.assertEqual(output.strip(),'command-payload')

    def test_root_failure_maps_only_known_guard_boundary(self):
        with tempfile.TemporaryDirectory() as tmp:
            p={**profile('s90d'),'host':'192.0.2.11','device_id':'fixture-id'}
            for guard_failure,expected_code in ((True,'CR-ID-HASH'),(False,None)):
                evidence=Path(tmp)/str(guard_failure);evidence.mkdir()
                transport=object.__new__(Transport);transport.profile=p;transport.evidence=evidence
                transport.root_session=evidence/'session';transport.root_session.mkdir()
                transport.native_bundle=None
                transport.identity_diagnostics=[('dotnet_sha256',p['host_sha256'],'c'*64)]
                def failed_run(argv,**kwargs):
                    result=Path(argv[argv.index('--result')+1])
                    result.write_text(json.dumps({'failed':True,'output':'','guard_failure':guard_failure}))
                    error=Refused('Command failed: worker');error.output='worker failed';raise error
                with patch('tvsetup.transport.run',side_effect=failed_run):
                    with self.assertRaises(Refused) as caught:transport.root('true\n')
                self.assertEqual(caught.exception.code,expected_code)

    def test_identity_checks_do_not_require_managed_profile_fields(self):
        for device in ('qn90a', 's90d'):
            p = profile(device)
            script = identity_guard({key: p[key] for key in ('firmware', 'architecture')})
            self.assertIn(p['firmware'], script)
            self.assertIn(p['architecture'], script)
            self.assertNotIn('dotnet', script)
            managed = managed_guard(p)
            self.assertTrue(managed.startswith(script))
            self.assertIn(p['runtime'], managed)
            self.assertIn(p['host_sha256'], managed)
            if p.get('launcher_sha256'):
                self.assertIn(p['launcher_sha256'], managed)

    def test_managed_package_install_and_recovery_keep_runtime_guards(self):
        from tvsetup.operations import Driver
        with tempfile.TemporaryDirectory() as tmp:
            artifact = Path(tmp)/'fixture.tpk'
            artifact.write_bytes(b'fixture signed package')
            for device in ('qn90a', 's90d'):
                for package in ('MiniHubBoot', 'MiniTelemetry'):
                    driver = object.__new__(Driver)
                    driver.profile = profile(device)
                    driver.tv = Mock()
                    driver.tv.sdk.side_effect = Refused('runtime changed')
                    action = SimpleNamespace(kind='package', before=None, options={'package': package})
                    info = {'artifact': str(artifact), 'sha256': sha(artifact.read_bytes())}
                    with patch('tvsetup.operations.observed', return_value=None), \
                         patch('tvsetup.operations.verify_package'), patch('tvsetup.operations.run') as install:
                        with self.assertRaisesRegex(Refused, 'runtime changed'):
                            driver.execute(action, info, {})
                        with self.assertRaisesRegex(Refused, 'runtime changed'):
                            driver.reinstall_recovery(action, {})
                        install.assert_not_called()
                    for call in driver.tv.sdk.call_args_list:
                        self.assertIn(driver.profile['host_sha256'], call.args[0])

    def test_tracked_sdb_subclass_calls_raw_connector_without_recursing(self):
        import importlib.util
        import sys
        from tvsetup.common import REPO
        toolkit_dir = REPO / 'tools/toolkit'
        class UpstreamClient:
            def __init__(self, executable, host):
                self.serial = f'{host}:26101'
                self.state = 'offline'
                self.connect_calls = 0
            def run(self, args, check=False):
                return SimpleNamespace(stdout=f'{self.serial} {self.state}\n', returncode=0)
            def connect(self):
                self.connect_calls += 1
                self.state = 'device'
        upstream=SimpleNamespace(SdbClient=UpstreamClient,route_callback_host=lambda host:'127.0.0.1')
        package=SimpleNamespace(sdb=upstream)
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {'SAMSUNG_TV_TOOLKIT': tmp}), \
                 patch.dict(sys.modules, {'samsung_tv_root':package,'samsung_tv_root.sdb':upstream}), \
                 patch.object(sys, 'path', [str(toolkit_dir), *sys.path]):
                spec=importlib.util.spec_from_file_location('sdb_subclass_fixture',toolkit_dir/'samsung_tv.py')
                module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
            client=module.SdbClient(Path('/fake/sdb'),'192.0.2.15')
            client.connect()
            client.connect()
            self.assertEqual(client.connect_calls,1)
            self.assertEqual(client.state,'device')

    def test_wrong_physical_identity_stops_before_sdk_or_callback(self):
        import importlib.util
        import sys
        from tvsetup.common import REPO
        # Import the tracked wrapper with a synthetic upstream module.
        class UpstreamClient:
            def __init__(self,*args): pass
            def connect(self): pass
        upstream=SimpleNamespace(SdbClient=UpstreamClient,route_callback_host=lambda host:(_ for _ in ()).throw(AssertionError('routed before identity check')))
        package=SimpleNamespace(sdb=upstream)
        with patch.object(sys, 'path', [str(REPO/'tools/toolkit'), *sys.path]), \
             patch.dict(sys.modules,{'samsung_tv_root':package,'samsung_tv_root.sdb':upstream}):
            spec=importlib.util.spec_from_file_location('identity_fixture',REPO/'tools/toolkit/samsung_tv.py')
            module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        for name in ('qn90a','s90d'):
            p=profile(name)
            data=dict(device=dict(modelName=p['model'],model=p['platform'],id='fixture-private-device-id'))
            with patch.object(module,'urlopen',return_value=io.BytesIO(json.dumps(data).encode())):
                with self.assertRaisesRegex(RuntimeError,'Physical TV identity') as caught:
                    module.device(dict(tv_host='192.0.2.11',expected_model=p['model'],expected_platform=p['platform'],expected_device_id='expected-tv'))
                self.assertIn('id does not match site.json',str(caught.exception))
                self.assertNotIn('fixture-private-device-id',str(caught.exception))
                self.assertNotIn('expected-tv',str(caught.exception))

    def test_toolkit_identity_does_not_print_host_or_display_name(self):
        import importlib.util
        import sys
        from tvsetup.common import REPO
        class UpstreamClient:
            def __init__(self,*args): pass
            def connect(self): pass
        upstream=SimpleNamespace(SdbClient=UpstreamClient,route_callback_host=lambda host:'192.0.2.31')
        package=SimpleNamespace(sdb=upstream)
        with patch.object(sys, 'path', [str(REPO/'tools/toolkit'), *sys.path]), \
             patch.dict(sys.modules,{'samsung_tv_root':package,'samsung_tv_root.sdb':upstream}):
            spec=importlib.util.spec_from_file_location('identity_redaction_fixture',REPO/'tools/toolkit/samsung_tv.py')
            module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        p=profile('s90d')
        data=dict(device=dict(modelName=p['model'],model=p['platform'],id='fixture-private-device-id',name='private-tv-host-name',developerMode='1',developerIP='192.0.2.31'))
        with patch.object(module,'urlopen',return_value=io.BytesIO(json.dumps(data).encode())), \
             patch.object(module.socket,'create_connection'), patch('builtins.print') as output:
            callback=module.device(dict(tv_host='192.0.2.11',expected_model=p['model'],expected_platform=p['platform'],expected_device_id='fixture-private-device-id'))
        output.assert_not_called()
        self.assertEqual(callback,'192.0.2.31')

    def test_toolkit_developer_host_mismatch_shows_only_routed_computer_address(self):
        import importlib.util
        import sys
        from tvsetup.common import REPO
        class UpstreamClient:
            def __init__(self,*args): pass
            def connect(self): pass
        routed='192.0.2.31'
        upstream=SimpleNamespace(SdbClient=UpstreamClient,route_callback_host=lambda host:routed)
        package=SimpleNamespace(sdb=upstream)
        with patch.object(sys, 'path', [str(REPO/'tools/toolkit'), *sys.path]), \
             patch.dict(sys.modules,{'samsung_tv_root':package,'samsung_tv_root.sdb':upstream}):
            spec=importlib.util.spec_from_file_location('identity_host_mismatch_fixture',REPO/'tools/toolkit/samsung_tv.py')
            module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        p=profile('s90d')
        tv_address='198.51.100.77'
        private_id='fixture-private-device-id'
        data=dict(device=dict(modelName=p['model'],model=p['platform'],id=private_id,
                              developerMode='1',developerIP=tv_address))
        with patch.object(module,'urlopen',return_value=io.BytesIO(json.dumps(data).encode())), \
             self.assertRaisesRegex(RuntimeError,'Developer Mode host must match') as caught:
            module.device(dict(tv_host='192.0.2.11',expected_model=p['model'],expected_platform=p['platform']))
        message=str(caught.exception)
        self.assertIn(routed,message)
        self.assertNotIn(tv_address,message)
        self.assertNotIn('192.0.2.11',message)
        self.assertNotIn(private_id,message)

class AgentGuardTests(unittest.TestCase):
    def test_agent_transport_records_probe_and_keeps_existing_managed_connect_guard(self):
        import importlib.machinery
        from tvsetup.agent_transport import AgentTransport
        p={**profile('s90d'),'host':'192.0.2.11','device_id':'fixture-id'}
        probe='\n'.join((
            'TVSETUP_PROBE:firmware:'+p['firmware'],
            'TVSETUP_PROBE:architecture:'+p['architecture'],
            'TVSETUP_PROBE:runtime:present',
            'TVSETUP_PROBE:dotnet_sha256:'+'c'*64,
            'TVSETUP_PROBE:dotnet_launcher_sha256:'+p['launcher_sha256'],
        ))
        class Loader:
            def create_module(self,spec):return None
            def exec_module(self,module):
                module.request=lambda *args,**kwargs:{'device':p['id'],'connected':True,'worker_ready':True,'identity':{'uid':0}}
        spec=importlib.machinery.ModuleSpec('enrolled_agent_client',Loader())
        with tempfile.TemporaryDirectory() as tmp:
            credential=Path(tmp)/'agent.json'
            credential.write_text(json.dumps({'device':p['id'],'host':p['host']}))
            evidence=Path(tmp)/'evidence'
            with patch('tvsetup.agent_transport.importlib.util.spec_from_file_location',return_value=spec), \
                 patch.object(AgentTransport,'execute_result',side_effect=[{'exit_code':0,'stdout':probe},{'exit_code':1,'stdout':''}]):
                with self.assertRaises(Refused) as caught:AgentTransport(p,evidence,credential)
            self.assertEqual(caught.exception.code,'CR-ID-HASH')
            self.assertIn('identity-diagnostics.json',[f.name for f in evidence.iterdir()])

    def test_large_agent_guarded_command_does_not_misclassify_post_guard_failure(self):
        from tvsetup.agent_transport import AgentTransport
        p=profile('s90d')
        with tempfile.TemporaryDirectory() as tmp:
            agent=object.__new__(AgentTransport);agent.profile=p;agent.evidence=Path(tmp)
            agent.identity_diagnostics=[('dotnet_sha256',p['host_sha256'],'c'*64)]
            uploaded={}
            def upload(data,target):
                import re
                uploaded['marker']=re.search(rb'TVSETUP_MANAGED_GUARD_OK_[a-f0-9]+',data)[0].decode()
            def result(script,timeout=20):
                if 'marker' not in uploaded:return {'exit_code':0,'stdout':''}
                return {'exit_code':1,'stdout':'\n'+uploaded['marker']+'\n'}
            agent.execute_result=result;agent._upload=upload
            with self.assertRaises(Refused) as caught:agent.sdk(managed_guard(p)+'true\n'*4000)
            self.assertIsNone(caught.exception.code)

if __name__=='__main__':unittest.main()
