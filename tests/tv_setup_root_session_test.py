"""Per-run root reuse and private results, with all device/toolkit I/O faked."""
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from tvsetup.common import Refused, atomic_json, sha
from tvsetup.config import profile
from tvsetup.root import execute
from tvsetup.root_session import prepared
from tvsetup.secrets import pairing_record
from tvsetup.transport import Transport
from tvsetup.worker import main


def build_fixture(profile, folder, script, cleanup_index=None):
    assert script is None
    result = {}
    for name in ('NamespaceRootProbe.dll', 'RootIdentity.dll'):
        path = folder/name
        path.write_bytes(b'fixture assembly')
        result[path] = name
    return result


def openssl_fixture(argv, **kwargs):
    if '-out' in argv:
        Path(argv[argv.index('-out')+1]).write_bytes(b'fixture key or signature')
    return ''


class RootSessionTests(unittest.TestCase):
    def test_preparation_reused_and_tampered_artifact_refused(self):
        with tempfile.TemporaryDirectory() as tmp, \
             patch('tvsetup.root.build', side_effect=build_fixture) as build, \
             patch('tvsetup.root.run', side_effect=openssl_fixture) as command:
            folder = Path(tmp)/'session'; p = profile('qn90a')
            first = prepared(p, folder, 'probe')
            self.assertEqual(first, prepared(p, folder, 'probe'))
            build.assert_called_once()
            self.assertEqual(sum(call.args[0][1] == 'genpkey' for call in command.call_args_list), 1)
            self.assertEqual(list(folder.rglob('test-private.pem')), [])
            (folder/'build/RootIdentity.dll').write_bytes(b'changed')
            with self.assertRaisesRegex(Refused, 'artifact changed'):
                prepared(p, folder, 'probe')
            build.assert_called_once()

    def test_profile_change_and_partial_preparation_are_not_retried(self):
        with tempfile.TemporaryDirectory() as tmp, \
             patch('tvsetup.root.build', side_effect=build_fixture) as build, \
             patch('tvsetup.root.run', side_effect=openssl_fixture):
            folder = Path(tmp)/'session'; p = profile('s90d')
            prepared(p, folder, 'probe')
            with self.assertRaisesRegex(Refused, 'identity/source changed'):
                prepared({**p, 'runtime':'changed'}, folder, 'probe')
            (folder/'manifest.json').unlink()
            with self.assertRaises(FileExistsError):
                prepared(p, folder, 'probe')
            build.assert_called_once()

    def test_two_operations_build_once_full_file_result_and_cleanup_on_lost_reply(self):
        for device in ('qn90a', 's90d'):
            with self.subTest(device=device), tempfile.TemporaryDirectory() as tmp:
                folder=Path(tmp); calls=[]; scripts=[]; uploads=[]
                payload='read result\n'*2000
                p={**profile(device), 'host':'192.0.2.11', 'device_id':'fixture-device'}
                class Client:
                    def __init__(self,*args):pass
                    def connect(self):pass
                    def require_device(self):pass
                    def capture(self,*args,**kwargs):
                        return SimpleNamespace(transport_returncode=0,output='a'*64+'  /etc/passwd\n'+'b'*64+'  /usr/share/sdbd/public.pem\n[exit:0]\n')
                    def push(self,source,target):
                        uploads.append(source.name)
                        if source.name=='operation.sh':scripts.append(source.read_text())
                        if source.name in ('result.txt','read.tmp'):
                            self_outer.assertEqual(source.stat().st_mode & 0o777, 0o600)
                    def run(self,args,check=False):
                        self_outer.assertTrue(check)
                        self_outer.assertEqual(args[0], 'pull')
                        Path(args[2]).write_text(payload)
                self_outer=self
                lost=False
                def capture(cfg,callback,script,timeout,label):
                    calls.append((label,script))
                    if label=='setup-root-operation' and lost:raise Refused('lost reply')
                    print('toolkit preview is deliberately incomplete')
                toolkit=SimpleNamespace(device=lambda cfg:'192.0.2.30',SdbClient=Client,capture=capture)
                with patch('tvsetup.root.PRIVATE',folder), patch('tvsetup.root.load',return_value=toolkit), \
                     patch('tvsetup.root.build',side_effect=build_fixture) as build, \
                     patch('tvsetup.root.run',side_effect=openssl_fixture), contextlib.redirect_stdout(io.StringIO()):
                    for operation in ('printf first', 'printf second'):
                        self.assertEqual(execute(p, operation, session=folder/'session', capture_result=True), payload)
                    lost=True
                    with self.assertRaisesRegex(Refused,'lost reply'):
                        execute(p, 'printf third', session=folder/'session', capture_result=True)
                build.assert_called_once()
                self.assertEqual(len(scripts),3)
                for n,word in enumerate(('first','second','third')):
                    self.assertIn('printf '+word, scripts[n])
                    self.assertIn('result.txt', scripts[n])
                    self.assertIn(p['host_sha256'], scripts[n])
                self.assertNotIn('test-private.pem',uploads)
                self.assertEqual([label for label,_ in calls], ['setup-root-stage','setup-root-operation','setup-root-cleanup']*3)
                for label,script in calls:
                    if label=='setup-root-operation':
                        self.assertIn('trap ',script)
                        self.assertIn('chmod 600 ',script)
                        completed=script.split('completed() {',1)[1].split('}\ntrap',1)[0]
                        self.assertIn('RootIdentity.dll',completed)
                        self.assertNotIn('result.txt',completed)
                    if label=='setup-root-cleanup':
                        self.assertIn('result.txt',script)
                        self.assertIn('read.tmp',script)
                        self.assertIn('sha256sum /etc/passwd',script)


class PrivateResultsTests(unittest.TestCase):
    def test_structured_shell_reads_preserve_large_output_and_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            tv=object.__new__(Transport)
            def local_root(script, **kwargs):
                self.assertTrue(kwargs['json_reads'])
                output=subprocess.check_output(['sh','-c','set -eu\n'+script],
                    env={**os.environ,'TV_SETUP_READ_TMP':str(Path(tmp)/'read.tmp')})
                return {name:bytes.fromhex(value).decode() for name,value in json.loads(output).items()}
            tv.root=local_root
            result=tv.root_reads({'long':"printf '%010000d' 0",'quoted':"printf 'a\\nb\"c\\tend\\n'"})
            self.assertEqual(len(result['long']),10000)
            self.assertEqual(result['quoted'],'a\nb"c\tend\n')
            with self.assertRaises(subprocess.CalledProcessError):tv.root_reads({'failed':'exit 7'})

    def test_worker_redacts_before_result_snapshot_journal_or_console(self):
        token='fixture-'*5
        pairing={'device_id':'qn90a','token':token,'endpoint':'https://receiver.example.invalid/v1/devices/qn90a'}
        raw={'pairing_config':json.dumps(pairing).encode().hex(),
             'legacy_pairing_config':json.dumps(pairing).encode().hex(),'status':('x'*10000).encode().hex()}
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp); config=folder/'profile.json'; script=folder/'operation.sh'; result=folder/'result.json'
            config.write_text('{}');script.write_text('true');console=io.StringIO()
            with patch('tvsetup.worker.execute',return_value=json.dumps(raw)),contextlib.redirect_stdout(console):
                main([str(config),str(script),'--result',str(result),'--json-reads'])
            data=json.loads(result.read_text())
            self.assertEqual(data['pairing_config'],pairing_record(pairing))
            self.assertEqual(data['legacy_pairing_config']['token_sha256'],sha(token.encode()))
            self.assertEqual(len(data['status']),10000)
            atomic_json(folder/'snapshot.json',data)
            atomic_json(folder/'journal.json',{'before':data,'after':data})
            recorded=console.getvalue()+''.join(p.read_text() for p in folder.iterdir())
            self.assertNotIn(token,recorded);self.assertNotIn(token.encode().hex(),recorded)
            self.assertEqual(result.stat().st_mode & 0o777,0o600)
            with patch('tvsetup.worker.execute',return_value='broken secret '+token):
                with self.assertRaisesRegex(Refused,'Malformed privileged read result'):
                    main([str(config),str(script),'--result',str(result),'--json-reads'])

    def test_parent_reads_file_instead_of_stdout_and_keeps_logs_clean(self):
        with tempfile.TemporaryDirectory() as tmp:
            tv=object.__new__(Transport);tv.profile=profile('qn90a');tv.evidence=Path(tmp)
            tv.root_session=Path(tmp)/'session';tv.native_bundle=None
            safe={'pairing_config':{'token_sha256':sha(b'fixture-secret')}}
            def worker(argv, **kwargs):
                atomic_json(Path(argv[argv.index('--result')+1]),safe)
                self.assertIn('--session',argv);self.assertIn('--json-reads',argv)
                return 'toolkit metadata only'
            with patch('tvsetup.transport.run',side_effect=worker):
                self.assertEqual(tv.root('true',json_reads=True),safe)
            for log in Path(tmp).glob('*.log'):
                self.assertEqual(log.read_text(),'toolkit metadata only')

    def test_redacted_pairing_still_detects_credential_rotation(self):
        from tvsetup.nas import NAS
        from tvsetup.planner import Plan
        p=profile('qn90a')
        original=dict(device_id=p['id'],firmware=p['firmware'],runtime_version=p['runtime'],
            endpoint='https://receiver.example.invalid/v1/devices/qn90a',token='old-fixture-token')
        path='/opt/usr/home/owner/apps_rw/MiniTelemetry/data/config.json'
        state={'pairing_config':pairing_record(original),'files':{path:'a'*64}}
        nas=NAS(Path('/unused'));nas.pairing=Mock(return_value=original)
        plan=Plan('qn90a')
        nas.check_pairing(plan,p,state);self.assertEqual(plan.actions,[])
        nas.pairing.return_value={**original,'token':'rotated-fixture-token'}
        nas.check_pairing(plan,p,state);self.assertEqual(len(plan.actions),1)
        self.assertEqual(plan.actions[0].kind,'pairing')
