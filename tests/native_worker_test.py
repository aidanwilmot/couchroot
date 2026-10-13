"""Run inside the Linux toolchain container against a locally built prototype.
No TV access. Native worker remains outside production packaging.
"""
import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import time
import signal
import unittest

@unittest.skipUnless(os.environ.get('NATIVE_WORKER'), 'set NATIVE_WORKER to a Linux prototype build')
class NativeWorkerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='couchroot-native-')
        self.root=Path(self.tmp.name); self.root.chmod(0o700)
        self.secret=os.urandom(32); self.nonce=os.urandom(32); self.seq=0
        self.token=self.root/'token'; self.token.write_bytes(base64.b64encode(self.secret));self.token.chmod(0o600)
        self.listener=socket.socket();self.listener.bind(('127.0.0.1',0));self.listener.listen();self.listener.settimeout(5)
        launcher=Path('/bin/true').resolve();sha=hashlib.sha256(launcher.read_bytes()).hexdigest()
        self.proc=subprocess.Popen([os.environ['NATIVE_WORKER'],'127.0.0.1',str(self.listener.getsockname()[1]),str(self.token),str(self.root),str(launcher),sha],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        self.sock,_=self.listener.accept();self.sock.settimeout(5);self.stream=self.sock.makefile('rb')
        self.sock.sendall(b'SAMSUNG-TV-ROOT/1\t'+self.nonce.hex().encode()+b'\n')
        self.assertTrue(self.receive().startswith('AUTH\t'))
    def tearDown(self):
        self.stream.close();self.sock.close();self.listener.close()
        try:_,stderr=self.proc.communicate(timeout=3)
        except subprocess.TimeoutExpired:self.proc.kill();_,stderr=self.proc.communicate()
        self.assertNotRegex(stderr.decode(errors='replace'), r'ERROR: AddressSanitizer|runtime error:|SUMMARY:')
        self.tmp.cleanup()
    def authenticated(self,payload):
        raw=payload.encode();return raw+b'\t'+hmac.new(self.secret,self.nonce+b'\0'+raw,hashlib.sha256).hexdigest().encode()+b'\n'
    def send(self,payload,body=b'',fragment=False):
        raw=self.authenticated(payload)+body
        if fragment:
            for i in range(0,len(raw),997):self.sock.sendall(raw[i:i+997])
        else:self.sock.sendall(raw)
    def receive(self):
        raw=self.stream.readline()
        if not raw:raise AssertionError(self.proc.communicate(timeout=3)[1].decode())
        payload,mac=raw.rstrip(b'\n').rsplit(b'\t',1)
        self.assertEqual(mac,hmac.new(self.secret,self.nonce+b'\0'+payload,hashlib.sha256).hexdigest().encode())
        return payload.decode()
    def result(self):
        frame=self.receive().split('\t');self.assertEqual(frame[:2],['OPRESULT',str(self.seq)])
        return json.loads(base64.b64decode(frame[2]))
    def op(self,op,**kwargs):
        self.seq+=1;self.send(f'OP\t{self.seq}\t'+base64.b64encode(json.dumps(dict(op=op,**kwargs)).encode()).decode());return self.result()
    def begin(self,data,path='file',expected='absent'):
        r=self.op('file.begin',path=str(self.root/path),size=len(data),sha256=hashlib.sha256(data).hexdigest(),expected_sha256=expected)
        self.assertTrue(r['ok'],r);return r['result']['transfer_id']
    def upload(self,id,data,offset=0,digest=None):
        self.seq+=1;sha=digest or hashlib.sha256(data).hexdigest();self.send(f'OPWRITE\t{self.seq}\t{id}\t{offset}\t{len(data)}\t{sha}',data,True);return self.result()
    def test_transfers_and_alignment(self):
        data=os.urandom(1048576);id=self.begin(data)
        self.assertFalse(self.upload(id,data,digest='0'*64)['ok'])
        self.assertEqual(self.op('file.status',transfer_id=id)['result']['offset'],0)
        self.assertFalse(self.upload('f'*32,data)['ok'])
        self.assertFalse(self.upload(id,data,1)['ok'])
        self.assertTrue(self.upload(id,data)['ok'])
        self.assertFalse(self.upload(id,data)['ok'])
        self.assertTrue(self.op('file.commit',transfer_id=id)['ok'])
        self.assertEqual((self.root/'file').read_bytes(),data)
        opened=self.op('file.open',path=str(self.root/'file'))['result']
        self.seq+=1;self.send(f'OP\t{self.seq}\t'+base64.b64encode(json.dumps(dict(op='file.read',transfer_id=opened['transfer_id'],offset=1048560,length=100)).encode()).decode())
        header=self.receive().split('\t');self.assertEqual(header[:4],['OPDATA',str(self.seq),'1048560','16']);raw=self.stream.read(16);self.assertEqual(raw,data[-16:]);self.assertEqual(hashlib.sha256(raw).hexdigest(),header[4])
        self.assertTrue(self.op('file.close',transfer_id=opened['transfer_id'])['ok'])
        id=self.begin(b'replacement',expected='0'*64);self.assertTrue(self.upload(id,b'replacement')['ok']);self.assertFalse(self.op('file.commit',transfer_id=id)['ok']);self.op('file.close',transfer_id=id)
        self.assertEqual((self.root/'file').read_bytes(),data)
        id=self.begin(b'replacement',expected=hashlib.sha256(data).hexdigest());self.assertTrue(self.upload(id,b'replacement')['ok']);self.assertTrue(self.op('file.commit',transfer_id=id)['ok'])
        self.assertEqual((self.root/'file').read_bytes(),b'replacement')
    def test_bounds_paths_and_unsupported(self):
        for path in ['/etc/passwd',str(self.root/'../escape'),str(self.root/'nested/file')]:
            self.assertFalse(self.op('file.open',path=path)['ok'])
        (self.root/'link').symlink_to('/etc/passwd');self.assertFalse(self.op('file.open',path=str(self.root/'link'))['ok'])
        for op in ['job.start','job.status','job.output','job.cancel','job.forget','helper.prepare','helper.release']:
            r=self.op(op);self.assertFalse(r['ok']);self.assertEqual(r['outcome'],'failed')
        ids=[self.begin(b'x',f'file-{i}') for i in range(8)]
        self.assertFalse(self.op('file.begin',path=str(self.root/'ninth'),size=0,sha256=hashlib.sha256(b'').hexdigest(),expected_sha256='absent')['ok'])
        for id in ids:self.assertTrue(self.op('file.close',transfer_id=id)['ok'])
    def test_nonzero_timeout_and_bounded_output(self):
        for command,timeout,code,timed in [('printf stdout; printf stderr >&2; exit 7',1000,7,0),('sleep 2; touch '+str(self.root/'survivor'),100,124,1),('head -c 1100000 /dev/zero',5000,0,0)]:
            self.seq+=1;self.send(f'EXEC\t{self.seq}\t{timeout}\t'+base64.b64encode(command.encode()).decode())
            f=self.receive().split('\t');self.assertEqual(f[:4],['RESULT',str(self.seq),str(code),str(timed)])
            self.assertLessEqual(len(base64.b64decode(f[4])),1048576)
        self.assertFalse((self.root/'survivor').exists())
    def job(self, op, id='native-test-job-01', **kwargs):
        return self.op(op, id=id, **kwargs)
    def start_job(self, command, timeout=5000, id='native-test-job-01'):
        result=self.job('job.start', id, command=command, timeout_ms=timeout, profile='root')
        self.assertTrue(result['ok'], result)
        return result['result']
    def completed(self, id='native-test-job-01'):
        deadline=time.monotonic()+5
        while time.monotonic()<deadline:
            result=self.job('job.status', id)['result']
            if result['exit_code'] is not None:return result
            time.sleep(.02)
        self.fail('Job did not terminate')
    def test_job_results_duplicate_and_retention(self):
        started=self.start_job('printf stdout; printf stderr >&2; exit 7')
        self.assertGreater(started['pid'],0)
        self.assertTrue(started['process_start'])
        done=self.completed();self.assertEqual((done['state'],done['exit_code']),('completed',7))
        self.assertFalse(done['persistence_failed'])
        result=self.job('job.output',stdout_cursor=0,stderr_cursor=0)['result']
        self.assertEqual(base64.b64decode(result['stdout']['data']),b'stdout')
        self.assertEqual(base64.b64decode(result['stderr']['data']),b'stderr')
        self.assertFalse(self.job('job.start',command='touch '+str(self.root/'replayed'),timeout_ms=1000,profile='root')['ok'])
        self.assertFalse((self.root/'replayed').exists())
        self.assertTrue(self.job('job.forget')['ok'])
        self.assertFalse(self.job('job.status')['ok'])
        for i in range(16):self.start_job(':',id=f'native-retention-{i:02}')
        self.assertFalse(self.job('job.start','native-retention-17',command=':',timeout_ms=1000,profile='root')['ok'])
        for i in range(16):
            self.completed(f'native-retention-{i:02}');self.assertTrue(self.job('job.forget',f'native-retention-{i:02}')['ok'])
    def test_job_ring_cursors(self):
        self.start_job("head -c 1200000 /dev/zero; printf end; printf error >&2")
        done=self.completed();self.assertEqual(done['exit_code'],0)
        result=self.job('job.output',stdout_cursor=0,stderr_cursor=0)['result']
        self.assertTrue(result['stdout']['truncated']);self.assertEqual(result['stdout']['end_cursor'],1200003)
        self.assertEqual(len(base64.b64decode(result['stdout']['data'])),65536)
        cursor=1200000
        result=self.job('job.output',stdout_cursor=cursor,stderr_cursor=0)['result']
        self.assertEqual(base64.b64decode(result['stdout']['data']),b'end')
        self.assertEqual(base64.b64decode(result['stderr']['data']),b'error')
        for cursor in [-1,1200004]:self.assertFalse(self.job('job.output',stdout_cursor=cursor,stderr_cursor=0)['ok'])
    def test_jobs_timeout_while_idle_and_foreground_busy(self):
        self.start_job('sleep 1; touch '+str(self.root/'survivor'),100)
        time.sleep(.4)
        done=self.completed();self.assertEqual(done['state'],'timed_out');self.assertTrue(done['timed_out'])
        self.start_job('sleep 1; touch '+str(self.root/'survivor2'),100,'native-test-job-02')
        self.seq+=1;self.send(f'EXEC\t{self.seq}\t3000\t'+base64.b64encode(b'sleep 1.2').decode());self.receive()
        self.assertEqual(self.completed('native-test-job-02')['state'],'timed_out')
        self.assertFalse((self.root/'survivor').exists());self.assertFalse((self.root/'survivor2').exists())
    def test_cancel_and_disconnect_kill_process_groups(self):
        self.start_job('sleep 2; touch '+str(self.root/'survivor'))
        self.assertFalse(self.job('job.forget')['ok'])
        self.assertTrue(self.job('job.cancel')['ok']);self.assertEqual(self.completed()['state'],'cancelled')
        started=self.start_job('sleep 2; touch '+str(self.root/'survivor2'),5000,'native-test-job-02')
        self.sock.shutdown(socket.SHUT_WR);self.assertEqual(self.stream.read(),b'');self.proc.wait(timeout=3)
        with self.assertRaises(ProcessLookupError):os.kill(started['pid'],0)
        record=json.loads((self.root/'.jobs/native-test-job-02.json').read_text());self.assertEqual(record['state'],'interrupted')
        self.assertFalse((self.root/'survivor').exists());self.assertFalse((self.root/'survivor2').exists())
    def test_signal_cleanup(self):
        started=self.start_job('sleep 30')
        self.proc.send_signal(signal.SIGTERM);self.proc.wait(timeout=3)
        with self.assertRaises(ProcessLookupError):os.kill(started['pid'],0)
        record=json.loads((self.root/'.jobs/native-test-job-01.json').read_text());self.assertEqual(record['state'],'interrupted')
    def test_saved_intent_never_replayed(self):
        record=self.root/'.jobs/native-saved-job-1.json'
        data={'id':'native-saved-job-1','boot_id':self.op('status')['result']['boot_id'],'state':'running','pid':os.getpid(),'process_start':'0'}
        record.write_text(json.dumps(data));record.chmod(0o600)
        status=self.job('job.status',data['id'])['result'];self.assertEqual(status['state'],'unknown');self.assertFalse(status['output_available'])
        self.assertFalse(self.job('job.cancel',data['id'])['ok'])
        self.assertFalse(self.job('job.forget',data['id'])['ok'])
        self.assertFalse(self.job('job.start',data['id'],command=':',timeout_ms=1000,profile='root')['ok'])
        data['state']='completed';record.write_text(json.dumps(data))
        self.assertTrue(self.job('job.forget',data['id'])['ok'])
    def test_helpers_fail_closed_without_smack_mount_support(self):
        path=self.root/'helper';path.write_bytes(b'not executable');path.chmod(0o600)
        result=self.op('helper.prepare',path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertFalse(result['ok']);self.assertIn('unavailable',result['error'])
        self.assertEqual(path.read_bytes(),b'not executable')
        self.assertFalse(self.op('helper.prepare',path='/bin/true',sha256='0'*64)['ok'])
    def test_truncated_upload_cannot_publish(self):
        id=self.begin(b'abc');self.seq+=1;self.send(f'OPWRITE\t{self.seq}\t{id}\t0\t3\t'+hashlib.sha256(b'abc').hexdigest(),b'a');self.sock.shutdown(socket.SHUT_WR)
        self.assertEqual(self.stream.read(),b'');self.proc.wait(timeout=3);self.assertNotEqual(self.proc.returncode,0);self.assertFalse((self.root/'file').exists());self.assertEqual(list(self.root.glob('.upload-*')),[])
    def test_bad_mac_fails_closed(self):
        self.sock.sendall(b'PING\t1\t'+b'0'*64+b'\n');self.assertEqual(self.stream.read(),b'');self.proc.wait(timeout=3);self.assertNotEqual(self.proc.returncode,0)
    def test_sequence_replay_fails_closed(self):
        self.assertTrue(self.op('status')['ok']);self.send('PING\t1');self.assertEqual(self.stream.read(),b'');self.proc.wait(timeout=3);self.assertNotEqual(self.proc.returncode,0)
    def test_oversized_header_fails_before_body(self):
        id=self.begin(b'abc');self.seq+=1;self.send(f'OPWRITE\t{self.seq}\t{id}\t0\t1048577\t'+hashlib.sha256(b'abc').hexdigest());self.assertEqual(self.stream.read(),b'');self.proc.wait(timeout=3);self.assertNotEqual(self.proc.returncode,0)
    def test_malformed_json_fails_closed(self):
        self.send('OP\t1\t'+base64.b64encode(b'{"op":"status"}garbage').decode());self.assertEqual(self.stream.read(),b'');self.proc.wait(timeout=3);self.assertNotEqual(self.proc.returncode,0)

if __name__=='__main__':unittest.main()
