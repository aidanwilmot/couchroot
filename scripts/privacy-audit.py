#!/usr/bin/env python3
"""Value-redacted heuristic scan of tracked files or every reachable Git blob.

This is a review aid, not a guarantee that a repository is safe to disclose.
Never print matched values, commit messages, author addresses or blob contents.
"""
import argparse
import collections
import json
from pathlib import Path
import re
import subprocess

RULES = {
 'private-key': rb'-----BEGIN (?:RSA |EC |OPENSSH |DSA |ENCRYPTED )?PRIVATE KEY-----',
 'credential-literal': rb'(?i)(?:password|token|secret)["\x27]?\s*[:=]\s*["\x27][a-zA-Z0-9_+/=-]{24,}',
 'personal-network': rb'\b(?:10(?:\.[0-9]{1,3}){3}|192\.168(?:\.[0-9]{1,3}){2})\b',
 'personal-home': rb'/Users/[a-zA-Z][^/\s"\x27]*|/home/(?!owner/|root/|user/)[a-zA-Z][^/\s"\x27]*/',
 'mac-address': rb'(?i)\b(?:[0-9a-f]{2}:){5}[0-9a-f]{2}\b',
 'device-identifier': rb'(?i)(?:duid|serialnumber|serial_number|udn)["\x27]?\s*[:=]\s*["\x27][^"\x27]{8,}',
 'historical-uuid': rb'\b(?!00000000-)[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}\b',
 'email': rb'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b',
}
SENSITIVE_SUFFIXES = {'.p12','.pfx','.pem','.key','.wgt','.tpk','.db','.sqlite','.pcap','.crt','.cer','.der','.so','.dylib','.zip'}


def git(*args):
    return subprocess.check_output(['git',*args])


def scan(history=False):
    findings=[]; blobs=0
    if history:
        records=[]
        for line in git('rev-list','--objects','--all').decode().splitlines():
            oid,_,path=line.partition(' ')
            if path: records.append((oid,path))
        process=subprocess.Popen(['git','cat-file','--batch'],stdin=subprocess.PIPE,stdout=subprocess.PIPE)
        def sources():
            try:
                for oid,path in records:
                    process.stdin.write((oid+'\n').encode());process.stdin.flush()
                    header=process.stdout.readline().split();size=int(header[2])
                    content=process.stdout.read(size);process.stdout.read(1)
                    if header[1]==b'blob':yield path,oid,content
            finally:
                process.stdin.close();process.stdout.close();process.wait()
        contents=sources()
    else:
        contents=((path,'working-tree',Path(path).read_bytes()) for path in git('ls-files','-z').decode().split('\0') if path and Path(path).is_file())
    for path,oid,data in contents:
        blobs+=1
        for category,rule in RULES.items():
            matches=re.findall(rule,data)
            # Reserved .invalid email-like strings are deliberate parser fixtures.
            if category == 'email':
                matches=[value for value in matches if not value.lower().endswith(b'.invalid')]
            count=len(matches)
            if count:findings.append(dict(category=category,path=path,object=oid,count=count))
        if Path(path).suffix.lower() in SENSITIVE_SUFFIXES:
            findings.append(dict(category='sensitive-artifact',path=path,object=oid,count=1))
    if history:
        metadata=git('log','--all','--format=%H%x00%an%x00%ae%x00%cn%x00%ce%x00%B')
        for category,rule in RULES.items():
            count=len(re.findall(rule,metadata))
            if count:findings.append(dict(category=category,path='(commit metadata)',object='all reachable commits',count=count))
    return dict(scope='reachable-history' if history else 'tracked-working-tree',blobs=blobs,
                categories=dict(collections.Counter(row['category'] for row in findings)),findings=findings)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--history',action='store_true');parser.add_argument('--check',action='store_true')
    args=parser.parse_args();report=scan(args.history);print(json.dumps(report,indent=2))
    raise SystemExit(1 if args.check and report['findings'] else 0)
