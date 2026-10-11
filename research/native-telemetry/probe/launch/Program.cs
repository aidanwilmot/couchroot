// Diagnostic only: a private mount namespace, no production files or credentials.
using System;
using System.IO;
using System.Runtime.InteropServices;
class Launch {
 [DllImport("libc.so.6", SetLastError=true)] static extern int unshare(int flags);
 [DllImport("libc.so.6", SetLastError=true)] static extern int mount(string source,string target,string type,UIntPtr flags,string data);
 [DllImport("libc.so.6", SetLastError=true)] static extern int execv(string path,IntPtr argv);
 static int Main() {
  Console.WriteLine(File.ReadAllText("/proc/self/attr/current"));
  foreach(var line in File.ReadAllLines("/proc/self/status"))if(line.StartsWith("Cap")||line.StartsWith("Uid:")||line.StartsWith("NoNewPrivs:"))Console.WriteLine(line);
  int rc=unshare(0x20000);Console.WriteLine("unshare="+rc+" errno="+Marshal.GetLastWin32Error());if(rc!=0)return 77;
  if(mount(null,"/",null,(UIntPtr)0x44000,null)!=0)return 78;
  foreach(var line in File.ReadAllLines("/proc/self/mountinfo"))if(line.Contains(" shared:"))return 79;
  const string root="/opt/minimal-native-launch-probe";
  if(mount(root,root,null,(UIntPtr)4096,null)!=0)return 80;
  if(mount(null,root,null,(UIntPtr)(4096|32|1),null)!=0)return 81;
  Console.WriteLine("readonly mount prepared");
  var name=Marshal.StringToHGlobalAnsi(root+"/resident");var args=Marshal.AllocHGlobal(IntPtr.Size*2);
  Marshal.WriteIntPtr(args,name);Marshal.WriteIntPtr(args,IntPtr.Size,IntPtr.Zero);
  Console.Out.Flush();execv(root+"/resident",args);
  Console.WriteLine("exec errno="+Marshal.GetLastWin32Error());return 82;
 }
}
