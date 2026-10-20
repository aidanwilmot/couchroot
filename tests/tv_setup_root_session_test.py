"""Per-run root reuse and private results, with all device/toolkit I/O faked."""
import contextlib
import io
import json
import os
from pathlib import Path, PurePosixPath
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
            with self.assertRaisesRegex(Refused,'Incomplete root session cache'):
                prepared(p, folder, 'probe')
            build.assert_called_once()

    def test_two_operations_build_once_full_file_result_and_cleanup_on_lost_reply(self):
        for device in ('qn90a', 's90d'):
            with self.subTest(device=device), tempfile.TemporaryDirectory() as tmp:
                folder=Path(tmp); calls=[]; scripts=[]; uploads=[]
                payload='read result\n'*2000
                p={**profile(device), 'host':'192.0.2.11', 'device_id':'fixture-device'}
                class Client:
                    def __init__(self,*args):self_outer.assertEqual(args[1],p["host"])
                    def connect(self):pass
                    def require_device(self):pass
                    def capture(self,*args,**kwargs):
                        return SimpleNamespace(transport_returncode=0,output='a'*64+'  /etc/passwd\n'+'b'*64+'  /usr/share/sdbd/public.pem\n[exit:0]\n')
                    def push(self,source,target):
                        uploads.append(source.name)
                        if source.name=='operation.sh':scripts.append(source.read_text())
                        if source.name in ('result.txt','read.tmp'):
                            self_outer.assertEqual(source.stat().st_mode & 0o777, 0o600)
                    def pull(self,remote,local):
                        self_outer.assertIsInstance(remote,PurePosixPath)
                        self_outer.assertEqual(remote.name,'result.txt')
                        self_outer.assertEqual(local.name,'downloaded-result.txt')
                        local.write_text(payload)
                    def run(self,*args,**kwargs):
                        raise AssertionError('unscoped SDB run bypasses serial and pull error checks')
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
                    with self.assertRaisesRegex(Refused,'lost reply') as failure:
                        execute(p, 'printf third', session=folder/'session', capture_result=True)
                    self.assertEqual(failure.exception.output,payload)
                build.assert_called_once()
                self.assertEqual(len(scripts),3)
                for n,word in enumerate(('first','second','third')):
                    self.assertIn('printf '+word, scripts[n])
                    self.assertIn('result.txt', scripts[n])
                    self.assertIn(p['host_sha256'], scripts[n])
                self.assertNotIn('test-private.pem',uploads)
                self.assertEqual([label for label,_ in calls], ['setup-root-stage','setup-root-operation','setup-root-cleanup']*3)
                for label,script in calls:
                    if label=='setup-root-stage':
                        self.assertIn("stat -c '%U:%G:%a'",script)
                    if label=='setup-root-operation':
                        self.assertIn('trap ',script)
                        self.assertIn('chmod 600 ',script)
                        completed=script.split('completed() {',1)[1].split('}\ntrap',1)[0]
                        self.assertIn('RootIdentity.dll',completed)
                        self.assertNotIn('result.txt',completed)
                        # Execute the actual generated trap locally, with all paths
                        # redirected into a temporary tree and rmdir forced to fail.
                        from tvsetup.root import BASE
                        trap=script[script.index('cleanup() {'):script.index('\n',script.index("trap '"))]
                        for status in (0,7):
                            with tempfile.TemporaryDirectory() as local:
                                base=Path(local);(base/'on-demand').mkdir()
                                result=base/('codex-qn90a-root-proof' if device=='qn90a' else 'codex-namespace-proof')/'result.txt'
                                result.parent.mkdir();result.write_text('failure output')
                                command='set -eu\nrmdir() { return 1; }\n'+trap.replace(BASE,local+'/')+'\nexit '+str(status)
                                finished=subprocess.run(['sh','-c',command],capture_output=True)
                                self.assertEqual(finished.returncode,status,finished.stderr)
                                self.assertEqual(result.read_text(),'failure output')
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

class RecoveryHygieneTests(unittest.TestCase):
    def test_failure_output_is_logged_but_read_credentials_are_not(self):
        from tvsetup import worker
        for reads in (False,True):
            with tempfile.TemporaryDirectory() as tmp:
                tv=object.__new__(Transport);tv.profile=profile('qn90a');tv.evidence=Path(tmp)
                tv.root_session=Path(tmp)/'session';tv.native_bundle=None
                secret='fixture-sensitive-value'
                failure=Refused('remote failed')
                failure.output=('partial '+secret.encode().hex()) if reads else 'stdout before failure\nstderr reason'
                def dispatch(argv,**kwargs):
                    with patch('tvsetup.worker.execute',side_effect=failure):
                        try:worker.main(argv[3:])
                        except Refused:
                            error=Refused('worker failed');error.output='safe worker failure';raise error
                with patch('tvsetup.transport.run',side_effect=dispatch):
                    with self.assertRaises(Refused):tv.root('false',json_reads=reads)
                log=next(Path(tmp).glob('*.log'))
                if reads:
                    self.assertNotIn(secret.encode().hex(),log.read_text())
                    self.assertIn('omitted',log.read_text())
                else:self.assertIn(failure.output,log.read_text())
                self.assertEqual(log.stat().st_mode & 0o777,0o600)

    def test_invalid_pairing_is_safe_unsupported_state_not_a_snapshot_failure(self):
        from tvsetup.worker import decode_reads
        from tvsetup.planner import plan
        from tvsetup.config import resolve
        from tv_setup_planner_test import accepted
        for value in (["private value"], {'token':123}, 'private value'):
            data=decode_reads(json.dumps({'pairing_config':json.dumps(value).encode().hex()}))
            self.assertEqual(data['pairing_config'],{'unsupported':'Malformed private pairing configuration'})
            state=accepted('qn90a');state.update(data)
            proposal=plan(profile('qn90a'),resolve('qn90a',overrides={'components':['telemetry']}),state)
            self.assertTrue(any('Malformed private pairing' in reason for reason in proposal.issues))
            # Driver.snapshot remains usable by rollback, independently of plan admission.
            from tvsetup.operations import Driver
            driver=object.__new__(Driver);driver.tv=Mock();driver.tv.snapshot.return_value=state
            self.assertEqual(driver.snapshot(),state)

    def test_transport_close_removes_only_its_build_cache_even_on_interrupt(self):
        client=Mock();client.capture.return_value=SimpleNamespace(output='\n[exit:0]\n',transport_returncode=0)
        toolkit=SimpleNamespace(device=lambda cfg:'192.0.2.30',SdbClient=lambda *a:client)
        with tempfile.TemporaryDirectory() as tmp,patch('tvsetup.toolkit.load',return_value=toolkit):
            root=Path(tmp);(root/'journal.json').write_text('recovery')
            p={**profile('qn90a'),'host':'192.0.2.11','device_id':'fixture-device'}
            with self.assertRaises(KeyboardInterrupt):
                with Transport(p,root) as tv:
                    cache=tv.root_session;(cache/'partial').write_text('build')
                    raise KeyboardInterrupt()
            self.assertFalse(cache.exists());self.assertEqual((root/'journal.json').read_text(),'recovery')

    def test_payload_is_private_under_permissive_umask(self):
        from tvsetup.operations import Driver
        from tvsetup.planner import Action
        with tempfile.TemporaryDirectory() as tmp:
            driver=object.__new__(Driver);driver.folder=Path(tmp)
            action=Action('private','telemetry','preferences',None,{'enabled':False},{})
            old=os.umask(0)
            try:result=driver.prepare(action)
            finally:os.umask(old)
            self.assertEqual(Path(result['artifact']).stat().st_mode & 0o777,0o600)

    def test_download_is_unlinked_before_temp_cleanup_when_pull_is_interrupted(self):
        from tvsetup import root
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);operation=folder/'operation';operation.mkdir()
            p={**profile('qn90a'),'host':'192.0.2.11','device_id':'fixture-device'}
            client=Mock()
            client.capture.return_value=SimpleNamespace(transport_returncode=0,output='a'*64+'  /etc/passwd\n'+'b'*64+'  /usr/share/sdbd/public.pem\n[exit:0]\n')
            def pull(remote,local):
                local.write_text('sensitive downloaded bytes');raise KeyboardInterrupt()
            client.pull.side_effect=pull
            toolkit=SimpleNamespace(device=lambda cfg:'192.0.2.30',SdbClient=lambda *a:client,capture=Mock())
            with patch.object(root,'PRIVATE',folder),patch.object(root,'load',return_value=toolkit), \
                 patch.object(root,'prepare_artifacts',return_value={}), \
                 patch.object(root.tempfile,'TemporaryDirectory',return_value=contextlib.nullcontext(str(operation))):
                with self.assertRaises(KeyboardInterrupt):root.execute(p,'false',capture_result=True)
            self.assertFalse((operation/'downloaded-result.txt').exists())
            self.assertEqual(toolkit.capture.call_args.args[-1],'setup-root-cleanup')
