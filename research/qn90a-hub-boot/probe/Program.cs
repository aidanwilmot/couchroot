using System;
using System.IO;
using System.Runtime.InteropServices;
class BootProbe {
 [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate bool Create(IntPtr data);
 [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate void Event(IntPtr data);
 [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate void Control(IntPtr control,IntPtr data);
 [StructLayout(LayoutKind.Sequential)] struct Callbacks {public Create create;public Event terminate;public Control control;}
 [DllImport("libappcore-agent.so.1")] static extern int service_app_main(int argc,string[] argv,ref Callbacks callbacks,IntPtr data);
 [DllImport("libappcore-agent.so.1")] static extern void service_app_exit();
 [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Timer(IntPtr data);
 [DllImport("libglib-2.0.so.0")] static extern uint g_timeout_add(uint interval,Timer callback,IntPtr data);
 static Timer timer = _ => {service_app_exit();return 0;};
 static bool Start(IntPtr data) {
  Directory.CreateDirectory("/tmp/minimal-boot-probe");
  File.WriteAllText("/tmp/minimal-boot-probe/status.txt", "boot="+File.ReadAllText("/proc/sys/kernel/random/boot_id")+"uptime="+File.ReadAllText("/proc/uptime"));
  g_timeout_add(1000,timer,IntPtr.Zero);return true;
 }
 static int Main(string[] args) {var c=new Callbacks{create=Start,terminate=_=>{},control=(_,__)=>{}};var a=new string[args.Length+1];a[0]="";args.CopyTo(a,1);int r=service_app_main(a.Length,a,ref c,IntPtr.Zero);GC.KeepAlive(c);return r;}
}
