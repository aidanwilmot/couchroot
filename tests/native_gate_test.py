"""No network: exercise the gate with authenticated-client and shell fixtures."""
import base64
import copy
from pathlib import Path
import subprocess
import tempfile
import unittest

from tvsetup import native_gate as gate
from tvsetup.common import REPO, Refused


class NativeGateTests(unittest.TestCase):
    def status(self):
        return dict(device='qn90a', connected=True, worker_ready=True, identity={'uid':0},
                    worker_selection=dict(phase='stable', pending=None,
                                          selected_implementation='native-prototype'))

    def request(self, status=None, output=None, mutate_result=None, after=None):
        calls=[]; status=self.status() if status is None else status
        def request(credentials, method, route, body=None):
            calls.append((method,route,body))
            if method=='GET':
                return copy.deepcopy(after if len(calls)>1 and after is not None else status)
            self.assertEqual((method,route),('POST','/v1/exec'))
            self.assertEqual(base64.b64decode(body['command'].split()[2]).decode(),gate.marker_script())
            result=dict(id=body['id'],exit_code=0,timed_out=False,stderr='',
                        stdout=gate.END+'\n' if output is None else output)
            if mutate_result:mutate_result(result)
            return result
        return request,calls

    def test_pass_uses_only_status_and_list_only_exec(self):
        for device in ('qn90a','s90d'):
            status=self.status();status['device']=device
            request,calls=self.request(status)
            self.assertTrue(gate.inspect(device,{'device':device},request)['ok'])
            self.assertEqual([(m,r) for m,r,_ in calls],
                             [('GET','/v1/status'),('POST','/v1/exec'),('GET','/v1/status')])

    def test_bad_selection_or_credentials_never_submits_exec(self):
        for field,value in [('phase','legacy-managed'),('pending',{}),
                            ('selected_implementation','managed'),('pending','missing')]:
            status=self.status();status['worker_selection'][field]=value
            if value=='missing':del status['worker_selection'][field]
            request,calls=self.request(status)
            self.assertFalse(gate.inspect('qn90a',{'device':'qn90a'},request)['ok'])
            self.assertEqual(len(calls),1)
        request,calls=self.request()
        with self.assertRaises(Refused):gate.inspect('qn90a',{'device':'s90d'},request)
        self.assertEqual(calls,[])

    def test_each_marker_blocks_including_dangling_symlinks_and_arbitrary_activation(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory=Path(tmp)
            script=gate.marker_script(directory)
            for name in (*gate.MARKERS,'other.activation.json.pending'):
                marker=directory/name;marker.symlink_to(directory/'absent')
                result=subprocess.run(['sh','-c',script],capture_output=True,text=True)
                self.assertEqual(result.returncode,0,result.stderr)
                request,_=self.request(output=result.stdout)
                report=gate.inspect('qn90a',{'device':'qn90a'},request)
                self.assertFalse(report['ok']);self.assertEqual(report['markers'],[name])
                self.assertTrue(marker.is_symlink());marker.unlink()
            (directory/'keep').write_text('untouched')
            result=subprocess.run(['sh','-c',script],capture_output=True,text=True)
            self.assertEqual(result.stdout,gate.END+'\n')
            self.assertEqual((directory/'keep').read_text(),'untouched')
            self.assertNotEqual(subprocess.run(['sh','-c',gate.marker_script(directory/'absent')],
                                              capture_output=True).returncode,0)

    def test_errors_truncation_and_changes_fail_closed_without_retry(self):
        for changes in [dict(exit_code=1),dict(timed_out=True),dict(id='wrong'),
                        dict(stdout=''),dict(stderr='permission denied')]:
            request,calls=self.request(mutate_result=lambda r:r.update(changes))
            with self.assertRaises(Refused):gate.inspect('qn90a',{'device':'qn90a'},request)
            self.assertEqual(len(calls),2)
        after=self.status();after['worker_selection']['pending']={}
        request,_=self.request(after=after)
        self.assertFalse(gate.inspect('qn90a',{'device':'qn90a'},request)['ok'])
        calls=[]
        def lost(*args):
            calls.append(args)
            if len(calls)==1:return self.status()
            raise TimeoutError('lost reply')
        with self.assertRaises(TimeoutError):gate.inspect('qn90a',{'device':'qn90a'},lost)
        self.assertEqual(len(calls),2)

    def test_marker_list_covers_startup_refusals(self):
        source=(REPO/'agent/service/native-startup.js').read_text()
        block=source.split('for (const name of [',1)[1].split('])',1)[0]
        import re
        self.assertEqual(set(re.findall(r"'([^']+\.pending)'",block)),
                         set(gate.MARKERS)|{'.activation.json.pending'})
