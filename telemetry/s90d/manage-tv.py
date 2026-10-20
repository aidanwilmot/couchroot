#!/usr/bin/env python3
"""Profile-guarded install/update/status/rollback for the shared collector."""
import argparse, hashlib, importlib.util, json, os, shlex, subprocess, sys, tempfile
from pathlib import Path
from profiles import load as load_profiles
R=Path(__file__).resolve().parent; REPO=R.parents[1]
P=Path.home()/'.local/share/samsung-tv-research'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 raise SystemExit('Retired: use ./tv-setup plan/apply/verify --device DEVICE --components hub,telemetry; recovery uses ./tv-setup rollback --device DEVICE --run RUN_ID. See docs/guides/telemetry.md.')

def root_operation(identity,script,timeout_seconds=10):
 if type(timeout_seconds) is not int or not 1 <= timeout_seconds <= 25: raise ValueError("Root operation deadline must be 1..25 seconds")
 with tempfile.TemporaryDirectory(prefix='telemetry-op-') as tmp:
  tmp=Path(tmp)
  if identity=='s90d':
   path=tmp/'operation.sh';path.write_text(script);subprocess.run(['python3',str(R/'tv-op.py'),str(path)],check=True)
  else:
   # The existing runner provides bounded, private-namespace root and checks cleanup.
   code='''using System;using System.IO;using System.Diagnostics;using System.Runtime.InteropServices;
class RootIdentity {
[DllImport("libc.so.6")]static extern uint getuid();
static int Main(){foreach(string l in File.ReadLines("/proc/self/status"))if(l.StartsWith("Uid:"))Console.WriteLine(l);if(getuid()!=0)return 0;
var p=new ProcessStartInfo("/bin/sh"){UseShellExecute=false,RedirectStandardOutput=true,RedirectStandardError=true};p.ArgumentList.Add("-c");p.ArgumentList.Add(System.Text.Encoding.UTF8.GetString(Convert.FromBase64String("SCRIPT")));
using(var c=Process.Start(p)){var o=c.StandardOutput.ReadToEndAsync();var e=c.StandardError.ReadToEndAsync();if(!c.WaitForExit(10000)){c.Kill(true);return 9;}Console.Write(o.Result);Console.Write(e.Result);return c.ExitCode;}}
}'''
   import base64
   (tmp/'Program.cs').write_text(code.replace('SCRIPT',base64.b64encode(script.encode()).decode()).replace("WaitForExit(10000)","WaitForExit("+str(timeout_seconds*1000)+")"))
   (tmp/'RootIdentity.csproj').write_text('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><TargetFramework>netcoreapp3.1</TargetFramework><OutputType>Exe</OutputType><UseAppHost>false</UseAppHost><CheckEolTargetFramework>false</CheckEolTargetFramework></PropertyGroup></Project>')
   spec=importlib.util.spec_from_file_location('qn_root',REPO/'tools/qn90a/root-check.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
   profile=load_profiles()[identity]
   cfg=dict(tv_host=profile['host'],expected_model=profile['model'],expected_platform=profile['platform'])
   mod.run('telemetry',telemetry_project=tmp,telemetry_config=cfg)
if __name__=='__main__':main()
