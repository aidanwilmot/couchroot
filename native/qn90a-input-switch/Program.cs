using System;
using System.IO;
using System.Runtime.InteropServices;
using System.Threading;

// Normally signed, no-window app. Hub launches it with one allowlisted HDMI input;
// it asks the TV's source service to switch, replies with the outcome and exits.
class InputSwitch {
 [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate bool Create(IntPtr data);
 [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate void Event(IntPtr data);
 [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate void Control(IntPtr control,IntPtr data);
 [StructLayout(LayoutKind.Sequential)] struct Callbacks {public Create create; public Event terminate,pause,resume;public Control control;}
 [DllImport("libcapi-appfw-application.so.0")] static extern int ui_app_main(int argc,string[] argv,ref Callbacks callbacks,IntPtr data);
 [DllImport("libcapi-appfw-application.so.0")] static extern void ui_app_exit();
 [DllImport("libcapi-appfw-app-control.so.0")] static extern int app_control_get_extra_data(IntPtr control,string key,out IntPtr value);
 [DllImport("libcapi-appfw-app-control.so.0")] static extern int app_control_create(out IntPtr control);
 [DllImport("libcapi-appfw-app-control.so.0")] static extern int app_control_destroy(IntPtr control);
 [DllImport("libcapi-appfw-app-control.so.0")] static extern int app_control_add_extra_data(IntPtr control,string key,string value);
 [DllImport("libcapi-appfw-app-control.so.0")] static extern int app_control_reply_to_launch_request(IntPtr reply,IntPtr request,int result);
 [DllImport("/usr/lib/libsource-api.so")] static extern int connect_source(int type);
 [DllImport("libvconf.so.0")] static extern int vconf_get_int(string key,out int value);
 [DllImport("libc.so.6")] static extern void free(IntPtr p);
 const int Succeeded=0,Failed=-1;
 static readonly Control control=Handle;
 // HDMI1-4 are source types 13-16 on this firmware's libsource-api.
 static int Type(string name) {switch(name){case "HDMI1":return 13;case "HDMI2":return 14;case "HDMI3":return 15;case "HDMI4":return 16;default:return 0;}}
 static string Extra(IntPtr request,string key) {IntPtr p;if(app_control_get_extra_data(request,key,out p)!=0||p==IntPtr.Zero)return null;try{return Marshal.PtrToStringAnsi(p);}finally{free(p);}}
 static int Current() {int now;return vconf_get_int("memory/system/source_type",out now)==0?now:-1;}
 static void Reply(IntPtr request,string outcome) {
  IntPtr reply;if(app_control_create(out reply)!=0)return;
  try{app_control_add_extra_data(reply,"outcome",outcome);app_control_reply_to_launch_request(reply,request,outcome=="switched"?Succeeded:Failed);}
  finally{app_control_destroy(reply);}
 }
 static void Handle(IntPtr request,IntPtr unused) {
  string outcome;
  try {
   int type=Type(Extra(request,"source"));
   if(IntPtr.Size!=4||!File.ReadAllText("/etc/prd_info.ini").Contains("Version=T-NKM2UABC-2310.0;"))outcome="unsupported-firmware";
   else if(type==0)outcome="unknown-source";
   else {
    int result=connect_source(type);
    // The source service updates the active-source key shortly after accepting.
    for(int i=0;i<20&&Current()!=type;i++)Thread.Sleep(100);
    outcome=Current()==type?"switched":"rejected-"+result;
   }
  } catch(Exception e) {outcome="error-"+e.GetType().Name;}
  Reply(request,outcome);
  ui_app_exit();
 }
 static int Main(string[] args) {
  var c=new Callbacks{create=_=>true,terminate=_=>{},pause=_=>{},resume=_=>{},control=control};
  var a=new string[args.Length+1];a[0]="";args.CopyTo(a,1);
  int r=ui_app_main(a.Length,a,ref c,IntPtr.Zero);GC.KeepAlive(c);return r;
 }
}
