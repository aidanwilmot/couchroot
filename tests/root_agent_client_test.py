import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SOURCE=Path(__file__).resolve().parents[1]/'research/autonomous-root/client.py'
spec=importlib.util.spec_from_file_location('root_agent_client_tests', SOURCE)
client=importlib.util.module_from_spec(spec)
spec.loader.exec_module(client)

class RootAgentClientTests(unittest.TestCase):
    def test_wait_requires_new_boot_and_ready_worker(self):
        observations=iter([
            dict(boot_id='old',worker_ready=True,identity={'uid':0}),
            dict(boot_id='new',worker_ready=False,identity={'uid':0}),
            dict(boot_id='new',worker_ready=True,identity={'uid':0}),
        ])
        with patch.object(client,'request',side_effect=lambda *a,**kw:next(observations)) as request,patch.object(client.time,'sleep'):
            self.assertEqual(client.wait_ready({},'old',10)['boot_id'],'new')
            self.assertEqual(request.call_count,3)
            self.assertLessEqual(request.call_args.kwargs['timeout'],10)

    def test_upload_is_chunked_and_commit_has_precondition(self):
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'source';data=b'abc'*800000;source.write_bytes(data)
            operations=[];chunks=[]
            def operation(config,value,**kwargs):
                operations.append(value)
                if value['op']=='file.begin':return dict(transfer_id='session',chunk_bytes=1048576)
                if value['op']=='file.write':
                    chunk=kwargs['binary'];chunks.append(chunk)
                    self.assertEqual(hashlib.sha256(chunk).hexdigest(),value['sha256'])
                    return dict(offset=value['offset']+len(chunk))
                return dict(committed=True)
            with patch.object(client,'operation',side_effect=operation):
                client.upload({},source,'/opt/couchroot-agent/files/test','a'*64)
            self.assertEqual(b''.join(chunks),data)
            self.assertEqual(len(chunks),3)
            self.assertEqual(operations[0]['expected_sha256'],'a'*64)
            self.assertEqual(operations[-1]['op'],'file.commit')

    def test_changed_download_never_publishes(self):
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/'target'
            def operation(config,value,**kwargs):
                if value['op']=='file.open':return dict(transfer_id='session',chunk_bytes=1048576,size=3,sha256=hashlib.sha256(b'old').hexdigest())
                return b'new'
            with patch.object(client,'operation',side_effect=operation):
                with self.assertRaisesRegex(RuntimeError,'changed or digest mismatch'):client.download({},'/usr/lib/example',target)
            self.assertFalse(target.exists())
            self.assertEqual(len(list(Path(folder).glob('*.part-*'))),1)

    def test_uncertain_chunk_is_not_replayed_or_committed(self):
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'source';source.write_bytes(b'abc')
            with patch.object(client,'operation',side_effect=[dict(transfer_id='session',chunk_bytes=1048576),TimeoutError('lost')]) as operation:
                with self.assertRaises(TimeoutError):client.upload({},source,'/opt/couchroot-agent/files/test')
                self.assertEqual(operation.call_count,2)

if __name__=='__main__':unittest.main()

class OperationDeadlineTests(unittest.TestCase):
    def test_client_budgets_match_contract_and_are_passed_per_operation(self):
        import json
        contract=json.loads((SOURCE.parent.parent.parent/'tests/worker-parity/contract.json').read_text())
        deadlines=contract['response_deadlines']
        for op in contract['operations']:
            expected=(deadlines['operation_ms'].get(op,deadlines['default_ms'])+deadlines['client_margin_ms'])/1000
            with self.subTest(op=op),patch.object(client,'request',return_value={}) as request:
                self.assertEqual(client.operation_timeout(op),expected)
                client.operation({},dict(op=op,timeout_ms=86400000))
                self.assertEqual(request.call_args.kwargs['timeout'],expected)
