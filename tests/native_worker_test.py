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
        launcher=self.root/'launcher-source';launcher.write_bytes(Path('/bin/true').read_bytes());launcher.chmod(0o600);sha=hashlib.sha256(launcher.read_bytes()).hexdigest()
        self.worker_args=[os.environ['NATIVE_WORKER'],'127.0.0.1',str(self.listener.getsockname()[1]),str(self.token),str(self.root),str(launcher),sha]
        self.proc=subprocess.Popen(self.worker_args,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        self.sock,_=self.listener.accept();self.sock.settimeout(5);self.stream=self.sock.makefile('rb')
        self.sock.sendall(b'SAMSUNG-TV-ROOT/1\t'+self.nonce.hex().encode()+b'\n')
        auth=self.receive().split('\t');self.assertEqual(auth[0],'AUTH');self.worker_pid=int(auth[1]);self.assertNotEqual(self.worker_pid,self.proc.pid)
    def restart(self):
        self.stream.close();self.sock.close()
        _,stderr=self.proc.communicate(timeout=5)
        self.assertNotRegex(stderr.decode(errors='replace'),r'ERROR: AddressSanitizer|runtime error:|SUMMARY:')
        self.secret=os.urandom(32);self.nonce=os.urandom(32);self.seq=0
        self.token.write_bytes(base64.b64encode(self.secret));self.token.chmod(0o600)
        self.proc=subprocess.Popen(self.worker_args,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        self.sock,_=self.listener.accept();self.sock.settimeout(5);self.stream=self.sock.makefile('rb')
        self.sock.sendall(b'SAMSUNG-TV-ROOT/1\t'+self.nonce.hex().encode()+b'\n')
        auth=self.receive().split('\t');self.assertEqual(auth[0],'AUTH');self.worker_pid=int(auth[1])
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
    @unittest.skipUnless(os.environ.get('NATIVE_WORKER_STORAGE_TEST'), 'isolated mount-capable container required')
    def test_full_and_readonly_job_intent_storage(self):
        import errno
        self.seq+=1;self.send(f'SHUTDOWN\t{self.seq}');self.receive();self.proc.wait(timeout=5)
        launcher=(self.root/'launcher-source').read_bytes()
        subprocess.run(['mount','-t','tmpfs','-o','size=2m,nr_inodes=1024,mode=0700','tmpfs',str(self.root)],check=True)
        try:
            (self.root/'launcher-source').write_bytes(launcher);(self.root/'launcher-source').chmod(0o600)
            self.restart()
            with tempfile.TemporaryDirectory(prefix='native-storage-witness-') as outside:
                marker=Path(outside)/'executed'
                counter=Path(outside)/'run-count'
                self.start_job('printf x >> '+str(counter)+'; sleep 1; exit 19',id='native-storage-finish')
                filler=self.root/'filler'
                with filler.open('wb',buffering=0) as f:
                    with self.assertRaises(OSError) as error:
                        while True:f.write(b'x'*65536)
                self.assertEqual(error.exception.errno,errno.ENOSPC)
                result=self.job('job.start',command='touch '+str(marker),profile='root',timeout_ms=1000)
                self.assertFalse(result['ok']);self.assertFalse(marker.exists())
                self.assertFalse((self.root/'.jobs/native-test-job-01.json').exists())
                self.assertFalse((self.root/'.jobs/native-test-job-01.json.next').exists())
                terminal=self.completed('native-storage-finish')
                self.assertEqual(terminal['exit_code'],19);self.assertTrue(terminal['persistence_failed'])
                filler.unlink()
                deadline=time.monotonic()+5
                while self.job('job.status','native-storage-finish')['result']['persistence_failed']:
                    self.assertLess(time.monotonic(),deadline);time.sleep(.05)
                saved=json.loads((self.root/'.jobs/native-storage-finish.json').read_text())
                self.assertEqual(saved['state'],'completed');self.assertEqual(saved['exit_code'],19)
                self.assertEqual(counter.read_bytes(),b'x')
                self.assertTrue(self.job('job.forget','native-storage-finish')['ok'])
                self.start_job('exit 7');self.assertEqual(self.completed()['exit_code'],7)
                self.assertTrue(self.job('job.forget')['ok'])
                subprocess.run(['mount','-o','remount,ro',str(self.root)],check=True)
                result=self.job('job.start',command='touch '+str(marker),profile='root',timeout_ms=1000)
                self.assertFalse(result['ok']);self.assertFalse(marker.exists())
                subprocess.run(['mount','-o','remount,rw',str(self.root)],check=True)
                self.start_job('exit 8');self.assertEqual(self.completed()['exit_code'],8)
                self.assertTrue(self.job('job.forget')['ok'])
                old=Path(self.op('status')['result']['app_launcher']['path'])
                self.start_job('sleep 30',timeout=60000,id='native-storage-crash')
                with filler.open('wb',buffering=0) as f:
                    with self.assertRaises(OSError) as error:
                        while True:f.write(b'x'*65536)
                self.assertEqual(error.exception.errno,errno.ENOSPC)
                os.kill(self.worker_pid,signal.SIGKILL);self.proc.wait(timeout=5)
                self.assertEqual(self.proc.returncode,125)
                self.assertFalse(old.exists());self.assertTrue((self.root/'.jobs/guardian').exists())
                filler.unlink();self.restart()
                self.assertEqual(self.job('job.status','native-storage-crash')['result']['state'],'interrupted')
                self.assertTrue(self.job('job.forget','native-storage-crash')['ok'])
            self.seq+=1;self.send(f'SHUTDOWN\t{self.seq}');self.receive();self.proc.wait(timeout=5)
        finally:
            subprocess.run(['mount','-o','remount,rw',str(self.root)],check=True)
            if self.proc.poll() is None:
                self.stream.close();self.sock.close();self.proc.wait(timeout=5)
            subprocess.run(['umount',str(self.root)],check=True)
        self.restart()

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
    def test_command_fault_keeps_worker_alive(self):
        for sig in ['SEGV','ABRT','BUS','ILL','FPE']:
            self.seq+=1
            self.send(f'EXEC\t{self.seq}\t2000\t'+base64.b64encode(f'kill -{sig} $$'.encode()).decode())
            self.assertEqual(self.receive().split('\t')[:4],['RESULT',str(self.seq),'137','0'])
            self.assertTrue(self.op('status')['ok'])
        self.start_job('kill -SEGV $$')
        self.assertEqual(self.completed()['exit_code'],137)
        self.assertTrue(self.job('job.forget')['ok'])
        self.start_job('printf recovered')
        self.assertEqual(self.completed()['exit_code'],0)
    @unittest.skipUnless(os.environ.get('NATIVE_WORKER_FAULT_TEST'),'requires separate fault-injection build')
    def test_exec_helper_memory_fault_keeps_worker_alive(self):
        for arg in ['--test-child-fault','--test-child-thread-fault']:
            self.start_job('exec '+os.environ['NATIVE_WORKER']+' '+arg)
            self.assertEqual(self.completed()['exit_code'],137)
            self.assertTrue(self.job('job.forget')['ok'])
            self.assertTrue(self.op('status')['ok'])
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
    def test_independent_launcher_and_guardian_status(self):
        status=self.op('status')['result']
        self.assertEqual(status['guardian_pid'],self.proc.pid)
        self.assertEqual(status['worker_dumpable'],0)
        staged=Path(status['app_launcher']['path'])
        self.assertNotEqual(staged,self.root/'launcher-source')
        self.assertEqual(staged.read_bytes(),(self.root/'launcher-source').read_bytes())
        self.assertEqual(staged.stat().st_mode & 0o777,0o500)
        self.assertTrue(status['app_launcher']['independently_staged'])
        self.assertTrue((self.root/'.jobs/guardian').exists())
    def test_worker_sigkill_recovers_jobs_and_detached_descendants(self):
        status=self.op('status')['result'];staged=Path(status['app_launcher']['path'])
        marker=self.root/'detached-survivor'
        self.start_job('exit 7',id='native-completed-01');self.completed('native-completed-01')
        foreign=self.root/'.jobs/native-foreign-01.json'
        foreign.write_text(json.dumps({'worker_id':'different-owner','id':'native-foreign-01','boot_id':status['boot_id'],'state':'running','pid':os.getpid(),'process_start':'0'}));foreign.chmod(0o600)
        foreign_bytes=foreign.read_bytes()
        started=self.start_job(f"setsid sh -c 'sleep 1; touch {marker}' >/dev/null 2>&1 & echo ready; sleep 30",5000)
        deadline=time.monotonic()+3
        while time.monotonic()<deadline:
            data=self.job('job.output',stdout_cursor=0,stderr_cursor=0)['result']['stdout']['data']
            if b'ready' in base64.b64decode(data):break
            time.sleep(.02)
        else:self.fail('Detached child did not start')
        interrupted_save=self.root/'.jobs/native-test-job-01.json.next';interrupted_save.write_text('partial-save');interrupted_save.chmod(0o600)
        os.kill(self.worker_pid,signal.SIGKILL)
        self.proc.wait(timeout=5);self.assertEqual(self.proc.returncode,137)
        self.assertFalse(staged.exists());self.assertFalse((self.root/'.jobs/guardian').exists())
        with self.assertRaises(ProcessLookupError):os.kill(started['pid'],0)
        record=json.loads((self.root/'.jobs/native-test-job-01.json').read_text())
        self.assertEqual(record['state'],'interrupted');self.assertIsNone(record['exit_code'])
        self.assertEqual(record['recovery'],'guardian-reaped-descendants')
        self.assertFalse(interrupted_save.exists());self.assertEqual(foreign.read_bytes(),foreign_bytes)
        time.sleep(1.1);self.assertFalse(marker.exists())
        self.restart()
        saved=self.job('job.status')['result'];self.assertEqual(saved['state'],'interrupted');self.assertFalse(saved['output_available'])
        completed=self.job('job.status','native-completed-01')['result'];self.assertEqual(completed['state'],'completed');self.assertEqual(completed['record']['exit_code'],7)
        self.assertTrue(self.job('job.forget','native-completed-01')['ok'])
        self.assertFalse(self.job('job.start',command='touch '+str(marker),profile='root',timeout_ms=1000)['ok'])
        self.assertTrue(self.job('job.forget')['ok'])
        self.assertFalse(marker.exists())
    def test_fatal_signal_uses_guardian_recovery(self):
        marker=self.root/'fatal-survivor'
        self.start_job(f"setsid sh -c 'sleep .5; touch {marker}' >/dev/null 2>&1 & printf ready; sleep 30")
        deadline=time.monotonic()+3
        while time.monotonic()<deadline:
            out=self.job('job.output',stdout_cursor=0,stderr_cursor=0)['result']['stdout']['data']
            if b'ready' in base64.b64decode(out):break
            time.sleep(.01)
        else:self.fail('Fatal-signal child not ready')
        os.kill(self.worker_pid,signal.SIGSEGV);self.proc.wait(timeout=5)
        self.assertEqual(self.proc.returncode,139)
        record=json.loads((self.root/'.jobs/native-test-job-01.json').read_text())
        self.assertEqual(record['state'],'interrupted');self.assertIsNone(record['exit_code'])
        self.assertEqual(record['recovery'],'guardian-reaped-descendants')
        self.assertEqual(record['worker_fault_signal'],signal.SIGSEGV)
        time.sleep(.6);self.assertFalse(marker.exists())
        self.restart();self.assertEqual(self.job('job.status')['result']['state'],'interrupted')
    def check_memory_fault(self,thread):
        self.start_job('sleep 30',timeout=60000)
        self.assertTrue(self.op('test.fault',thread=thread)['ok'])
        self.proc.wait(timeout=2);self.assertEqual(self.proc.returncode,139)
        record=json.loads((self.root/'.jobs/native-test-job-01.json').read_text())
        self.assertEqual(record['worker_fault_signal'],signal.SIGSEGV)
        self.assertEqual(record['state'],'interrupted');self.assertIsNone(record['exit_code'])
        self.restart();self.assertEqual(self.job('job.status')['result']['state'],'interrupted')
    @unittest.skipUnless(os.environ.get('NATIVE_WORKER_FAULT_TEST'),'requires separate fault-injection build')
    def test_main_thread_memory_fault_recovery(self):
        self.check_memory_fault(0)
    @unittest.skipUnless(os.environ.get('NATIVE_WORKER_FAULT_TEST'),'requires separate fault-injection build')
    def test_new_thread_memory_fault_recovery(self):
        self.check_memory_fault(1)
    @unittest.skipUnless(os.environ.get('NATIVE_WORKER_FAULT_TEST'),'requires separate fault-injection build')
    def test_progress_watchdog_when_pulse_thread_healthy(self):
        for thread,reason in [(0,'active-request-stalled'),(1,'job-monitor-stalled')]:
            self.start_job('sleep 30',timeout=60000)
            self.assertTrue(self.op('test.stall',thread=thread)['ok'])
            self.proc.wait(timeout=3);self.assertEqual(self.proc.returncode,137)
            record=json.loads((self.root/'.jobs/native-test-job-01.json').read_text())
            self.assertEqual(record['state'],'interrupted')
            self.assertIsNone(record['exit_code'])
            self.assertEqual(record['watchdog_reason'],reason)
            self.restart();self.assertTrue(self.job('job.forget')['ok'])
    def test_stopped_worker_watchdog_recovers(self):
        self.start_job('sleep 30',timeout=60000)
        os.kill(self.worker_pid,signal.SIGSTOP)
        self.proc.wait(timeout=5);self.assertEqual(self.proc.returncode,137)
        record=json.loads((self.root/'.jobs/native-test-job-01.json').read_text())
        self.assertEqual(record['state'],'interrupted');self.assertTrue(record['watchdog_triggered'])
        self.assertFalse(record['watchdog_froze_group']) # Host mode has no freezer controller.
        self.restart();self.assertEqual(self.job('job.status')['result']['state'],'interrupted')
    def guardian_loss(self):
        status=self.op('status')['result']
        self.start_job('sleep 30',timeout=60000)
        self.proc.kill();self.proc.wait(timeout=3)
        # The inherited scope lock remains held until EXITKILL closes worker fds.
        import fcntl
        deadline=time.monotonic()+3
        with (self.root/'.jobs/lock').open('rb') as lock:
            while True:
                try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);break
                except BlockingIOError:
                    if time.monotonic()>deadline:self.fail('Lost guardian descendants retained scope lock')
                    time.sleep(.01)
            fcntl.flock(lock,fcntl.LOCK_UN)
        return status,json.loads((self.root/'.jobs/guardian').read_text())
    def test_guardian_loss_reconciles_without_replaying(self):
        status,journal=self.guardian_loss()
        old=Path(status['app_launcher']['path']);self.assertTrue(old.exists())
        completed=self.root/'.jobs/native-old-complete.json'
        completed.write_text(json.dumps(dict(worker_id=journal['worker_id'],id='native-old-complete',state='completed',exit_code=7)))
        completed.chmod(0o600);original=completed.read_bytes()
        foreign=self.root/'.views/foreign-owner';foreign.mkdir();(foreign/'keep').write_text('keep')
        # A reused PID must not be signaled or trusted as the original guardian.
        journal['pid']=os.getpid();journal['process_start']='0'
        (self.root/'.jobs/guardian').write_text(json.dumps(journal))
        self.restart()
        self.assertTrue(self.op('status')['result']['stale_guardian_reconciled'])
        self.assertFalse(old.exists());self.assertEqual((foreign/'keep').read_text(),'keep')
        self.assertEqual(completed.read_bytes(),original)
        r=self.job('job.status')['result'];self.assertEqual(r['state'],'interrupted')
        self.assertIsNone(r['record']['exit_code']);self.assertEqual(r['record']['recovery'],'stale-guardian-reconciled')
        self.assertFalse(self.job('job.start',command='touch '+str(self.root/'replayed'),profile='root',timeout_ms=1000)['ok'])
        self.assertFalse((self.root/'replayed').exists());self.assertTrue(self.job('job.forget')['ok'])
        self.start_job('exit 8');self.assertEqual(self.completed()['exit_code'],8)
    def test_stale_journal_mismatch_and_live_identity_fail_closed(self):
        import copy
        status,journal=self.guardian_loss();path=self.root/'.jobs/guardian'
        old=Path(status['app_launcher']['path']);old_bytes=old.read_bytes()
        variants=[]
        for key,value in [('schema',1),('prepared',False),('boot_id','different-boot'),('scope_ino',journal['scope_ino']+1),('runtime_ino',journal['runtime_ino']+1)]:
            j=copy.deepcopy(journal);j[key]=value;variants.append(j)
        live=copy.deepcopy(journal);live['pid']=os.getpid();live['process_start']=Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19];variants.append(live)
        for j in variants:
            raw=json.dumps(j);path.write_text(raw)
            other=subprocess.run(self.worker_args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=5)
            self.assertNotEqual(other.returncode,0);self.assertIn(b'unresolved guardian journal',other.stderr)
            self.assertEqual(path.read_text(),raw);self.assertEqual(old.read_bytes(),old_bytes)
            self.assertEqual(json.loads((self.root/'.jobs/native-test-job-01.json').read_text())['state'],'running')
        path.write_text(json.dumps(journal));self.restart()
        self.assertTrue(self.op('status')['result']['stale_guardian_reconciled'])
    def test_stale_journal_metadata_and_partial_write_refusal(self):
        status,journal=self.guardian_loss();path=self.root/'.jobs/guardian'
        original=path.read_bytes();old=Path(status['app_launcher']['path']);old_bytes=old.read_bytes()
        def rejected():
            r=subprocess.run(self.worker_args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=5)
            self.assertNotEqual(r.returncode,0);self.assertIn(b'unresolved guardian journal',r.stderr)
            self.assertEqual(path.read_bytes(),original);self.assertEqual(old.read_bytes(),old_bytes)
        temporary=self.root/'.jobs/guardian.next';temporary.write_bytes(original);temporary.chmod(0o600)
        rejected();self.assertEqual(temporary.read_bytes(),original);temporary.unlink()
        path.chmod(0o644);rejected();path.chmod(0o600)
        linked=self.root/'linked-journal';os.link(path,linked);rejected();linked.unlink()
        backup=self.root/'journal-backup';path.rename(backup);path.symlink_to(backup)
        rejected();self.assertTrue(path.is_symlink());path.unlink();backup.rename(path)
        self.restart();self.assertTrue(self.op('status')['result']['stale_guardian_reconciled'])
    @unittest.skipUnless(os.environ.get('NATIVE_WORKER_FAULT_TEST'), 'fault-injection build required')
    def test_startup_checkpoint_recovery(self):
        for stage in ['namespace','runtime','launcher-created','launcher-partial-copy','launcher-copy','launcher','contained','ready','journal-runtime','journal-contained','journal-ready']:
            with self.subTest(stage=stage):
                self.seq+=1;self.send(f'SHUTDOWN\t{self.seq}');self.receive();self.proc.wait(timeout=5)
                self.token.write_bytes(base64.b64encode(self.secret));self.token.chmod(0o600)
                result=subprocess.run(self.worker_args,env={**os.environ,'COUCHROOT_NATIVE_STARTUP_FAULT':stage},capture_output=True,timeout=5)
                self.assertEqual(result.returncode,86,result.stderr)
                journal=json.loads((self.root/'.jobs/guardian').read_text())
                self.assertEqual(journal['schema'],3)
                old=self.root/'.views'/journal['worker_id']
                self.restart()
                self.assertTrue(self.op('status')['result']['stale_guardian_reconciled'])
                self.assertFalse(old.exists())
                self.start_job('exit 9');self.assertEqual(self.completed()['exit_code'],9)
                self.assertTrue(self.job('job.forget')['ok'])

    def test_legacy_prepared_schema_two_recovery(self):
        _,journal=self.guardian_loss()
        journal['schema']=2;journal.pop('phase')
        (self.root/'.jobs/guardian').write_text(json.dumps(journal))
        self.restart()
        self.assertTrue(self.op('status')['result']['stale_guardian_reconciled'])

    @unittest.skipUnless(os.environ.get('NATIVE_WORKER_FAULT_TEST'), 'fault-injection build required')
    def test_temporary_checkpoint_identity_refusal(self):
        self.seq+=1;self.send(f'SHUTDOWN\t{self.seq}');self.receive();self.proc.wait(timeout=5)
        result=subprocess.run(self.worker_args,env={**os.environ,'COUCHROOT_NATIVE_STARTUP_FAULT':'journal-runtime'},capture_output=True,timeout=5)
        self.assertEqual(result.returncode,86,result.stderr)
        path=self.root/'.jobs/guardian.next';original=path.read_bytes();journal=json.loads(original)
        old=self.root/'.views'/journal['worker_id']
        for key,value in [('phase','ready'),('worker_id','0'*32),('boot_id','different-boot'),('process_start','0'),('pid',journal['pid']+1),('namespace_ino',journal['namespace_ino']+1),('scope_ino',journal['scope_ino']+1)]:
            bad={**journal,key:value};raw=json.dumps(bad).encode();path.write_bytes(raw)
            rejected=subprocess.run(self.worker_args,capture_output=True,timeout=5)
            self.assertNotEqual(rejected.returncode,0)
            self.assertIn(b'unresolved guardian journal',rejected.stderr)
            self.assertEqual(path.read_bytes(),raw);self.assertTrue(old.is_dir())
        path.write_bytes(original);self.restart()
        self.assertFalse(old.exists())
        self.assertTrue(self.op('status')['result']['stale_guardian_reconciled'])

    def test_interrupted_reconciliation_is_idempotent(self):
        status,journal=self.guardian_loss()
        # Model interruption after owned runtime deletion but before journal unlink.
        old=Path(status['app_launcher']['path']);old.unlink();old.parent.rmdir();old.parent.parent.rmdir()
        self.restart()
        self.assertTrue(self.op('status')['result']['stale_guardian_reconciled'])
        self.assertEqual(self.job('job.status')['result']['state'],'interrupted')
    def test_scope_lock_and_unresolved_guardian_refuse_replacement(self):
        other=subprocess.run(self.worker_args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=5)
        self.assertNotEqual(other.returncode,0);self.assertIn(b'exclusive job ownership',other.stderr)
        self.assertTrue(self.op('status')['ok'])
        self.seq+=1;self.send(f'SHUTDOWN\t{self.seq}');self.receive();self.proc.wait(timeout=5)
        marker=self.root/'.jobs/guardian';marker.write_text('unresolved');marker.chmod(0o600)
        other=subprocess.run(self.worker_args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=5)
        self.assertNotEqual(other.returncode,0);self.assertIn(b'unresolved guardian journal',other.stderr)
        self.assertEqual(marker.read_text(),'unresolved')
    def test_launcher_source_integrity_rejection(self):
        self.seq+=1;self.send(f'SHUTDOWN\t{self.seq}');self.receive();self.proc.wait(timeout=5)
        source=self.root/'launcher-source';source.write_bytes(b'invalid'*10)
        for digest in ['0'*64,hashlib.sha256(source.read_bytes()).hexdigest()]:
            args=self.worker_args.copy();args[-1]=digest
            other=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=5)
            self.assertNotEqual(other.returncode,0);self.assertIn(b'launcher source',other.stderr)
            self.assertFalse((self.root/'.jobs/guardian').exists())
        self.assertFalse((self.root/'.views').exists())
    def test_helpers_fail_closed_without_smack_mount_support(self):
        path=self.root/'helper';path.write_bytes(b'not executable');path.chmod(0o600)
        result=self.op('helper.prepare',path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertFalse(result['ok']);self.assertIn('unavailable',result['error'])
        self.assertEqual(path.read_bytes(),b'not executable')
        self.assertFalse(self.op('helper.prepare',path='/bin/true',sha256='0'*64)['ok'])
    def test_foreground_exited_leader_keeps_group_owned(self):
        marker=self.root/'escaped-child'
        cmd=f'(sleep .5; touch {marker}) & exit 0'
        self.seq+=1;self.send(f'EXEC\t{self.seq}\t100\t'+base64.b64encode(cmd.encode()).decode())
        fields=self.receive().split('\t');self.assertEqual(fields[:4],['RESULT',str(self.seq),'124','1'])
        time.sleep(.6);self.assertFalse(marker.exists())
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
