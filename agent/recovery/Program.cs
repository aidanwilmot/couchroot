using System;
using System.Runtime.InteropServices;
using System.Threading;
class Recovery {
 [DllImport("libvconf.so.0")]static extern IntPtr vconf_get_str(string key);
 [DllImport("libvconf.so.0")]static extern int vconf_set_str(string key,string value);
 [DllImport("libc.so.6")]static extern void free(IntPtr ptr);
 [DllImport("libc.so.6")]static extern uint getuid();
 const string Key="db/sdk/develop/ip";
 static string Read(){var p=vconf_get_str(Key);if(p==IntPtr.Zero)throw new Exception("Host unavailable");try{return Marshal.PtrToStringAnsi(p);}finally{free(p);}}
 static bool Host(string h){System.Net.IPAddress ip;return System.Net.IPAddress.TryParse(h,out ip)&&ip.AddressFamily==System.Net.Sockets.AddressFamily.InterNetwork&&ip.ToString()==h&&h!="0.0.0.0";}
 static int Main(string[] args){try{
  if(getuid()!=0||args.Length!=4||!Host(args[1])||!Host(args[2]))return 2;
  int seconds;if(!int.TryParse(args[3],out seconds)||seconds<0||seconds>600)return 2;
  if(args[0]=="watch"){if(seconds<30)return 2;Thread.Sleep(seconds*1000);}
  else if(args[0]!="set"||seconds!=0)return 2;
  string current=Read();if(current==args[2]){Console.WriteLine("Already restored");return 0;}
  if(current!=args[1])throw new Exception("Host drift; refusing overwrite");
  if(vconf_set_str(Key,args[2])!=0||Read()!=args[2])throw new Exception("Host change unconfirmed");
  Console.WriteLine("Host readback verified");return 0;
 }catch(Exception e){Console.Error.WriteLine(e.Message);return 1;}}
}
