using System;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
class Probe {
 [DllImport("libc.so.6")] static extern int setgroups(UIntPtr n,IntPtr groups);
 [DllImport("libc.so.6")] static extern int setgid(uint gid);
 [DllImport("libc.so.6")] static extern int setuid(uint uid);
 static int Run(string cmd,params string[] args){var s=new ProcessStartInfo(cmd){UseShellExecute=false};foreach(var a in args)s.ArgumentList.Add(a);using(var p=Process.Start(s)){if(!p.WaitForExit(10000)){p.Kill();p.WaitForExit();return 124;}Console.WriteLine("command_exit="+p.ExitCode);return p.ExitCode;}}
 static int Main(string[] args) {
  if(setgroups(UIntPtr.Zero,IntPtr.Zero)!=0||setgid(100)!=0||setuid(5001)!=0)return 77;
  Environment.SetEnvironmentVariable("XDG_RUNTIME_DIR","/run/user/5001");
  Environment.SetEnvironmentVariable("DBUS_SESSION_BUS_ADDRESS","kernel:path=/sys/fs/kdbus/5001-user/bus");
  Console.WriteLine(File.ReadAllText("/proc/self/status").Split("Uid:")[1].Split('\n')[0]);Console.WriteLine(File.ReadAllText("/proc/self/attr/current"));
  if(args.Length==1 && args[0]=="--launch") {
   string launchUnit="minimal-native-launch-probe.service";
   int start=Run("/usr/bin/systemd-run","--user","--unit="+launchUnit,"--property=StandardOutput=file:/tmp/minimal-native-launch-probe.txt","--property=RuntimeMaxSec=10s","--property=TimeoutStopSec=2s","--property=RemainAfterExit=yes","/usr/bin/dotnet","/opt/minimal-native-launch-probe/Launch.dll");
   System.Threading.Thread.Sleep(1500);
   Run("/usr/bin/systemctl","--user","show",launchUnit,"-p","MainPID","-p","ActiveState","-p","Result","-p","ExecMainStatus");
   Run("/usr/bin/systemctl","--user","stop",launchUnit);Run("/usr/bin/systemctl","--user","reset-failed",launchUnit);
   return start;
  }
  if(args.Length==2 && args[0]=="--unit-readonly") {
   string name="minimal-native-ro-user-20260921.service";
   int start=Run("/usr/bin/systemd-run","--user","--unit="+name,"--property=BindReadOnlyPaths="+Path.GetDirectoryName(args[1]),"--property=SuccessExitStatus=42","--property=RuntimeMaxSec=5s","--property=TimeoutStopSec=2s","--property=RemainAfterExit=yes",args[1]);
   System.Threading.Thread.Sleep(500);
   Run("/usr/bin/systemctl","--user","show",name,"-p","LoadState","-p","ActiveState","-p","Result","-p","ExecMainCode","-p","ExecMainStatus","-p","BindReadOnlyPaths");
   Run("/usr/bin/systemctl","--user","stop",name);Run("/usr/bin/systemctl","--user","reset-failed",name);
   return start;
  }
  if(args.Length==2 && args[0]=="--exec") {
   try {return Run(args[1]);} catch(System.ComponentModel.Win32Exception e){Console.WriteLine("DIRECT_EXEC_ERRNO="+e.NativeErrorCode);return 78;}
  }
  if(args.Length!=1)return 64;
  if(args[0]=="--direct") {
   try {return Run("/opt/usr/apps/MiniNativeProbe/bin/probe");}
   catch(System.ComponentModel.Win32Exception e){Console.WriteLine("DIRECT_EXEC_ERRNO="+e.NativeErrorCode+" "+e.Message);return 78;}
  }
  string unit="minimal-native-probe-20260921.service";
  int rc=Run("/usr/bin/systemd-run","--user","--unit="+unit,"--property=RuntimeMaxSec=5s","--property=TimeoutStopSec=2s","--property=RemainAfterExit=yes",args[0]);
  System.Threading.Thread.Sleep(500);
  Run("/usr/bin/systemctl","--user","show",unit,"-p","LoadState","-p","ActiveState","-p","Result","-p","ExecMainCode","-p","ExecMainStatus","-p","FragmentPath");
  Run("/usr/bin/systemctl","--user","stop",unit);Run("/usr/bin/systemctl","--user","reset-failed",unit);
  return rc;
 }
}
