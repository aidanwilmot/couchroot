import json
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from tvsetup.agent_transport import AgentTransport
from tvsetup.common import Refused
from tvsetup.config import profile

class AgentTransportTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.tv=object.__new__(AgentTransport);self.tv.evidence=Path(self.tmp.name);self.tv.credentials={}
        self.tv.profile=profile('s90d');self.tv.identity_diagnostics=[]
    def test_lost_response_is_journaled_and_never_retried(self):
        calls=[]
        def request(*args):calls.append(args);raise TimeoutError('lost response')
        self.tv.api=SimpleNamespace(request=request)
        with self.assertRaises(TimeoutError):self.tv._execute('true')
        self.assertEqual(len(calls),1)
        record=json.loads(next(self.tv.evidence.glob('*.json')).read_text())
        self.assertEqual(record['state'],'submitted')
    def test_shell_bytes_survive_worker_argument_quoting(self):
        import base64
        captured=[]
        def request(*args):
            captured.append(args[-1]['command'])
            return dict(id=args[-1]['id'],exit_code=0,stdout='')
        self.tv.api=SimpleNamespace(request=request)
        script="find /tmp -exec true {} " + chr(92) + ";\n"
        self.tv._execute(script)
        self.assertEqual(base64.b64decode(captured[0].split()[2]).decode(),script)
        self.assertNotIn(chr(92),captured[0])
    def test_wrong_request_identity_is_refused(self):
        self.tv.api=SimpleNamespace(request=lambda *args:dict(id='other',exit_code=0,stdout='bad'))
        with self.assertRaises(Refused):self.tv._execute('true')
    def test_timed_out_command_cannot_count_as_success(self):
        self.tv.api=SimpleNamespace(request=lambda *args:dict(id=args[-1]['id'],exit_code=0,timed_out=True))
        with self.assertRaises(Refused):self.tv._execute('true')
    def test_arbitrary_file_push_and_namespace_changes_are_refused(self):
        with self.assertRaises(Refused):self.tv.push(Path('not-read'),'/etc/passwd')
        with self.assertRaises(Refused):self.tv.root('true',namespace=True)
    def test_nonzero_exit_is_a_completed_result(self):
        self.tv.api=SimpleNamespace(request=lambda *args:dict(id=args[-1]['id'],exit_code=1,stdout='0\n',stderr=''))
        result=self.tv.execute_result('grep -c missing /tmp/example')
        self.assertEqual(result['exit_code'],1)
        self.assertEqual(result['stdout'],'0\n')
        self.assertEqual(self.tv._execute('false',check=False),'0\n')
        with self.assertRaisesRegex(Refused,'completed with exit code 1'):self.tv._execute('false')
        self.assertTrue(all(json.loads(p.read_text())['state']=='completed' for p in self.tv.evidence.glob('*.json')))

    def test_command_limit_refuses_before_submission(self):
        with self.assertRaises(Refused):self.tv._execute('x'*16385)

if __name__=='__main__':unittest.main()
