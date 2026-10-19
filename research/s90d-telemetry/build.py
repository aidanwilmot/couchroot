"""Build collector plus additive saver/splash/telemetry boot helper."""
import hashlib
from pathlib import Path
import subprocess
root=Path(__file__).resolve().parent
subprocess.run(['dotnet','build',str(root.parents[1]/'telemetry/s90d-collector'),'-c','Release','--nologo'],check=True)
artifact=root.parents[1]/'telemetry/s90d-collector/bin/Release/net6.0/Telemetry.dll'
digest=hashlib.sha256(artifact.read_bytes()).hexdigest()
out=root/'bin/helper';out.mkdir(parents=True,exist_ok=True)
base=root.parent/'system-screensaver/boot'
source=(base/'Program.cs').read_text()
assert source.count('static int Main() {')==1 and source.count('return diagnosticStatus;')==1
source=source.replace('static int Main() {','static int Main() {\n        Splash.Start();')
source=source.replace('return diagnosticStatus;','Splash.Finish();\n        TelemetryBoot.Start();\n        return diagnosticStatus;')
(out/'Program.cs').write_text(source)
(out/'Splash.cs').write_text((root.parent/'s90d-splash/Splash.cs').read_text())
(out/'Boot.csproj').write_text((base/'Boot.csproj').read_text())
(out/'TelemetryBoot.cs').write_text('''using System;
using System.IO;
using System.Reflection;
using System.Security.Cryptography;
using System.Threading;
static class TelemetryBoot {
 public static void Start() {
  try {
   const string root="/opt/minimal-telemetry";
   if(!File.Exists(root+"/enabled") || new DirectoryInfo(root).LinkTarget!=null)return;
   if(Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(root+"/Telemetry.dll"))).ToLowerInvariant()!="DIGEST")return;
   var thread=new Thread(()=>{try { Assembly.LoadFrom(root+"/Telemetry.dll").GetType("Telemetry").GetMethod("Run").Invoke(null,null); }catch { Console.Error.WriteLine("Telemetry unavailable"); }});
   // AT-HUB is Type=simple: this optional resident thread adds no boot dependency.
   thread.IsBackground=false;thread.Name="TVTelemetry";thread.Start();
  }catch { Console.Error.WriteLine("Telemetry startup skipped"); }
 }
}
'''.replace('DIGEST',digest))
subprocess.run(['dotnet','build',str(out/'Boot.csproj'),'-c','Release','--nologo'],check=True)
print('Collector SHA256',digest)
print('Boot SHA256',hashlib.sha256((out/'bin/Release/net6.0/Boot.dll').read_bytes()).hexdigest())
