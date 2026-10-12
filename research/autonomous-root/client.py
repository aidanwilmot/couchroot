#!/usr/bin/env python3
"""Certificate-pinned administrator client. No automatic command retries."""
import argparse
import hashlib
import http.client
import json
from pathlib import Path
import ssl
import uuid


def request(config, method, route, body=None):
    context=ssl.create_default_context(cafile=config['server_certificate'])
    context.check_hostname=False # Exact certificate pin below is the identity.
    context.minimum_version=ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(config['client_certificate'],config['client_key'])
    connection=http.client.HTTPSConnection(config['host'],config['port'],context=context,timeout=40)
    try:
        connection.connect()
        if hashlib.sha256(connection.sock.getpeercert(binary_form=True)).hexdigest()!=config['server_sha256']:
            raise RuntimeError('Server certificate pin mismatch; no command submitted')
        connection.request(method,route,body=json.dumps(body) if body is not None else None,
            headers={'Content-Type':'application/json','Connection':'close'})
        response=connection.getresponse();raw=response.read(4*1024*1024+1)
        if len(raw)>4*1024*1024:raise RuntimeError('Oversized response')
        value=json.loads(raw)
        if response.status!=200:raise RuntimeError(json.dumps(value))
        return value
    finally:connection.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',required=True,type=Path)
    parser.add_argument('operation',choices=['status','requests','enable','disable','exec','archive-journal'])
    parser.add_argument('--command-file',type=Path)
    parser.add_argument('--timeout-ms',type=int,default=20000)
    parser.add_argument('--request-id',default=None)
    args=parser.parse_args();config=json.loads(args.config.read_text())
    if args.operation=='exec':
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
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
