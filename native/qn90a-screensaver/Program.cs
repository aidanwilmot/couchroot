using System;
using System.IO;
using System.Diagnostics;
using System.Runtime.InteropServices;
class SaverControl {
 [DllImport("libc.so.6")] static extern uint getuid();
 [DllImport("libc.so.6",SetLastError=true)] static extern int kill(int pid,int signal);
 [DllImport("libc.so.6",SetLastError=true)] static extern int chmod(string path,uint mode);
 static string Run(string file,string arguments,bool verbose=true) {
  var start=new ProcessStartInfo(file,arguments){UseShellExecute=false,RedirectStandardOutput=true,RedirectStandardError=true};
  using(var proc=Process.Start(start)) {
   var output=proc.StandardOutput.ReadToEndAsync();var error=proc.StandardError.ReadToEndAsync();
   if(!proc.WaitForExit(6000)){proc.Kill(true);throw new Exception("Child timeout");}
   if(verbose){Console.WriteLine(output.Result);Console.WriteLine(error.Result);}
   if(proc.ExitCode!=0)throw new Exception("Child exit="+proc.ExitCode);
   return output.Result;
  }
 }

 [DllImport("libcapi-screensaver.so")] static extern int screensaver_set_appid(string id);
 [DllImport("libcapi-screensaver.so")] static extern int screensaver_set_timeout(int seconds);
 [DllImport("libcapi-screensaver.so")] static extern void screensaver_fini();
 static void Require(int code,string action) {if(code!=0)throw new Exception(action+" failed: "+code); Console.WriteLine(action+" accepted");}
 // These Wayland setters flush requests but do not wait for server acceptance.
 // Keep the connection alive and verify the native state before this helper exits.
 static void SetTimeout(int seconds) {
  Require(screensaver_set_timeout(seconds),"Idle timeout request");
  for(int i=0;i<5;i++) {
   System.Threading.Thread.Sleep(20);
   string state=Run("/usr/bin/enlightenment_info","-scrsaver info",false);
   var match=System.Text.RegularExpressions.Regex.Match(state,@"Timeout period:\s+([0-9.]+)");
   if(match.Success&&double.Parse(match.Groups[1].Value,System.Globalization.CultureInfo.InvariantCulture)==seconds) {
    Console.WriteLine("Verified native idle timeout: "+seconds+" seconds");return;
   }
  }
  throw new Exception("Native timeout readback did not match request");
 }
 static void EnvironmentSetup() {
  foreach(var process in Process.GetProcessesByName("enlightenment")) {
   foreach(string pair in File.ReadAllText("/proc/"+process.Id+"/environ").Split('\0'))
    if(pair.StartsWith("XDG_RUNTIME_DIR=")||pair.StartsWith("WAYLAND_DISPLAY=")) {
     int split=pair.IndexOf('='); Environment.SetEnvironmentVariable(pair.Substring(0,split),pair.Substring(split+1));
     Console.WriteLine(pair);
    }
  }
 }

 const string ModulePath="/usr/lib/enlightenment/modules/e-mod-tizen-screensaver/linux-gnueabi-armv7l-ver-autocannoli-0.20/module.so";
 const string OverridePath="/var/lib/enlightenment/.e/e/modules/e-mod-tizen-screensaver/linux-gnueabi-armv7l-ver-autocannoli-0.20/module.so";
 const string OriginalHash="1dffd1d7d24b3827d0263e43e26d8149ba4d20fdcae3ba4fa75b4d6b9ac55728";
 const string OverrideHash="2456c5a3c12f52118080f324cd942000d7b77dafdf359bfc555d663e112907ba";
 const string CompositorHash="036317c954f37a9b01e46a23e0b9965fa58fbbbefb74e03e709bf21b645b7b4f";
 // Assembled from timeout-policy.S; tests execute these exact bytes under ARM emulation.
 const string TimeoutCode="002809d142f20002c4f2bc02914203d14cf20001c4f27201004b184771bf0b00";
 static byte[] Unhex(string hex) {var b=new byte[hex.Length/2];for(int i=0;i<b.Length;i++)b[i]=Convert.ToByte(hex.Substring(i*2,2),16);return b;}
 static void TimeoutPolicy(bool apply) {
  if(Hash(File.ReadAllBytes(ModulePath))!=OriginalHash||Hash(File.ReadAllBytes("/usr/bin/enlightenment"))!=CompositorHash)throw new Exception("Unknown timeout-policy firmware");
  var processes=Process.GetProcessesByName("enlightenment");
  if(processes.Length!=1)throw new Exception("Expected one compositor");
  int pid=processes[0].Id;long address=0;
  foreach(string line in File.ReadLines("/proc/"+pid+"/maps"))
   if(line.EndsWith(ModulePath)&&line.Contains("r-xp"))address=Convert.ToInt64(line.Split('-')[0],16);
  if(address==0)throw new Exception("Stock module missing");
  byte[] original=BitConverter.GetBytes(0x000bbf71u),patched=BitConverter.GetBytes(checked((uint)(address+0x6941))),code=Unhex(TimeoutCode),empty=new byte[32];
  using(var memory=new FileStream("/proc/"+pid+"/mem",FileMode.Open,FileAccess.ReadWrite,FileShare.ReadWrite,1,FileOptions.None)) {
   Func<long,int,byte[]> read=(offset,length)=>{var b=new byte[length];memory.Seek(address+offset,SeekOrigin.Begin);if(memory.Read(b,0,length)!=length)throw new Exception("Short policy read");return b;};
   Func<byte[],byte[],bool> same=(a,b)=>Convert.ToBase64String(a)==Convert.ToBase64String(b);
   Action<long,byte[]> write=(offset,b)=>{memory.Seek(address+offset,SeekOrigin.Begin);memory.Write(b,0,b.Length);memory.Flush();};
   var pointer=read(0x1716c,4);var body=read(0x6940,32);
   bool stock=same(pointer,original)&&same(body,empty),active=same(pointer,patched)&&same(body,code);
   if(!stock&&!active)throw new Exception("Unknown timeout policy state: "+BitConverter.ToString(pointer)+" / "+BitConverter.ToString(body));
   if((apply&&stock)||(!apply&&active)) {
    Require(kill(pid,19),"Brief compositor stop for timeout policy");
    try {
     bool stopped=false;
     for(int i=0;i<50;i++){foreach(string line in File.ReadLines("/proc/"+pid+"/status"))if(line.StartsWith("State:")&&line.Contains("T"))stopped=true;if(stopped)break;System.Threading.Thread.Sleep(2);}
     if(!stopped)throw new Exception("Compositor did not stop");
     // Refuse an observed instruction pointer inside the policy before writing.
     foreach(string task in Directory.GetDirectories("/proc/"+pid+"/task")) {
      var fields=File.ReadAllText(task+"/stat").Split(')')[1].Trim().Split(' ');
      long pc=long.Parse(fields[27]);
      if(pc>=address+0x6940&&pc<address+0x6960)throw new Exception("Thread is in timeout policy; no write");
     }
     if(!same(read(0x1716c,4),pointer)||!same(read(0x6940,32),body))throw new Exception("Policy changed before write");
     try {
      if(apply){write(0x6940,code);write(0x1716c,patched);}else{write(0x1716c,original);write(0x6940,empty);}
      if(!same(read(0x1716c,4),apply?patched:original)||!same(read(0x6940,32),apply?code:empty))throw new Exception("Policy readback mismatch");
     }catch {write(0x1716c,pointer);write(0x6940,body);throw;}
    }finally {Require(kill(pid,18),"Compositor resumed");}
   }
  }
  Console.WriteLine(apply?"Default timeout normalization active (7200 -> 300); reboot clears it":"Stock default timeout behavior restored");
 }
 static string Hash(byte[] bytes) {using(var h=System.Security.Cryptography.SHA256.Create()) return BitConverter.ToString(h.ComputeHash(bytes)).Replace("-", "").ToLowerInvariant();}
 static void RestoreModule() {
  if(Hash(File.ReadAllBytes(ModulePath))!=OriginalHash)throw new Exception("Unknown stock module");
  // A repeated recovery must remove our timeout policy before requesting 7200.
  foreach(var process in Process.GetProcessesByName("enlightenment")) {
   foreach(string line in File.ReadLines("/proc/"+process.Id+"/maps")) {
    if(line.EndsWith(ModulePath)&&line.Contains("r-xp")) {
     TimeoutPolicy(false);MemorySelection(false);break;
    }
   }
  }
  if(File.Exists(OverridePath)) {
   if(Hash(File.ReadAllBytes(OverridePath))!=OverrideHash)throw new Exception("Unknown override; refusing removal");
   File.Delete(OverridePath);
  }
  // Remove empty remnants of the rejected override as well as the known file.
  string architecture=Path.GetDirectoryName(OverridePath),module=Path.GetDirectoryName(architecture);
  if(Directory.Exists(architecture))Directory.Delete(architecture,false);
  if(Directory.Exists(module))Directory.Delete(module,false);
  Run("/usr/bin/enlightenment_info","-module unload e-mod-tizen-screensaver");
  Run("/usr/bin/enlightenment_info","-module load "+ModulePath);
  EnvironmentSetup();Require(screensaver_set_appid("org.tizen.default-screensaver"),"Stock native ID");SetTimeout(7200);screensaver_fini();
  ReadSelection();
  Console.WriteLine("Rejected override and empty directories removed; stock module loaded by absolute firmware path.");
 }
 // Change data only in the existing mapping; reboot automatically restores stock.
 static void MemorySelection(bool apply) {
  if(Hash(File.ReadAllBytes(ModulePath))!=OriginalHash)throw new Exception("Unknown stock module");
  var processes=Process.GetProcessesByName("enlightenment");
  if(processes.Length!=1)throw new Exception("Expected one compositor");
  int pid=processes[0].Id;long baseAddress=0;
  foreach(string line in File.ReadLines("/proc/"+pid+"/maps"))
   if(line.EndsWith(ModulePath)&&line.Contains("r-xp"))baseAddress=Convert.ToInt64(line.Split('-')[0],16);
  if(baseAddress==0)throw new Exception("Stock module mapping missing");
  byte[] oldPointer=BitConverter.GetBytes((uint)(0x572c-0x393c)),newPointer=BitConverter.GetBytes((uint)(0x6900-0x393c));
  byte[] newString=System.Text.Encoding.ASCII.GetBytes("MiniSave01.Saver\0"),oldString=new byte[17];
  using(var memory=new FileStream("/proc/"+pid+"/mem",FileMode.Open,FileAccess.ReadWrite,FileShare.ReadWrite,1,FileOptions.None)) {
   Func<long,int,byte[]> read=(offset,length)=>{var bytes=new byte[length];memory.Seek(baseAddress+offset,SeekOrigin.Begin);if(memory.Read(bytes,0,length)!=length)throw new Exception("Short native read");return bytes;};
   Func<byte[],byte[],bool> same=(a,b)=>Convert.ToBase64String(a)==Convert.ToBase64String(b);
   Action<long,byte[]> write=(offset,bytes)=>{memory.Seek(baseAddress+offset,SeekOrigin.Begin);memory.Write(bytes,0,bytes.Length);memory.Flush();};
   var pointer=read(0x3978,4);var label=read(0x6900,newString.Length);
   bool original=same(pointer,oldPointer)&&same(label,oldString),patched=same(pointer,newPointer)&&same(label,newString);
   if(!original&&!patched)throw new Exception("Unexpected native data; no write: "+BitConverter.ToString(pointer)+" / "+BitConverter.ToString(label));
   if((apply&&original)||(!apply&&patched)) {
    Require(kill(pid,19),"Brief compositor stop");
    try {
     bool stopped=false;
     for(int i=0;i<50;i++) {foreach(string line in File.ReadLines("/proc/"+pid+"/status"))if(line.StartsWith("State:")&&line.Contains("T"))stopped=true;if(stopped)break;System.Threading.Thread.Sleep(2);}
     if(!stopped)throw new Exception("Compositor did not stop");
     if(!same(read(0x3978,4),pointer)||!same(read(0x6900,newString.Length),label))throw new Exception("Native data changed before write");
     try {
      if(apply){write(0x6900,newString);write(0x3978,newPointer);}else{write(0x3978,oldPointer);write(0x6900,oldString);}
      if(!same(read(0x3978,4),apply?newPointer:oldPointer)||!same(read(0x6900,newString.Length),apply?newString:oldString))throw new Exception("Native readback mismatch: "+BitConverter.ToString(read(0x3978,4))+" / "+BitConverter.ToString(read(0x6900,newString.Length)));
     }catch {write(0x3978,pointer);write(0x6900,label);throw;}
    }finally {Require(kill(pid,18),"Compositor resumed");}
   }
  }
  EnvironmentSetup();Require(screensaver_set_appid(apply?"DEFAULT":"org.tizen.default-screensaver"),"Native selection request");
  string expected=apply?"MiniSave01.Saver":"org.tizen.default-screensaver";
  bool selected=false;
  for(int i=0;i<25;i++) {System.Threading.Thread.Sleep(20);if(ReadSelection(false)==expected){selected=true;break;}}
  screensaver_fini();
  if(!selected)throw new Exception("Native app-ID request not reflected; inspect before further changes");
  Console.WriteLine(apply?"In-memory Asteroids selection applied; full reboot clears it":"Original in-memory selection restored");
 }
 static string ReadSelection(bool verbose=true,bool required=true) {
  string selected=null;
  using(var hash=System.Security.Cryptography.SHA256.Create())
   if(BitConverter.ToString(hash.ComputeHash(File.ReadAllBytes(ModulePath))).Replace("-", "").ToLowerInvariant()!="1dffd1d7d24b3827d0263e43e26d8149ba4d20fdcae3ba4fa75b4d6b9ac55728")
    throw new Exception("Native module hash differs; no fixed-offset read");
  foreach(var proc in Process.GetProcessesByName("enlightenment")) {
   foreach(string line in File.ReadLines("/proc/"+proc.Id+"/maps")) {
    if(!line.Contains("/e-mod-tizen-screensaver/")||!line.Contains("r-xp"))continue;
    string mappedPath=line.Substring(line.IndexOf('/'));
    string mappedHash=Hash(File.ReadAllBytes(mappedPath));
    if(mappedHash!=OriginalHash&&mappedHash!=OverrideHash)throw new Exception("Unknown mapped module");
    if(verbose) {Console.WriteLine("Mapped screensaver module: "+mappedPath);
    Console.WriteLine("Mapped module SHA-256: "+mappedHash);}
    long baseAddress=Convert.ToInt64(line.Split('-')[0],16);
    using(var memory=new FileStream("/proc/"+proc.Id+"/mem",FileMode.Open,FileAccess.Read,FileShare.ReadWrite,1,FileOptions.None)) {
     byte[] pointer=new byte[4];memory.Seek(baseAddress+0x172bc,SeekOrigin.Begin);if(memory.Read(pointer,0,4)!=4)throw new Exception("Short state pointer read");
     long state=BitConverter.ToUInt32(pointer,0); if(state<0x10000)throw new Exception("Invalid native state pointer");
     byte[] appid=new byte[256];memory.Seek(state+4,SeekOrigin.Begin);if(memory.Read(appid,0,256)!=256)throw new Exception("Short app ID read");
     selected=System.Text.Encoding.ASCII.GetString(appid).Split('\0')[0];
     if(verbose)Console.WriteLine("Native saver app ID: "+selected);
     if(verbose) {
      byte[] history=new byte[276];memory.Seek(baseAddress+0x17310,SeekOrigin.Begin);
      if(memory.Read(history,0,history.Length)!=history.Length)throw new Exception("Short history read");
      Console.WriteLine("Last native request: pid="+BitConverter.ToInt32(history,0)+" process="+System.Text.Encoding.ASCII.GetString(history,4,256).Split('\0')[0]+" timeout="+BitConverter.ToInt32(history,260)+" status="+BitConverter.ToInt32(history,264)+" modified="+BitConverter.ToInt32(history,272));
      byte[] policy=new byte[4];memory.Seek(baseAddress+0x1716c,SeekOrigin.Begin);if(memory.Read(policy,0,4)!=4)throw new Exception("Short policy pointer read");
      Console.WriteLine("Timeout policy pointer: "+BitConverter.ToUInt32(policy,0).ToString("x8")+" (normalized="+(BitConverter.ToUInt32(policy,0)==baseAddress+0x6941)+")");
     }
    }
   }
  }
  if(selected==null) {
   if(required)throw new Exception("No mapped native screensaver state");
   Console.WriteLine("No mapped native screensaver state");
  }
  return selected;
 }
 static int Main() {
  foreach(string line in File.ReadLines("/proc/self/status")) if(line.StartsWith("Uid:") || line.StartsWith("Gid:")) Console.WriteLine(line);
  if(getuid()!=0) { Console.WriteLine("Owner baseline: no action"); return 0; }
  try {
#if HOME_SAVER_MEMORY_APPLY
   MemorySelection(true);ReadSelection();
#elif HOME_SAVER_SCRIPT_PROBE
   const string probe="/opt/data/DeviceTracker/.qn90a-script-probe";
   if(File.Exists(probe))throw new Exception("Script probe already exists");
   try {
    File.WriteAllText(probe,"#!/bin/sh\nexit 0\n");
    Require(chmod(probe,448),"Temporary script permissions");
    Run(probe,"");Console.WriteLine("Unsigned harmless script executed through kernel shebang");
   }finally {if(File.Exists(probe))File.Delete(probe);}
#elif HOME_SAVER_APPLY
   TimeoutPolicy(false);MemorySelection(true);EnvironmentSetup();SetTimeout(7200);screensaver_fini();ReadSelection();
#elif HOME_SAVER_MEMORY_RESTORE
   TimeoutPolicy(false);MemorySelection(false);ReadSelection();
#elif HOME_SAVER_MODULE_RESTORE
   RestoreModule();
#elif HOME_SAVER_IDLE_TRIAL
   EnvironmentSetup();SetTimeout(15);screensaver_fini();
#elif HOME_SAVER_RESTORE
   TimeoutPolicy(false);
   MemorySelection(false);
   SetTimeout(7200); screensaver_fini();
#elif HOME_SAVER_TIMEOUT_FIVE_MINUTES
   TimeoutPolicy(false);EnvironmentSetup();SetTimeout(300);screensaver_fini();
#elif HOME_SAVER_TIMEOUT_RESTORE
   TimeoutPolicy(false);EnvironmentSetup(); SetTimeout(7200); screensaver_fini();
#elif HOME_SAVER_WAKE
   Console.WriteLine("Input begin uptime: "+File.ReadAllText("/proc/uptime").Trim());
   Run("/usr/bin/input_keyevent","Right");
   Console.WriteLine("Input end uptime: "+File.ReadAllText("/proc/uptime").Trim());
#elif HOME_SAVER_CAPTURE
   Run("/usr/bin/enlightenment_info","-dump_screen -p /home/owner/share/tmp/sdk_tools/ -n qn90a-asteroids.png");
#elif HOME_SAVER_INSPECT
   Console.WriteLine("Boot ID: "+File.ReadAllText("/proc/sys/kernel/random/boot_id").Trim());
   Console.WriteLine("Uptime: "+File.ReadAllText("/proc/uptime").Trim());
   Run("/usr/bin/enlightenment_info","-module list");
   ReadSelection(true,false);
   Console.WriteLine("Rejected user override present: "+File.Exists(OverridePath));
   Run("/usr/bin/enlightenment_info","-scrsaver info");
   Run("/usr/bin/vconftool","get memory/window_system/screensaver_on_off");
   Run("/usr/bin/vconftool","get memory/appfw/current_fullscreen_appid");
   Run("/usr/bin/vconftool","get memory/appfw/current_partial_appid");

#else
#error Select a fixed operation
#endif
   return 0;
  }catch(Exception e){Console.Error.WriteLine(e.Message);return 1;}
 }
}
