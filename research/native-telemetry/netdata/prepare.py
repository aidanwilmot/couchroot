#!/usr/bin/env python3
"""Download, verify and extract the pinned upstream ELF; never run the installer."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import urllib.request


def digest(path):
    with path.open('rb') as source:
        result=hashlib.sha256()
        for chunk in iter(lambda:source.read(1024*1024),b''):result.update(chunk)
        return result.hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True,help='Private build directory outside the checkout')
    parser.add_argument('--strip',default='arm-linux-gnueabi-strip')
    args=parser.parse_args();output=args.output.expanduser().resolve()
    source=Path(__file__).resolve().parent
    if output.is_relative_to(source.parents[2]):
        parser.error('Keep upstream archives and binaries outside the source checkout')
    output.mkdir(parents=True,exist_ok=True,mode=0o700)
    pin=json.loads((source/'upstream.json').read_text())
    archive=output/'netdata-armv7l-v2.11.1.gz.run'
    if not archive.exists():
        temporary=archive.with_suffix('.partial')
        with urllib.request.urlopen(pin['url'],timeout=60) as response, temporary.open('wb') as target:
            shutil.copyfileobj(response,target)
        if digest(temporary)!=pin['archive_sha256']:raise SystemExit('Upstream archive checksum mismatch')
        temporary.replace(archive)
    if digest(archive)!=pin['archive_sha256']:raise SystemExit('Upstream archive checksum mismatch')
    binary=output/'netdata-arm'
    with archive.open('rb') as packed:
        header=b''.join(packed.readline() for _ in range(200))
        match=re.search(rb'^skip="([0-9]+)"$',header,re.M)
        if not match:raise SystemExit('Unexpected makeself archive header')
        packed.seek(0)
        for _ in range(int(match[1])):packed.readline()
        with tarfile.open(fileobj=packed,mode='r|gz') as files:
            for member in files:
                if member.name!='./bin/srv/netdata':continue
                if not member.isfile() or member.size>200_000_000:raise SystemExit('Unexpected ELF member')
                with files.extractfile(member) as elf,binary.open('wb') as target:shutil.copyfileobj(elf,target)
                break
            else:raise SystemExit('ELF member not found')
    subprocess.run([args.strip,str(binary)],check=True)
    if digest(binary)!=pin['stripped_elf_sha256']:raise SystemExit('Stripped ELF differs from reviewed build; do not deploy')
    print(binary)


if __name__=='__main__':main()
