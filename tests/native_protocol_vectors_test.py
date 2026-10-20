"""Shared vectors through the compiled worker's real greeting and dispatch loop.
All sockets are loopback in a disposable Linux test container; no device access.
"""
import base64
import contextlib
import hashlib
import hmac
import json
import os
from pathlib import Path
import socket
import select
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
V=json.loads((ROOT/'tests/fixtures/root-protocol.json').read_text())


@contextlib.contextmanager
def peer(hello=True,held=False):
    with tempfile.TemporaryDirectory(prefix='protocol-wire-') as tmp:
        root=Path(tmp);root.chmod(0o700)
        secret=bytes.fromhex(V['secret_hex']);nonce=bytes.fromhex(V['nonce_hex'])
        token=root/'token';token.write_bytes(base64.b64encode(secret));token.chmod(0o600)
        launcher=root/'launcher';launcher.write_bytes(Path('/bin/true').read_bytes());launcher.chmod(0o600)
        with socket.socket() as listener:
            listener.bind(('127.0.0.1',0));listener.listen();listener.settimeout(5)
            argv=[os.environ['NATIVE_WORKER'],'127.0.0.1',str(listener.getsockname()[1]),str(token),str(root),str(launcher),hashlib.sha256(launcher.read_bytes()).hexdigest()]
            if held:argv.append('--held-bootstrap')
            process=subprocess.Popen(argv,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            try:
                sock,_=listener.accept()
                with sock,sock.makefile('rb') as stream:
                    sock.settimeout(3)
                    def receive():
                        raw=stream.readline()
                        if not raw:return None
                        payload,mac=raw.rstrip(b'\n').rsplit(b'\t',1)
                        assert mac==hmac.new(secret,nonce+b'\0'+payload,hashlib.sha256).hexdigest().encode()
                        return payload.decode()
                    def send(payload,**options):
                        mac=hmac.new(secret,nonce+b'\0'+payload.encode(),hashlib.sha256).hexdigest()
                        if options.get('uppercase_mac'):mac=mac.upper()
                        if options.get('bad_mac'):mac='0'*64
                        sock.sendall((payload+'\t'+mac+('\r\n' if options.get('crlf') else '\n')).encode())
                    if hello:
                        sock.sendall(b'SAMSUNG-TV-ROOT/1\t'+nonce.hex().encode()+b'\n')
                        assert receive().startswith('AUTH\t')
                    yield sock,send,receive
            finally:
                try:process.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill();process.communicate();raise


@unittest.skipUnless(os.environ.get('NATIVE_WORKER'),'native CI fixture required')
class NativeProtocolVectors(unittest.TestCase):
    def test_real_greeting_rejects_oversize_before_newline(self):
        with peer(hello=False) as (sock,_,receive):
            sock.sendall(b'x'*(V['limits']['preauth_bytes']+1))
            self.assertIsNone(receive(),'oversized unterminated hello was not rejected promptly')

    def test_real_exec_timeout_dispatch(self):
        for held,cases in ((False,V['exec_timeouts']),(True,V['held_exec_timeouts'])):
            for case in cases:
                with self.subTest(held=held,timeout=case['ms']),peer(held=held) as (_,send,receive):
                    send('EXEC\t1\t'+str(case['ms'])+'\t'+base64.b64encode(b'printf ok').decode())
                    result=receive()
                    self.assertEqual(result is not None,case['accepted'])
                    if result:self.assertEqual(result.split('\t')[:5],['RESULT','1','0','0','b2s='])

    def test_real_exec_command_and_output_limits(self):
        size=V['limits']['command_bytes']
        for length in (0,size,size+1):
            with self.subTest(length=length),peer() as (_,send,receive):
                command=(':'+(' '*(length-1))) if length else ''
                send('EXEC\t1\t1000\t'+base64.b64encode(command.encode()).decode())
                result=receive();self.assertEqual(result is not None,0<length<=size)
                if result:self.assertEqual(result.split('\t')[:4],['RESULT','1','0','0'])
        limit=V['limits']['output_bytes']
        with peer() as (_,send,receive):
            command=f'head -c {limit+17} /dev/zero; head -c {limit+17} /dev/zero >&2'
            send('EXEC\t1\t5000\t'+base64.b64encode(command.encode()).decode())
            result=receive().split('\t');self.assertEqual(result[:4],['RESULT','1','0','0'])
            self.assertEqual(base64.b64decode(result[4]),bytes(limit))
            self.assertEqual(base64.b64decode(result[5]),bytes(limit)+V['output_limit_notice'].encode())

    def test_real_session_frames(self):
        for case in V['session_frames']:
            with self.subTest(case=case['name']),peer() as (sock,send,receive):
                send('PING\t1');self.assertTrue(receive().startswith('PONG\t1\t'))
                if 'raw' in case:sock.sendall(case['raw'].encode())
                else:send(case['payload'],**{k:v for k,v in case.items() if k!='payload'})
                self.assertEqual(receive() is not None,case['native'])

    def test_real_binary_chunk_limit(self):
        limit=V['limits']['binary_chunk_bytes']
        for length in (limit,limit+1):
            with self.subTest(length=length),peer() as (sock,send,receive):
                body=b'x'*length
                send(f'OPWRITE\t1\t'+('a'*32)+f'\t0\t{length}\t'+hashlib.sha256(body).hexdigest())
                if length<=limit:
                    sock.sendall(body)
                    self.assertTrue(receive().startswith('OPRESULT\t1\t')) # unknown transfer, valid header/body
                else:self.assertIsNone(receive())

    def test_real_authenticated_line_boundary(self):
        with peer() as (sock,_,receive):
            sock.sendall(b'x'*V['limits']['frame_bytes'])
            self.assertEqual(select.select([sock],[],[],.1)[0],[], 'exact line limit closed before LF')
            sock.sendall(b'x')
            self.assertIsNone(receive())
