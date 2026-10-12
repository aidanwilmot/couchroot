using System;
using System.Runtime.InteropServices;
class Program {
 const string Operation="http://tizen.org/appcontrol/operation/main";
 [DllImport("libbundle.so.0")] static extern IntPtr bundle_create();
 [DllImport("libbundle.so.0")] static extern void bundle_free(IntPtr b);
 [DllImport("libaul.so.0")] static extern int aul_svc_set_operation(IntPtr b,string operation);
 [DllImport("libaul.so.0")] static extern int aul_get_default_app(IntPtr b,out IntPtr app);
 [DllImport("libapp-context-manager-common.so")] static extern byte util_is_appbooting_supported_webapp_byappid(string app);
 [DllImport("libcapi-appfw-app-operation-tv.so.0")] static extern int app_operation_set_current_app(string operation,string app);
 [DllImport("libvconf.so.0")] static extern int vconf_set_str(string key,string value);
 [DllImport("libvconf.so.0")] static extern IntPtr vconf_get_str(string key);
 [DllImport("libvconf.so.0")] static extern int vconf_set_int(string key,int value);
 [DllImport("libvconf.so.0")] static extern int vconf_get_int(string key,out int value);
 [DllImport("libc")] static extern uint getuid();
 [DllImport("libc")] static extern void free(IntPtr p);
 // Native setters update values without replacing Buxton access labels.
 static void SetString(string key,string value) {
  if(vconf_set_str(key,value)!=0) throw new Exception("Failed to set "+key);
  IntPtr p=vconf_get_str(key);
  string actual=p==IntPtr.Zero?null:Marshal.PtrToStringAnsi(p);
  if(p!=IntPtr.Zero) free(p);
  if(actual!=value) throw new Exception("Readback mismatch for "+key);
  Console.WriteLine(key+"="+actual);
 }
 static void SetInt(string key,int value) {
  if(vconf_set_int(key,value)!=0) throw new Exception("Failed to set "+key);
  int actual;
  if(vconf_get_int(key,out actual)!=0 || actual!=value) throw new Exception("Readback mismatch for "+key);
  Console.WriteLine(key+"="+actual);
 }
 static int Main(string[] args) {
  if(IntPtr.Size!=4) return 2;
  Console.WriteLine("uid="+getuid());
  if(args.Length!=1 || (args[0]!="query" && args[0]!="hub" && args[0]!="stock")) return 2;
  IntPtr b=bundle_create(); if(b==IntPtr.Zero) return 3;
  try {
   int rc=aul_svc_set_operation(b,Operation); if(rc!=0) return 4;
   IntPtr app; rc=aul_get_default_app(b,out app);
   Console.WriteLine("home_result="+rc+" home_app="+(app==IntPtr.Zero?"<none>":Marshal.PtrToStringAnsi(app)));
   string current=app==IntPtr.Zero?null:Marshal.PtrToStringAnsi(app);
   if(app!=IntPtr.Zero) free(app);
   if(rc!=0) return 5;
   if(args[0]!="query") {
    if(current!="MiniHub001.Hub" && current!="com.samsung.tv.csfs") {
     Console.Error.WriteLine("Unexpected Home assignment; inspect before changing it."); return 7;
    }
    string target=args[0]=="hub"?"MiniHub001.Hub":"com.samsung.tv.csfs";
    int result=app_operation_set_current_app(Operation,target);
    Console.WriteLine("set_result="+result+" target="+target);
    if(result!=0) return 6;
    rc=aul_get_default_app(b,out app);
    string actual=app==IntPtr.Zero?null:Marshal.PtrToStringAnsi(app);
    if(app!=IntPtr.Zero) free(app);
    Console.WriteLine("home_after="+actual);
    if(rc!=0 || actual!=target) return 8;
    SetString("db/appfw/home_appid",target);
    SetInt("db/menu/smart_hub/ontvsetting/auto_start",args[0]=="hub"?1:0);
    if(args[0]=="stock") {
     SetString("db/appfw/startup_appid","org.tizen.tv-viewer");
     SetString("db/appfw/booting_appid_backup","org.tizen.tv-viewer");
    }
   }
   Console.WriteLine("hub_appbooting_supported="+util_is_appbooting_supported_webapp_byappid("MiniHub001.Hub"));
   return rc==0?0:5;
  } finally {bundle_free(b);}
 }
}
