using System;
using System.Collections.Generic;
using System.IO;
using System.Globalization;
using System.Runtime.InteropServices;
using System.Text.Json;

// Normally signed, no-window app; a narrowly scoped task rule requests it at boot.
// All state/diagnostics live on tmpfs. There is no daemon or retry across boots.
class Boot {
 const string Hub="MiniHub001.Hub", Root="/tmp/minimal-hub-boot";
 static string boot, outcome="entry", foreground="";
 static double entered, requested, readySince, completed;
 static int ticks, stable, attempts, result;
 static readonly List<object> launchHistory=new List<object>();
 [DllImport("libdeviced.so.1")] static extern int device_power_get_state();
 static bool accepted;
 [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate bool Create(IntPtr data);
 [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate void Event(IntPtr data);
 [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate void Control(IntPtr control,IntPtr data);
 [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Timer(IntPtr data);
 [StructLayout(LayoutKind.Sequential)] struct Callbacks {public Create create; public Event terminate,pause,resume;public Control control;}
 [DllImport("libcapi-appfw-application.so.0")] static extern int ui_app_main(int argc,string[] argv,ref Callbacks callbacks,IntPtr data);
 [DllImport("libcapi-appfw-application.so.0")] static extern void ui_app_exit();
 [DllImport("libglib-2.0.so.0")] static extern uint g_timeout_add(uint interval,Timer callback,IntPtr data);
 [DllImport("libvconf.so.0")] static extern int vconf_get_int(string key,out int value);
 [DllImport("libvconf.so.0")] static extern IntPtr vconf_get_str(string key);
 [DllImport("libc.so.6")] static extern void free(IntPtr p);
 [DllImport("libc.so.6")] static extern int chmod(string path,uint mode);
 [DllImport("libcapi-appfw-app-control.so.0")] static extern int app_control_create(out IntPtr control);
 [DllImport("libcapi-appfw-app-control.so.0")] static extern int app_control_destroy(IntPtr control);
 [DllImport("libcapi-appfw-app-control.so.0")] static extern int app_control_set_app_id(IntPtr control,string id);
 [DllImport("libcapi-appfw-app-control.so.0")] static extern int app_control_set_operation(IntPtr control,string op);
 [DllImport("libcapi-appfw-app-control.so.0")] static extern int app_control_send_launch_request(IntPtr control,IntPtr cb,IntPtr data);
 static readonly Timer timer=Tick;
 static double Uptime()=>double.Parse(File.ReadAllText("/proc/uptime").Split(' ')[0],CultureInfo.InvariantCulture);
 static string Read(string key) {IntPtr p=vconf_get_str(key);if(p==IntPtr.Zero)return null;try{return Marshal.PtrToStringAnsi(p);}finally{free(p);}}
 // These firmware marker files are SMACK-private to system processes. Do not
 // change their labels: use readable boot state plus a conservative settle period.
 static bool Ready()=>vconf_get_int("memory/system/boot_done",out int done)==0 && done==1 && device_power_get_state()==0;
 static void Status(string value) {
  outcome=value;
  File.WriteAllText(Root+"/status.new",JsonSerializer.Serialize(new{schema=1,boot,entered,uptime=Uptime(),outcome,foreground,attempts,result,accepted,launchHistory,power=device_power_get_state(),readySince,requested,completed,ticks,stable,wm=File.Exists("/tmp/wm_start"),app=File.Exists("/tmp/app_ready"),bootDoneRc=vconf_get_int("memory/system/boot_done",out int bd),bootDone=bd,ready=Ready()}));
  File.Move(Root+"/status.new",Root+"/status.json",true);
 }
 static int End(string value){Status(value);ui_app_exit();return 0;}
 static bool Start(IntPtr unused) {
  try {
   if(IntPtr.Size!=4 || !File.ReadAllText("/etc/prd_info.ini").Contains("Version=T-NKM2AKUC-2301.1;"))return false;
   boot=File.ReadAllText("/proc/sys/kernel/random/boot_id").Trim();entered=Uptime();
   if(Directory.Exists(Root)&&(File.GetAttributes(Root)&FileAttributes.ReparsePoint)!=0)return false;
   Directory.CreateDirectory(Root);chmod(Root,448);
   // Atomic once-per-boot claim, retained even after an abort/failure.
   using(var claim=new FileStream(Root+"/claimed",FileMode.CreateNew,FileAccess.Write,FileShare.None)){}
   foreground=Read("memory/appfw/current_fullscreen_appid");Status("waiting");
   if(g_timeout_add(1000,timer,IntPtr.Zero)==0){Status("timer-create-failed");return false;}return true;
  } catch(Exception e) {try{if(Directory.Exists(Root)&&!File.Exists(Root+"/status.json"))Status("entry-error-"+e.GetType().Name);}catch{}return false;}
 }
 static int Tick(IntPtr unused) {
  try {
   ticks++;double now=Uptime();foreground=Read("memory/appfw/current_fullscreen_appid");
   if(entered>120 || now>120 || ticks>=110)return End("deadline");
   if(foreground==Hub)return End(accepted?"foreground-confirmed":"already-foreground");
   if(device_power_get_state()!=0)return End("inactive-display");
   if(foreground==null)return 1;
   // User activity, playback or another app wins permanently for this boot.
   if(foreground!="" && foreground!="org.tizen.tv-viewer" && foreground!="com.samsung.tv.csfs")return End("other-app");
   if(accepted) {if(now-requested>=60)return End("foreground-timeout");return 1;}
   if(!Ready()){stable=0;readySince=0;return 1;}
   if(readySince==0)readySince=now;
   if(now-readySince<5 || ++stable<2)return 1;
   // The native send can block for several seconds and still report rejection
   // after Hub has begun starting. Give it breathing room after the call returns.
   if(attempts>0 && now-completed<3)return 1;
   if(attempts>=3)return End("launch-rejected");
   attempts++;requested=now;IntPtr control;string stage="create";
   result=app_control_create(out control);
   if(result==0)try {
    stage="set-app-id";
    result=app_control_set_app_id(control,Hub);
    if(result==0){stage="set-operation";result=app_control_set_operation(control,"http://tizen.org/appcontrol/operation/default");}
    if(result==0){stage="send";result=app_control_send_launch_request(control,IntPtr.Zero,IntPtr.Zero);}
   } finally {app_control_destroy(control);}
   // Keep every result (at most three) so a later success cannot hide an early
   // failure. Measure retry spacing from completion, not the pre-call timestamp.
   completed=Uptime();
   launchHistory.Add(new{attempt=attempts,started=requested,finished=completed,stage,result,foregroundBefore=foreground,foregroundAfter=Read("memory/appfw/current_fullscreen_appid"),readyAfter=Ready()});
   accepted=result==0;Status(accepted?"launch-accepted":"launch-retry");return 1;
  } catch {try{return End("error");}catch{ui_app_exit();return 0;}}
 }
 static int Main(string[] args) {
  var c=new Callbacks{create=Start,terminate=_=>{},pause=_=>{},resume=_=>{},control=(_,__)=>{}};
  var a=new string[args.Length+1];a[0]="";args.CopyTo(a,1);
  int r=ui_app_main(a.Length,a,ref c,IntPtr.Zero);GC.KeepAlive(c);GC.KeepAlive(timer);return r;
 }
}
