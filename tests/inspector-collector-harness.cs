using System;
using System.Collections.Generic;
using System.Reflection;
using System.Runtime.InteropServices;
class InspectorHarness {
 static void Check(bool condition){if(!condition)throw new Exception("Inspector assertion failed");}
 static void Main(string[] args) {
  NativeLibrary.SetDllImportResolver(typeof(Inspector).Assembly,(name,assembly,path)=>name=="libsqlite3.so.0"&&OperatingSystem.IsMacOS()?NativeLibrary.Load("/usr/lib/libsqlite3.dylib"):IntPtr.Zero);
  Check(Inspector.Flag("false").Equals(false));Check(Inspector.Flag("true").Equals(true));Check(Inspector.Flag("garbage")==null);
  string[] fields=new string[22];Array.Fill(fields,"0");fields[0]="S";fields[11]="100";fields[12]="50";fields[19]="222";fields[21]="10";
  var p=Inspector.ParseStat("42 (name with ) space) "+string.Join(" ",fields),4096);
  Check(p.name=="name with ) space"&&p.ticks==150&&p.start==222&&p.rss==40960);
  Check(Inspector.Cpu(222,250,222,150,10,100)==10);Check(Inspector.Cpu(223,250,222,150,10,100)==null);
  Check(Inspector.Cpu(222,100,222,150,10,100)==null);Check(Inspector.Cpu(222,250,222,150,160,100)==null);
  var method=typeof(Inspector).GetMethod("Apps",BindingFlags.NonPublic|BindingFlags.Static);
  var apps=(Dictionary<string,object>)method.Invoke(null,new object[]{args[0]});
  var rows=(List<Dictionary<string,object>>)apps["rows"];
  Check((string)apps["status"]=="partial"&&rows.Count==1024&&(bool)apps["truncated"]);
  Check((bool)rows[0]["on_boot"]&&rows[0]["app_disabled"]==null);
  apps=(Dictionary<string,object>)method.Invoke(null,new object[]{args[0]+".absent"});Check((string)apps["status"]=="unavailable");
  Check(!System.IO.File.Exists(args[0]+".absent"));
  Console.WriteLine("PASS: registry read-only query, bounded rows, unknown flags, stat parsing, PID reuse and CPU gaps");
 }
}
