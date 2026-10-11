global using File = HostFile;
using System;
using System.Collections.Generic;
using System.Globalization;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Text.Json;

// Program.cs is compiled unchanged. Only its file and native I/O are replaced;
// every state transition under test executes the actual production Tick method.
static class HostFile {
 public static double Now;
 public static readonly Dictionary<string,string> Data=new();
 public static string ReadAllText(string path) => path=="/proc/uptime"
  ? Now.ToString(CultureInfo.InvariantCulture)+" 0" : Data[path];
 public static bool Exists(string path)=>Data.ContainsKey(path);
 public static void WriteAllText(string path,string value)=>Data[path]=value;
 public static void Move(string source,string target,bool overwrite) {
  if(!overwrite&&Data.ContainsKey(target))throw new Exception("Destination exists");
  Data[target]=Data[source];Data.Remove(source);
 }
 public static System.IO.FileAttributes GetAttributes(string path)=>System.IO.File.GetAttributes(path);
}

static class Harness {
 const int FirstRequest=22; // Expected policy: first ready tick at 16, five seconds plus confirmation tick.
 const string Viewer="org.tizen.tv-viewer", Hub="MiniHub001.Hub";
 static readonly Type Production=typeof(Boot);
 static readonly MethodInfo TickMethod=Production.GetMethod("Tick",BindingFlags.Static|BindingFlags.NonPublic)!;
 [DllImport("boot-test-native")] static extern void test_reset(int ready,int power,string? fg,int rejects);
 [DllImport("boot-test-native")] static extern void test_ready(int value);
 [DllImport("boot-test-native")] static extern void test_power(int value);
 [DllImport("boot-test-native")] static extern void test_foreground(string? value);
 [DllImport("boot-test-native")] static extern int test_sends();
 [DllImport("boot-test-native")] static extern int test_exits();
 [DllImport("boot-test-native")] static extern int test_outstanding_controls();
 [DllImport("boot-test-native")] static extern void test_fail_stage(int stage,int result);
 [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate void SendHook();
 [DllImport("boot-test-native")] static extern void test_on_send(SendHook hook);
 static double SendSeconds;
 static readonly SendHook sendHook=()=>HostFile.Now+=SendSeconds;
 static void Set(string name,object value)=>Production.GetField(name,BindingFlags.Static|BindingFlags.NonPublic)!.SetValue(null,value);
 static void Reset(int ready=1,int power=0,string? fg=Viewer,int rejects=0,double entered=15) {
  test_reset(ready,power,fg,rejects);test_on_send(sendHook);SendSeconds=0;HostFile.Now=entered;HostFile.Data.Clear();
  Set("boot","00000000-0000-4000-8000-000000000041");Set("outcome","entry");Set("foreground","");
  foreach(string field in new[]{"ticks","stable","attempts","result"})Set(field,0);
  foreach(string field in new[]{"requested","readySince","completed"})Set(field,0.0);
  Set("entered",entered);Set("accepted",false);
  ((System.Collections.IList)Production.GetField("launchHistory",BindingFlags.Static|BindingFlags.NonPublic)!.GetValue(null)!).Clear();
 }
 static int Tick(double now) {
  HostFile.Now=now;
  int value=(int)TickMethod.Invoke(null,new object[]{IntPtr.Zero})!;
  Assert(test_outstanding_controls()==0,"native appcontrol handle leaked");return value;
 }
 static JsonElement Status()=>JsonDocument.Parse(HostFile.Data["/tmp/minimal-hub-boot/status.json"]).RootElement;
 static string Outcome()=>Status().GetProperty("outcome").GetString()!;
 static void Assert(bool condition,string message) {if(!condition)throw new Exception(message);}
 static void Ended(int result,string outcome,int sends) {
  Assert(result==0,"timer still scheduled");Assert(test_exits()==1,"ui_app_exit count");
  Assert(Outcome()==outcome,"unexpected outcome: "+Outcome());Assert(test_sends()==sends,"unexpected launch count");
 }
 static void AcceptedAtFirstRequest() {
  for(int t=16;t<FirstRequest;t++){Assert(Tick(t)==1,"premature stop");Assert(test_sends()==0,"launched before settle");}
  Assert(Tick(FirstRequest)==1,"request tick stopped");Assert(test_sends()==1,"first request missing");
  Assert(Outcome()=="launch-accepted","request not accepted");
  Assert(Status().GetProperty("requested").GetDouble()==FirstRequest,"missing request timing");
 }
 static void Case(string name,Action body) {body();Console.WriteLine("PASS "+name);}
 static int Main(string[] args) {
  IntPtr native=NativeLibrary.Load(args[0]);
  NativeLibrary.SetDllImportResolver(typeof(Boot).Assembly,(name,assembly,path)=>native);
  Case("readiness settle then one request and foreground confirmation",()=>{
   Reset();AcceptedAtFirstRequest();test_foreground(Hub);Ended(Tick(FirstRequest+1),"foreground-confirmed",1);
  });
  Case("accepted request never reissued during 60-second confirmation",()=>{
   Reset();AcceptedAtFirstRequest();for(int t=FirstRequest+1;t<FirstRequest+60;t++)Assert(Tick(t)==1,"premature timeout");
   Ended(Tick(FirstRequest+60),"foreground-timeout",1);
  });
  Case("three rejected requests with minimum retry spacing",()=>{
   Reset(rejects:99);var times=new List<double>();int previous=0,ret=1;
   for(int t=16;t<=35&&ret!=0;t++){ret=Tick(t);if(test_sends()!=previous){times.Add(t);previous=test_sends();}}
   Ended(ret,"launch-rejected",3);Assert(times.Count==3&&times[1]-times[0]>=3&&times[2]-times[1]>=3,"retry cadence");
  });
  Case("two rejected requests then acceptance stops further requests",()=>{
   Reset(rejects:2);for(int t=16;t<=40;t++)Assert(Tick(t)==1,"unexpected stop");
   Assert(test_sends()==3,"request repeated after acceptance");test_foreground(Hub);Ended(Tick(41),"foreground-confirmed",3);
   var history=Status().GetProperty("launchHistory");
   Assert(history.GetArrayLength()==3,"lost failed launch history");
   for(int i=0;i<3;i++) {
    var attempt=history[i];
    Assert(attempt.GetProperty("attempt").GetInt32()==i+1,"attempt order");
    Assert(attempt.GetProperty("stage").GetString()=="send","wrong failure stage");
    Assert(attempt.GetProperty("result").GetInt32()==(i<2?-5:0),"earlier result overwritten");
    Assert(attempt.GetProperty("finished").GetDouble()>=attempt.GetProperty("started").GetDouble(),"invalid call timing");
   }
  });
  foreach(var failure in new[]{(1,"create"),(2,"set-app-id"),(3,"set-operation")}) {
   Case("retain pre-send failure at "+failure.Item2,()=>{
    Reset();test_fail_stage(failure.Item1,-22);
    for(int t=16;t<=FirstRequest;t++)Assert(Tick(t)==1,"unexpected early stop");
    var entry=Status().GetProperty("launchHistory")[0];
    Assert(entry.GetProperty("stage").GetString()==failure.Item2,"wrong pre-send stage");
    Assert(entry.GetProperty("result").GetInt32()==-22,"lost pre-send error");
    Assert(test_sends()==0,"sent after preparation failure");
   });
  }
  Case("slow rejected call gets three seconds after return before retry",()=>{
   Reset(rejects:2);SendSeconds=5.4;
   for(int t=16;t<=FirstRequest;t++)Tick(t);
   var first=Status().GetProperty("launchHistory")[0];
   Assert(Math.Abs(first.GetProperty("finished").GetDouble()-(FirstRequest+5.4))<0.001,"missing blocking call time");
   Tick(FirstRequest+5.5);Tick(FirstRequest+7);Tick(FirstRequest+8.39);
   Assert(test_sends()==1,"retried before three seconds after return");
   SendSeconds=0;Tick(FirstRequest+8.41);Assert(test_sends()==2,"retry missing after completion delay");
  });
  Case("Hub foreground during rejection settle cancels retries",()=>{
   Reset(rejects:2);SendSeconds=5.4;
   for(int t=16;t<=FirstRequest;t++)Tick(t);
   test_foreground(Hub);Ended(Tick(FirstRequest+6),"already-foreground",1);
  });
  Case("user activity wins during rejection settle",()=>{
   Reset(rejects:2);SendSeconds=5.4;
   for(int t=16;t<=FirstRequest;t++)Tick(t);
   test_foreground("kIciSQlYEM.plex");Ended(Tick(FirstRequest+6),"other-app",1);
  });
  Case("another app wins before a request",()=>{
   Reset(fg:"org.tizen.netflix-app");Ended(Tick(16),"other-app",0);
  });
  Case("another app wins while confirming an accepted request",()=>{
   Reset();AcceptedAtFirstRequest();test_foreground("kIciSQlYEM.plex");Ended(Tick(FirstRequest+1),"other-app",1);
  });
  Case("inactive display aborts without launch",()=>{
   Reset(power:2);Ended(Tick(16),"inactive-display",0);
  });
  Case("display becoming inactive cancels confirmation",()=>{
   Reset();AcceptedAtFirstRequest();test_power(2);Ended(Tick(FirstRequest+1),"inactive-display",1);
  });
  Case("Hub already foreground produces no launch",()=>{
   Reset(fg:Hub);Ended(Tick(16),"already-foreground",0);
  });
  Case("unreadable foreground cannot launch and expires",()=>{
   Reset(fg:null);Assert(Tick(16)==1,"early unreadable abort");Ended(Tick(121),"deadline",0);
  });
  Case("late admission cannot launch even without a prior claim",()=>{
   Reset(entered:121);Ended(Tick(122),"deadline",0);
  });
  Case("boot readiness must settle continuously",()=>{
   Reset(ready:0);for(int t=16;t<=20;t++)Tick(t);Assert(test_sends()==0,"not-ready launch");
   test_ready(1);Tick(21);Tick(22);test_ready(0);Tick(23);test_ready(1);
   for(int t=24;t<FirstRequest+8;t++){Tick(t);Assert(test_sends()==0,"settle failed to restart");}
   Tick(FirstRequest+8);Assert(test_sends()==1,"settled request missing");
  });
  Console.WriteLine("18 production Tick scenarios passed; ARM-only Start/claim and actual scheduling require device evidence.");
  return 0;
 }
}
