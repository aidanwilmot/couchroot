using System;
using System.IO;
using System.Diagnostics;
using System.Text.Json;
using System.Runtime.InteropServices;
// Tizen only permits a service launch from its own package. This normal UI
// entrypoint creates no window, forwards a verified Hub request, then exits.
class Bootstrap {
 static readonly Stopwatch Started=Stopwatch.StartNew();
 static bool accepted;
 [DllImport("libc.so.6")] static extern int chmod(string path,uint mode);
 static void Status() {
  try { const string root="/tmp/minimal-telemetry-relay";if(Directory.Exists(root)&&(File.GetAttributes(root)&FileAttributes.ReparsePoint)!=0)return;Directory.CreateDirectory(root);chmod(root,448);using(var p=Process.GetCurrentProcess()){File.WriteAllText(root+"/status.new",JsonSerializer.Serialize(new{at=DateTime.UtcNow.ToString("O"),elapsed_ms=Started.ElapsedMilliseconds,cpu_seconds=p.TotalProcessorTime.TotalSeconds,rss_bytes=p.WorkingSet64,accepted}));File.Move(root+"/status.new",root+"/status.json",true);} } catch {}
 }
 [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate bool Create(IntPtr data);
 [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate void Event(IntPtr data);
 [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate void Control(IntPtr control,IntPtr data);
 [StructLayout(LayoutKind.Sequential)] struct Callbacks { public Create create;public Event terminate,pause,resume;public Control control; }
 [DllImport("libcapi-appfw-application.so.0")] static extern int ui_app_main(int argc,string[] argv,ref Callbacks callbacks,IntPtr data);
 [DllImport("libcapi-appfw-application.so.0")] static extern void ui_app_exit();
 [DllImport("libcapi-appfw-app-control.so.0")] static extern int app_control_get_caller(IntPtr control,out IntPtr caller);
 [DllImport("libcapi-appfw-app-control.so.0")] static extern int app_control_set_app_id(IntPtr control,string id);
 [DllImport("libcapi-appfw-app-control.so.0")] static extern int app_control_send_launch_request(IntPtr control,IntPtr callback,IntPtr data);
 [DllImport("libcapi-appfw-app-control.so.0")] static extern int app_control_create(out IntPtr control);
 [DllImport("libcapi-appfw-app-control.so.0")] static extern int app_control_destroy(IntPtr control);
 [DllImport("libcapi-appfw-app-control.so.0")] static extern int app_control_set_operation(IntPtr control,string op);
 [DllImport("libcapi-appfw-app-control.so.0")] static extern int app_control_get_extra_data(IntPtr control,string key,out IntPtr value);
 [DllImport("libcapi-appfw-app-control.so.0")] static extern int app_control_get_extra_data_array(IntPtr control,string key,out IntPtr values,out int count);
 [DllImport("libcapi-appfw-app-control.so.0")] static extern int app_control_add_extra_data_array(IntPtr control,string key,string[] values,int count);
 [DllImport("libc.so.6")] static extern void free(IntPtr pointer);
 static void Launch(IntPtr control,IntPtr data) {
  try {
   IntPtr caller;
   if(app_control_get_caller(control,out caller)!=0)return;
   string id;try{id=Marshal.PtrToStringAnsi(caller);}finally{free(caller);}
   if(id!="MiniHub001.Hub")return;
   IntPtr request;int create=app_control_create(out request);if(create!=0)return;
   try {
    int setid=app_control_set_app_id(request,"MiniTelemetry.Service"),setop=app_control_set_operation(request,"http://tizen.org/appcontrol/operation/default");if(setid!=0||setop!=0)return;
    foreach(var key in new[]{"telemetry.enabled","telemetry.receiver_url"}) {
     IntPtr values;int count;int rc1=app_control_get_extra_data_array(control,key,out values,out count);if(rc1!=0){IntPtr scalar;int rc2=app_control_get_extra_data(control,key,out scalar);if(rc2!=0)return;try{string v=Marshal.PtrToStringAnsi(scalar);if(v.Length>512)return;app_control_add_extra_data_array(request,key,new[]{v},1);}finally{free(scalar);}continue;}
     try { if(count!=1)return;string value=Marshal.PtrToStringAnsi(Marshal.ReadIntPtr(values));if(value.Length>512)return;if(app_control_add_extra_data_array(request,key,new[]{value},1)!=0)return; }
     finally {for(int i=0;i<count;i++)free(Marshal.ReadIntPtr(values,i*IntPtr.Size));free(values);}
    }
    int rc=app_control_send_launch_request(request,IntPtr.Zero,IntPtr.Zero);
    accepted=rc==0;if(rc!=0)Console.Error.WriteLine("Telemetry launch unavailable");
   } finally {app_control_destroy(request);}
  } catch { Console.Error.WriteLine("Telemetry launch unavailable"); }
  finally { Status();ui_app_exit(); }
 }
 static int Main(string[] args) {
  var callbacks=new Callbacks{create=_=>true,terminate=_=>{},pause=_=>{},resume=_=>{},control=Launch};
  var argv=new string[args.Length+1];argv[0]=string.Empty;args.CopyTo(argv,1);
  int result=ui_app_main(argv.Length,argv,ref callbacks,IntPtr.Zero);GC.KeepAlive(callbacks);return result;
 }
}
