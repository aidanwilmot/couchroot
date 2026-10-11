using System;
using System.IO;
using System.Runtime.InteropServices;
class RootIdentity {
 [DllImport("libc.so.6", SetLastError=true)] static extern int open(string path,int flags);
 [DllImport("libc.so.6", SetLastError=true)] static extern int close(int fd);
 static int Main(){
  foreach(string line in File.ReadLines("/proc/self/status"))if(line.StartsWith("Uid:")||line.StartsWith("Gid:")||line.StartsWith("Cap")||line.StartsWith("NoNewPrivs:")||line.StartsWith("Seccomp:"))Console.WriteLine(line);
  Console.WriteLine("SMACK="+File.ReadAllText("/proc/self/attr/current"));
  foreach(var path in new[]{"/dev/mmcblk0p19","/proc/1/ns/mnt"}){int fd=open(path,0x80000);int error=Marshal.GetLastWin32Error();Console.WriteLine("READ-ONLY OPEN (zero bytes read) "+path+": "+(fd>=0?"success":"errno="+error));if(fd>=0)close(fd);}
  return 0;
 }
}
