using System;
using System.IO;
using System.Runtime.InteropServices;
class Control {
 [DllImport("libvconf.so.0")] static extern IntPtr vconf_get_str(string key);
 [DllImport("libvconf.so.0")] static extern int vconf_get_int(string key,out int value);
 [DllImport("libvconf.so.0")] static extern int vconf_set_str(string key,string value);
 [DllImport("libvconf.so.0")] static extern int vconf_set_int(string key,int value);
 [DllImport("libc.so.6")] static extern void free(IntPtr p);
 [DllImport("libbundle.so.0")] static extern IntPtr bundle_create();
 [DllImport("libbundle.so.0")] static extern void bundle_free(IntPtr b);
 [DllImport("libaul.so.0")] static extern int aul_svc_set_operation(IntPtr b,string operation);
 [DllImport("libaul.so.0")] static extern int aul_get_default_app(IntPtr b,out IntPtr app);
 [DllImport("libcapi-appfw-app-operation-tv.so.0")] static extern int app_operation_set_current_app(string operation,string app);
 const string Op="http://tizen.org/appcontrol/operation/main";
 static string Read(string key) {
  if(key.EndsWith("auto_start") || key=="memory/appfw/app_context_db_change") {
   int n;if(vconf_get_int(key,out n)!=0)throw new Exception("Missing integer key");return n.ToString();
  }
  IntPtr p=vconf_get_str(key);if(p==IntPtr.Zero)throw new Exception("Missing string key");
  try{return Marshal.PtrToStringAnsi(p);}finally{free(p);}
 }
 static string Home() {
  IntPtr b=bundle_create();if(b==IntPtr.Zero)throw new Exception("Missing bundle");
  try {IntPtr p; if(aul_svc_set_operation(b,Op)!=0 || aul_get_default_app(b,out p)!=0)throw new Exception("Home query failed");
   try{return Marshal.PtrToStringAnsi(p);}finally{if(p!=IntPtr.Zero)free(p);}
  }finally{bundle_free(b);}
 }
 static int Main(string[] a) {
  try {
   if(a.Length<2 || IntPtr.Size!=4)throw new Exception("Arguments/architecture");
   string firmware=a[1]=="s90d"?"T-PTMDAKUC-0090-2130.0":a[1]=="qn90a"?"T-NKM2AKUC-2301.1":throw new Exception("Model");
   if(!File.ReadAllText("/etc/prd_info.ini").Contains("Version="+firmware+";"))throw new Exception("Firmware");
   if(a[0]=="reload") {
    const string key="memory/appfw/app_context_db_change";int next=Read(key)=="0"?1:0;
    if(vconf_set_int(key,next)!=0 || Read(key)!=next.ToString())throw new Exception("Reload notification");return 0;
   }
   if(a[0]=="qn90a-firstscreen") {
    if(a[1]!="qn90a" || a.Length!=5)throw new Exception("QN90A first-screen mode only");
    string key=a[2],before=a[3],after=a[4];
    if(key=="db/first_screen/type") {
     if(!((before=="com.samsung.tv.csfs" && after=="MiniHub001.Hub") ||
          (before=="MiniHub001.Hub" && after=="com.samsung.tv.csfs")))throw new Exception("First-screen value pair");
     if(Read(key)!=before)throw new Exception("First-screen setting changed concurrently");
     if(vconf_set_str(key,after)!=0 || Read(key)!=after)throw new Exception("First-screen setter/readback");return 0;
    }
    if(key=="db/menu/smart_hub/ontvsetting/auto_start") {
     if(!((before=="0" && after=="1") || (before=="1" && after=="0")))throw new Exception("Autostart value pair");
     if(Read(key)!=before)throw new Exception("Autostart setting changed concurrently");
     int value=int.Parse(after);
     if(vconf_set_int(key,value)!=0 || Read(key)!=after)throw new Exception("Autostart setter/readback");return 0;
    }
    throw new Exception("QN90A key not allowlisted");
   }
   if(a[1]!="s90d" || a.Length!=5)throw new Exception("S90D-only settings");
   if(a[0]=="home") {
    if((a[3]!="MiniHub001.Hub" && a[3]!="com.samsung.tv.csfs") || (a[4]!="MiniHub001.Hub" && a[4]!="com.samsung.tv.csfs"))throw new Exception("Home value");
    if(Home()!=a[3])throw new Exception("Home changed concurrently");
    if(app_operation_set_current_app(Op,a[4])!=0 || Home()!=a[4])throw new Exception("Home setter/readback");return 0;
   }
   if(a[0]!="setting" || (a[2]!="db/appfw/home_appid" && a[2]!="db/menu/smart_hub/ontvsetting/auto_start"))throw new Exception("Key not allowlisted");
   if(Read(a[2])!=a[3])throw new Exception("Setting changed concurrently");
   int rc;
   if(a[2].EndsWith("auto_start")) {int n=int.Parse(a[4]);if(n!=0 && n!=1)throw new Exception("Integer value");rc=vconf_set_int(a[2],n);}
   else {if(a[4]!="MiniHub001.Hub" && a[4]!="com.samsung.tv.csfs")throw new Exception("Home string");rc=vconf_set_str(a[2],a[4]);}
   if(rc!=0 || Read(a[2])!=a[4])throw new Exception("Setter/readback");return 0;
  }catch(Exception e){Console.Error.WriteLine(e.Message);return 1;}
 }
}
