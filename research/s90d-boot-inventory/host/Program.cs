using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.Json;
using System.Threading;
using Microsoft.Win32.SafeHandles;
public class Recorder {
 static int Main(string[] args)=>Run(args);
 const string Root="/opt/boot-inventory";
 const long Cap=4*1024*1024;
 static StreamWriter writer;
 static long bytes;
 static bool capped;
 static readonly object Gate=new object();
 static string session;
 [DllImport("libc.so.6")] static extern uint geteuid();
 [DllImport("libc.so.6",SetLastError=true)] static extern int mkdir(string path,uint mode);
 [DllImport("libc.so.6",SetLastError=true)] static extern int open(string path,int flags,uint mode);
 [DllImport("libc.so.6")] static extern void free(IntPtr ptr);
 [DllImport("libvconf.so.0")] static extern IntPtr vconf_get_str(string key);
 static double Mono()=>Stopwatch.GetTimestamp()/(double)Stopwatch.Frequency;
 static readonly string[] Markers={"/tmp/vconf_ready","/tmp/avoc_ready","/tmp/deviced-ready","/tmp/dbus_launch","/tmp/app_ready","/tmp/tvs_ready","/tmp/firstscreen_ready","/tmp/wm_start","/run/.wm_ready","/run/ps_agent.pid"};
 static readonly string[] Names={"MiniHub","wrt","app-boot","launchpad","enlightenment","Boot","Recorder","tvctx","csfs","DN_","dotnet-loader"};
 static bool Plain(string path)=>new FileInfo(path).LinkTarget==null;
 static FileStream Exclusive(string path){int fd=open(path,1|64|128|0x20000|0x80000,384);if(fd<0)throw new IOException("Exclusive open refused: "+path);return new FileStream(new SafeFileHandle(new IntPtr(fd),true),FileAccess.Write);}
 static void Event(string kind,string key,string value){lock(Gate){if(capped||writer==null)return;string s=JsonSerializer.Serialize(new{mono=Mono(),kind,key,value});int n=Encoding.UTF8.GetByteCount(s)+1;if(bytes+n>Cap-16384){capped=true;return;}writer.WriteLine(s);bytes+=n;}}
 static string Read(string path,int max=8192){try{using var f=new FileStream(path,FileMode.Open,FileAccess.Read,FileShare.ReadWrite);byte[] b=new byte[max];int n=f.Read(b,0,b.Length);return Encoding.UTF8.GetString(b,0,n);}catch{return null;}}
 static void Sample(string path){string s=Read(path);if(s!=null)Event("sample",path,s);}
 static void CopyLog(string name){string source="/tmp/hsm_boot_klog";if(!File.Exists(source)||!Plain(source))return;lock(Gate){try{using var src=File.OpenRead(source);using var dst=Exclusive(Path.Combine(session,name));byte[] b=new byte[8192];long copied=0;while(copied<786432&&bytes+b.Length<Cap-32768){int n=src.Read(b,0,b.Length);if(n==0)break;dst.Write(b,0,n);copied+=n;bytes+=n;}Event("copy",name,copied.ToString());}catch(Exception e){Event("error",name,e.Message);}}}
 static void Processes(){foreach(string path in Directory.EnumerateDirectories("/proc")){if(!int.TryParse(Path.GetFileName(path),out _))continue;string stat=Read(path+"/stat",2048);if(stat==null)continue;int a=stat.IndexOf('('),b=stat.LastIndexOf(')');if(a<0||b<=a)continue;string name=stat.Substring(a+1,b-a-1);if(!Names.Any(name.Contains))continue;Event("process-stat",Path.GetFileName(path),stat);string io=Read(path+"/io",1024);if(io!=null)Event("process-io",Path.GetFileName(path),io);}}
 static void Prune(){var dirs=new DirectoryInfo(Root).EnumerateDirectories("boot-*").Where(d=>d.LinkTarget==null&&Guid.TryParse(d.Name.Substring(5),out _)).OrderByDescending(d=>d.LastWriteTimeUtc).Skip(2);foreach(var dir in dirs){foreach(string name in new[]{"trace.jsonl","preserved-start.log","preserved-final.log"}){string p=Path.Combine(dir.FullName,name);if(File.Exists(p)&&Plain(p))File.Delete(p);}try{dir.Delete();}catch{/* Do not delete unknown contents. */}}}
 public static int Run(string[] args){
  int seconds=args.Length==1?int.Parse(args[0]):180;
  if(geteuid()!=0||seconds<2||seconds>180||!Directory.Exists(Root)||new DirectoryInfo(Root).LinkTarget!=null||!File.Exists(Root+"/enabled")||!Plain(Root+"/enabled"))return 2;
  string boot=Read("/proc/sys/kernel/random/boot_id",64)?.Trim();if(!Guid.TryParse(boot,out _))return 3;
  session=Root+"/boot-"+boot;if(Directory.Exists(session))return 0;Prune();if(mkdir(session,448)!=0)return 4;
  using var deadline=new Timer(_=>Environment.Exit(124),null,(seconds+5)*1000,Timeout.Infinite);
  using var stream=Exclusive(session+"/trace.jsonl");writer=new StreamWriter(stream,new UTF8Encoding(false),16384);
  double start=Mono();Event("identity","boot_id",boot);Event("identity","schema","1");Event("identity","clock","Stopwatch CLOCK_MONOTONIC; seconds");Sample("/etc/prd_info.ini");CopyLog("preserved-start.log");
  var watchers=new List<FileSystemWatcher>();
  foreach(string dir in new[]{"/tmp","/run"}){var w=new FileSystemWatcher(dir);w.NotifyFilter=NotifyFilters.FileName|NotifyFilters.LastWrite;FileSystemEventHandler handler=(s,e)=>{if(Markers.Contains(e.FullPath))Event("marker-event",e.FullPath,e.ChangeType+" present="+File.Exists(e.FullPath));};w.Created+=handler;w.Changed+=handler;w.Deleted+=handler;w.Renamed+=(s,e)=>{if(Markers.Contains(e.FullPath))Event("marker-event",e.FullPath,"Renamed");};w.Error+=(s,e)=>Event("error","watcher",e.GetException().Message);w.EnableRaisingEvents=true;watchers.Add(w);}
  foreach(string m in Markers)Event("marker-initial",m,File.Exists(m)?"present (time unknown)":"absent");
  string previous="";bool copied=false;
  while(Mono()-start<seconds&&!capped){double tick=Mono();Event("clocks","paired","monotonic="+tick.ToString("F6",System.Globalization.CultureInfo.InvariantCulture)+" realtime_ms="+DateTimeOffset.UtcNow.ToUnixTimeMilliseconds());Sample("/proc/uptime");Sample("/proc/stat");Sample("/proc/meminfo");Sample("/proc/diskstats");Sample("/proc/pressure/cpu");Sample("/proc/pressure/io");Processes();
   try{double before=Mono();IntPtr p=vconf_get_str("memory/appfw/current_fullscreen_appid");if(p!=IntPtr.Zero){string value=Marshal.PtrToStringAnsi(p);free(p);if(value!=previous){Event("foreground","memory/appfw/current_fullscreen_appid",value);previous=value;}}double delay=Mono()-before;if(delay>.1)Event("read-latency","vconf",delay.ToString());}catch(Exception e){Event("error","vconf",e.Message);}
   if(!copied&&Mono()-start>=60){CopyLog("preserved-final.log");copied=true;}lock(Gate)writer.Flush();int wait=(int)Math.Max(0,1000-(Mono()-tick)*1000);Thread.Sleep(wait);
  }
  foreach(var w in watchers)w.Dispose();if(!copied)CopyLog("preserved-final.log");lock(Gate){bool cap=capped;capped=false;Event("end","reason",cap?"byte cap":"deadline");writer.Flush();writer.Dispose();writer=null;}return 0;
 }
}
