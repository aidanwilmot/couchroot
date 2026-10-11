"""Build an opt-in trace variant without changing the normal screensaver helper."""
from pathlib import Path
import hashlib
import subprocess
root=Path(__file__).resolve().parent
subprocess.run(['dotnet','build',str(root/'host'),'-c','Release','--nologo'],check=True)
digest=hashlib.sha256((root/'host/bin/Release/net6.0/Recorder.dll').read_bytes()).hexdigest()
out=root/'bin/helper';out.mkdir(parents=True,exist_ok=True)
source=(root.parent/'system-screensaver/boot/Program.cs').read_text()
source=source.replace('static int Main() {','static int Main() {\n        BootTrace.Start();\n        BootTrace.Mark("helper-entry");',1)
source=source.replace('using var process = Process.Start(', 'BootTrace.Mark("diagnostic-start");\n            using var process = Process.Start(',1)
source=source.replace('diagnosticStatus = process.ExitCode;', 'diagnosticStatus = process.ExitCode;\n            BootTrace.Mark("diagnostic-end");',1)
source=source.replace('try { Apply(Log); }','try { BootTrace.Mark("overlay-start"); Apply(Log); BootTrace.Mark("overlay-end"); }',1)
source=source.replace('return diagnosticStatus;', 'BootTrace.Mark("helper-work-complete");\n        return diagnosticStatus;',1)
(out/'Program.cs').write_text(source)
(out/'Trace.cs').write_text('''using System;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Security.Cryptography;
using System.Threading;
static class BootTrace {
 static bool enabled;
 static readonly object Gate = new object();
 static string log;
 public static void Mark(string marker) {
  if(!enabled)return;
  try { lock(Gate) File.AppendAllText(log, (Stopwatch.GetTimestamp()/(double)Stopwatch.Frequency).ToString("F6",System.Globalization.CultureInfo.InvariantCulture)+" "+marker+"\\n"); } catch {}
 }
 public static void Start() {
  try {
   const string root="/opt/boot-inventory";
   if(!File.Exists(root+"/enabled") || new DirectoryInfo(root).LinkTarget!=null || new FileInfo(root+"/enabled").LinkTarget!=null)return;
   if(Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(root+"/Recorder.dll"))).ToLowerInvariant()!="DIGEST")return;
   log=root+"/helper.log";
   if(File.Exists(log)&&new FileInfo(log).LinkTarget!=null)return;
   File.WriteAllText(log,File.ReadAllText("/proc/sys/kernel/random/boot_id").Trim()+"\\n"); enabled=true;
   // Type=simple is active at process start. A foreground trace thread keeps
   // this diagnostic variant alive for its bounded capture, not boot ordering.
   var t=new Thread(()=>{try { Mark("recorder-thread-entry"); var a=Assembly.LoadFrom(root+"/Recorder.dll"); a.GetType("Recorder").GetMethod("Run").Invoke(null,new object[]{new string[]{"180"}}); Mark("recorder-thread-exit"); }catch(Exception e){Mark("recorder-error "+e.GetType().Name);}});
   t.Name="BootInventory";t.IsBackground=false;t.Start();
  } catch { enabled=false; }
 }
}
'''.replace('DIGEST',digest))
(out/'Boot.csproj').write_text((root.parent/'system-screensaver/boot/Boot.csproj').read_text())
subprocess.run(['dotnet','build',str(out/'Boot.csproj'),'-c','Release','--nologo'],check=True)
print('Recorder',digest)
print('Helper',hashlib.sha256((out/'bin/Release/net6.0/Boot.dll').read_bytes()).hexdigest())
