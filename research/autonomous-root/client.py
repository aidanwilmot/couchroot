#!/usr/bin/env python3
"""Certificate-pinned administrator client. No automatic command retries."""
import argparse
import hashlib
import http.client
import json
from pathlib import Path
import ssl
import uuid
import os
import time
import sys


class OperationError(RuntimeError):
    def __init__(self, value):
        self.result = value
        self.outcome = value.get('outcome', 'rejected')
        super().__init__(json.dumps(value))


def request(config, method, route, body=None, *, binary=None, raw_response=False, timeout=40):
    context=ssl.create_default_context(cafile=config['server_certificate'])
    context.check_hostname=False # Exact certificate pin below is the identity.
    context.minimum_version=ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(config['client_certificate'],config['client_key'])
    connection=http.client.HTTPSConnection(config['host'],config['port'],context=context,timeout=timeout)
    try:
        connection.connect()
        if hashlib.sha256(connection.sock.getpeercert(binary_form=True)).hexdigest()!=config['server_sha256']:
            raise RuntimeError('Server certificate pin mismatch; no command submitted')
        headers={'Content-Type':'application/json','Connection':'close'}
        payload=json.dumps(body) if body is not None else None
        if binary is not None:
            headers.update({'Content-Type':'application/octet-stream','X-Operation':json.dumps(body)})
            payload=binary
        connection.request(method,route,body=payload,headers=headers)
        response=connection.getresponse();raw=response.read(4*1024*1024+1)
        if len(raw)>4*1024*1024:raise RuntimeError('Oversized response')
        if response.status!=200:raise OperationError(json.loads(raw))
        if raw_response:
            if len(raw)>1024*1024 or hashlib.sha256(raw).hexdigest()!=response.getheader('X-SHA256'):
                raise RuntimeError('Download chunk digest mismatch')
            return raw
        return json.loads(raw)
    finally:connection.close()


def operation(config, value, *, binary=None):
    envelope=dict(id=str(uuid.uuid4()), operation=value)
    route='/v1/files/write' if binary is not None else '/v1/files/read' if value['op']=='file.read' else '/v1/op'
    return request(config,'POST',route,envelope,binary=binary,raw_response=value['op']=='file.read')


def file_digest(stream):
    digest=hashlib.sha256()
    while True:
        data=stream.read(1024*1024)
        if not data:break
        digest.update(data)
    stream.seek(0)
    return digest.hexdigest()


def upload(config, source, target, expected_sha256='absent', transfer_id=None):
    with Path(source).open('rb') as stream:
        digest=file_digest(stream);size=os.fstat(stream.fileno()).st_size
        if transfer_id:
            session=operation(config,dict(op='file.status',transfer_id=transfer_id))
            if not session.get('upload') or any(session.get(k)!=v for k,v in dict(path=target,size=size,sha256=digest,expected_sha256=expected_sha256).items()):
                raise RuntimeError('Resume source or precondition differs from the existing upload')
        else:session=operation(config,dict(op='file.begin',path=target,size=size,sha256=digest,expected_sha256=expected_sha256))
        transfer=session['transfer_id'];offset=session.get('offset',0)
        if offset<0 or offset>size:raise RuntimeError('Invalid resume offset')
        stream.seek(offset)
        print('Upload transfer: '+transfer,file=sys.stderr)
        while True:
            data=stream.read(session['chunk_bytes'])
            if not data:break
            result=operation(config,dict(op='file.write',transfer_id=transfer,offset=offset,sha256=hashlib.sha256(data).hexdigest()),binary=data)
            offset+=len(data)
            if result.get('offset')!=offset:raise RuntimeError('Upload offset mismatch; inspect transfer status')
        return operation(config,dict(op='file.commit',transfer_id=transfer))


def download(config, source, target):
    target=Path(target)
    if target.exists():raise FileExistsError(target)
    session=operation(config,dict(op='file.open',path=source));transfer=session['transfer_id']
    temporary=target.with_name(target.name+'.part-'+uuid.uuid4().hex)
    print('Download transfer: '+transfer,file=sys.stderr)
    try:
        digest=hashlib.sha256();offset=0
        with temporary.open('xb') as stream:
            os.chmod(temporary,0o600)
            while offset<session['size']:
                data=operation(config,dict(op='file.read',transfer_id=transfer,offset=offset,length=min(session['chunk_bytes'],session['size']-offset)))
                if not data or offset+len(data)>session['size']:raise RuntimeError('Invalid download length')
                stream.write(data);digest.update(data);offset+=len(data)
            stream.flush();os.fsync(stream.fileno())
        if digest.hexdigest()!=session['sha256']:raise RuntimeError('Downloaded file changed or digest mismatch')
        os.link(temporary,target)  # Atomic publication without overwriting a local file.
        temporary.unlink()
    except Exception:
        # Preserve partial bytes and transfer ID for explicit diagnosis/resumption.
        print('Partial download: '+str(temporary),file=sys.stderr)
        raise
    operation(config,dict(op='file.close',transfer_id=transfer))
    return dict(path=str(target),size=offset,sha256=digest.hexdigest())


def wait_ready(config, previous_boot_id=None, timeout=180):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        try:
            status=request(config,'GET','/v1/status',timeout=min(40,max(0.001,deadline-time.monotonic())))
            boot=status.get('boot_id')
            if boot and status.get('worker_ready') and status.get('identity',{}).get('uid')==0 and (previous_boot_id is None or boot!=previous_boot_id):return status
        except (OSError,TimeoutError):pass
        time.sleep(min(1,max(0,deadline-time.monotonic())))
    raise TimeoutError('No ready root worker on the requested boot before the deadline')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',required=True,type=Path)
    parser.add_argument('operation',choices=['status','requests','enable','disable','exec','archive-journal','upload','download','op','wait-ready','app-exec','job-start','job-status','job-tail','job-cancel','job-forget','helper-prepare','helper-release'])
    parser.add_argument('--command-file',type=Path)
    parser.add_argument('--timeout-ms',type=int,default=20000)
    parser.add_argument('--request-id',default=None)
    parser.add_argument('--transfer-id');parser.add_argument('--job-id');parser.add_argument('--helper-id')
    parser.add_argument('--sha256');parser.add_argument('--profile',choices=['root','app'],default='root')
    parser.add_argument('--stdout-cursor',type=int,default=0);parser.add_argument('--stderr-cursor',type=int,default=0)
    parser.add_argument('--source');parser.add_argument('--target')
    parser.add_argument('--expected-sha256',default='absent')
    parser.add_argument('--operation-file',type=Path)
    parser.add_argument('--previous-boot-id');parser.add_argument('--wait-seconds',type=float,default=180)
    args=parser.parse_args();config=json.loads(args.config.read_text())
    if args.operation in ('upload','download'):
        if not args.source or not args.target:parser.error('--source and --target required')
        result=upload(config,args.source,args.target,args.expected_sha256,args.transfer_id) if args.operation=='upload' else download(config,args.source,args.target)
    elif args.operation=='app-exec' or args.operation.startswith('job-'):
        name='app.exec' if args.operation=='app-exec' else 'job.'+args.operation[4:].replace('tail','output')
        value=dict(op=name)
        if name.startswith('job.'):
            if not args.job_id and name!='job.start':parser.error('--job-id required')
            value['id']=args.job_id or str(uuid.uuid4())
        if name in ('app.exec','job.start'):
            if not args.command_file:parser.error('--command-file required')
            value.update(command=args.command_file.read_text(),timeout_ms=args.timeout_ms)
            if name=='job.start':value['profile']=args.profile
        if name=='job.output':value.update(stdout_cursor=args.stdout_cursor,stderr_cursor=args.stderr_cursor)
        result=operation(config,value)
    elif args.operation.startswith('helper-'):
        if args.operation=='helper-prepare':
            if not args.source or not args.sha256:parser.error('--source and --sha256 required')
            value=dict(op='helper.prepare',path=args.source,sha256=args.sha256)
        else:
            if not args.helper_id:parser.error('--helper-id required')
            value=dict(op='helper.release',helper_id=args.helper_id)
        result=operation(config,value)
    elif args.operation=='op':
        if not args.operation_file:parser.error('--operation-file required')
        result=operation(config,json.loads(args.operation_file.read_text()))
    elif args.operation=='wait-ready':result=wait_ready(config,args.previous_boot_id,args.wait_seconds)
    elif args.operation=='exec':
        if not args.command_file:parser.error('exec requires --command-file')
        value=dict(id=args.request_id or str(uuid.uuid4()),command=args.command_file.read_text(),timeout_ms=args.timeout_ms)
        print('Request ID: '+value['id'],file=__import__('sys').stderr)
        result=request(config,'POST','/v1/exec',value)
    elif args.operation=='archive-journal':
        snapshot=request(config,'GET','/v1/requests')
        if 'sha256' not in snapshot:raise RuntimeError('Installed agent does not support journal archiving')
        result=request(config,'POST','/v1/journal/archive',{'expected_sha256':snapshot['sha256']})
    elif args.operation in ('enable','disable'):result=request(config,'POST','/v1/'+args.operation,{})
    else:result=request(config,'GET','/v1/'+args.operation)
    if isinstance(result,bytes):
        if not args.target:parser.error('Binary operation requires --target for the returned range')
        with Path(args.target).open('xb') as output:output.write(result)
    else:print(json.dumps(result,indent=2))

if __name__=='__main__':main()
