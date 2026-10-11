"""Fault-injected transport boundaries. These tests never connect to hardware."""
import copy
import io
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from tvsetup.common import Refused
from tvsetup.config import profile
from tvsetup.root import execute


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
                for _,script in calls:
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
    def test_tracked_sdb_subclass_calls_raw_connector_without_recursing(self):
        import importlib.util
        import sys
        from tvsetup.common import REPO
        toolkit_dir = REPO / 'research/toolkit'
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
        with patch.object(sys, 'path', [str(REPO/'research/toolkit'), *sys.path]), \
             patch.dict(sys.modules,{'samsung_tv_root':package,'samsung_tv_root.sdb':upstream}):
            spec=importlib.util.spec_from_file_location('identity_fixture',REPO/'research/toolkit/samsung_tv.py')
            module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        for name in ('qn90a','s90d'):
            p=profile(name)
            data=dict(device=dict(modelName=p['model'],model=p['platform'],id='other-physical-tv'))
            with patch.object(module,'urlopen',return_value=io.BytesIO(json.dumps(data).encode())):
                with self.assertRaisesRegex(RuntimeError,'Physical TV identity'):
                    module.device(dict(tv_host='192.0.2.11',expected_model=p['model'],expected_platform=p['platform'],expected_device_id='expected-tv'))

if __name__=='__main__':unittest.main()
