using System;
using System.Threading;
public static class Telemetry {
 public static int Calls;
 public static readonly ManualResetEventSlim Entered=new(false), Release=new(false);
 public static string Runtime="",Root="";
 public static bool Fail;
 public static int RunWithPaths(string root,string runtime) {
  Interlocked.Increment(ref Calls);Root=root;Runtime=runtime;Entered.Set();
  if(!Release.Wait(5000))throw new Exception("Test timed out");
  if(Fail)throw new Exception("Collector failure");
  return 0;
 }
}
