using System;
using System.Reflection;
using System.Threading;
static class Harness {
 static readonly BindingFlags Flags=BindingFlags.Static|BindingFlags.NonPublic;
 static object Call(string name,params object[] args)=>typeof(Service).GetMethod(name,Flags).Invoke(null,args);
 static void Check(bool ok,string message) {if(!ok)throw new Exception(message);}
 static void Main() {
  foreach(string device in new[]{"s90d","qn90a"}) {
   Check((bool)Call("ValidEndpoint","https://nas/v1/devices/"+device,device),"Device URL rejected");
   foreach(string url in new[]{"http://nas/v1/devices/"+device,"https://x:y@nas/v1/devices/"+device,"https://nas/v1/devices/"+device+"?x=y","https://nas/v1/devices/"+device+"#x","https://nas/v1/devices/another"})
    Check(!(bool)Call("ValidEndpoint",url,device),"Invalid URL accepted");
  }
  Check((bool)Call("ValidEndpoint","https://nas/v1/s90d","s90d"),"Legacy S90D URL rejected");
  Check(!(bool)Call("ValidEndpoint","https://nas/v1/s90d","qn90a"),"Cross-device URL accepted");
  foreach(string device in new[]{"s90d","qn90a"}) {
   Telemetry.Entered.Reset();Telemetry.Release.Reset();Telemetry.Fail=device=="s90d";
   int before=Telemetry.Calls;
   Call("StartCollector",device);Check(Telemetry.Entered.Wait(3000),"Collector did not start");
   for(int i=0;i<20;i++)Call("StartCollector",device);
   Check(Telemetry.Calls==before+1,"Duplicate collector started");
   Check(Telemetry.Runtime=="/tmp/minimal-telemetry-"+device,"Wrong runtime directory");
   Check(Telemetry.Root=="/opt/usr/home/owner/apps_rw/MiniTelemetry/data","Wrong private directory");
   Telemetry.Release.Set();
   Check(SpinWait.SpinUntil(()=>(int)typeof(Service).GetField("started",Flags).GetValue(null)==0,3000),"Collector cannot restart after exit");
  }
  Console.WriteLine("Shared service: URL isolation, single collector, retry after failure and per-TV paths passed.");
 }
}
