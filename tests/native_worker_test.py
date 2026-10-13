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
        try:self.proc.communicate(timeout=3)
        except subprocess.TimeoutExpired:self.proc.kill();self.proc.communicate()
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
            r=self.op(op);self.assertFalse(r['ok']);self.assertIn('Unsupported',r['error'])
        ids=[self.begin(b'x',f'file-{i}') for i in range(8)]
        self.assertFalse(self.op('file.begin',path=str(self.root/'ninth'),size=0,sha256=hashlib.sha256(b'').hexdigest(),expected_sha256='absent')['ok'])
        for id in ids:self.assertTrue(self.op('file.close',transfer_id=id)['ok'])
    def test_nonzero_timeout_and_bounded_output(self):
        for command,timeout,code,timed in [('printf stdout; printf stderr >&2; exit 7',1000,7,0),('sleep 2; touch '+str(self.root/'survivor'),100,124,1),('head -c 1100000 /dev/zero',5000,0,0)]:
            self.seq+=1;self.send(f'EXEC\t{self.seq}\t{timeout}\t'+base64.b64encode(command.encode()).decode())
            f=self.receive().split('\t');self.assertEqual(f[:4],['RESULT',str(self.seq),str(code),str(timed)])
            self.assertLessEqual(len(base64.b64decode(f[4])),1048576)
        self.assertFalse((self.root/'survivor').exists())
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
