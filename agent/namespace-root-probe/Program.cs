using System;
using System.IO;
using System.Linq;
using System.Diagnostics;
using System.Runtime.InteropServices;
class NamespaceRootProbe {
#if QN90A
 const string ProbeName = "codex-qn90a-root-proof";
#else
 const string ProbeName = "codex-namespace-proof";
#endif
 [DllImport("libc.so.6", SetLastError=true)] static extern int unshare(int flags);
 [DllImport("libc.so.6", SetLastError=true)] static extern int mount(string source,string target,string fs,UIntPtr flags,string data);
 [DllImport("libc.so.6", SetLastError=true)] static extern int umount2(string path,int flags);
 static void Require(string action,int rc){int error=Marshal.GetLastWin32Error();Console.WriteLine(action+" result="+rc+" errno="+(rc<0?error:0));if(rc<0)throw new Exception(action+" failed: "+error);}
 static void RunId(string archive,string label){
  Console.WriteLine("IDENTITY TEST "+label);
  var start=new ProcessStartInfo("/usr/sbin/sdbd-tarlauncher"){UseShellExecute=false,RedirectStandardOutput=true,RedirectStandardError=true};
  foreach(var arg in new[]{"--package_name",ProbeName,"-xzf",archive,"--to-command=/usr/bin/dotnet /home/owner/share/tmp/sdk_tools/"+ProbeName+"/RootIdentity.dll"})start.ArgumentList.Add(arg);
  using(var p=Process.Start(start)){
   // Leave five seconds above the setup operation’s bounded 25-second deadline.
   var stdout=p.StandardOutput.ReadToEndAsync();var stderr=p.StandardError.ReadToEndAsync();
   if(!p.WaitForExit(30000)){p.Kill(true);throw new Exception("helper timeout");}
   string output=stdout.Result;Console.Write(output);Console.Write(stderr.Result);Console.WriteLine("launcher exit="+p.ExitCode);
   string expected=label.StartsWith("baseline")?"Uid:\t5001\t5001\t5001\t5001":"Uid:\t0\t0\t0\t0";
   if(!output.Contains(expected))throw new Exception("unexpected identity; root proof not established");
   if(p.ExitCode!=0)throw new Exception("helper did not complete");
  }
 }
 static int Main(string[] args){
  if(args.Length!=1 && (args.Length!=2 || args[1]!="--setup-archives")) return 2;
  string dir=args[0], archive="/home/owner/share/tmp/sdk_tools/on-demand/"+ProbeName+".tar.gz";
  if(dir!="/home/owner/share/tmp/sdk_tools/"+ProbeName || IntPtr.Size!=4) return 2;
  string original=File.ReadAllText("/etc/passwd");
  var lines=original.Split('\n');int changed=0;
  for(int i=0;i<lines.Length;i++){var cols=lines[i].Split(':');if(cols.Length>=7&&cols[0]=="owner"){if(cols[2]!="5001")throw new Exception("unexpected owner uid");cols[2]="0";cols[3]="0";lines[i]=string.Join(":",cols);changed++;}}
  if(changed!=1)throw new Exception("expected one owner record");
  File.WriteAllText(dir+"/passwd-view",string.Join("\n",lines));
  bool keyMounted=false,passwdMounted=false,archivesMounted=false,sharedMounted=false;
  try{
   Require("unshare private mount namespace",unshare(0x20000));
   Require("make mount propagation recursively private",mount(null,"/",null,new UIntPtr(0x44000),null));
   if(File.ReadAllText("/proc/self/mountinfo").Contains(" shared:"))throw new Exception("shared mounts remain; abort");
   Console.WriteLine("Verified no shared mount propagation in probe namespace.");
   if(args.Length==2){
   // Keep the agent's real directory visible only for exact-name legacy cleanup.
   // New archives live under the SDK-owned stage, never in the shared directory.
   Require("bind original archive directory",mount("/home/owner/share/tmp/sdk_tools/on-demand",dir+"/shared-on-demand",null,new UIntPtr(4096),null));sharedMounted=true;
   Require("bind private setup archives",mount(dir+"/archives","/home/owner/share/tmp/sdk_tools/on-demand",null,new UIntPtr(4096),null));archivesMounted=true;
   }
   Require("bind test public key (probe namespace only)",mount(dir+"/public.pem","/usr/share/sdbd/public.pem",null,new UIntPtr(4096),null));keyMounted=true;
   RunId(archive,"baseline, real owner record");
   Require("bind owner record view (probe namespace only)",mount(dir+"/passwd-view","/etc/passwd",null,new UIntPtr(4096),null));passwdMounted=true;
   RunId(archive,"temporary owner uid 0 record");
   return 0;
  }catch(Exception e){Console.WriteLine("PROBE STOPPED: "+e.Message);return 1;}
  finally{if(passwdMounted)Console.WriteLine("unmount passwd view="+umount2("/etc/passwd",2));if(keyMounted)Console.WriteLine("unmount public key view="+umount2("/usr/share/sdbd/public.pem",2));if(archivesMounted)Console.WriteLine("unmount setup archives="+umount2("/home/owner/share/tmp/sdk_tools/on-demand",2));if(sharedMounted)Console.WriteLine("unmount original archives="+umount2(dir+"/shared-on-demand",2));Console.WriteLine("Namespace probe exiting; no service or shell left running.");}
 }
}
