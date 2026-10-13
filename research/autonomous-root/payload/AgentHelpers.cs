// Original Couchroot managed helper execution views (0BSD).
using System;
using System.Collections.Generic;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.Json;
internal static partial class SamsungTvRootAgent
{
    private static readonly HashSet<string> Helpers = new HashSet<string>();
    private static string NamespaceLink(string path)
    {
        byte[] buffer=new byte[128];long count=readlink(path,buffer,(UIntPtr)buffer.Length).ToInt64();
        if(count<=0 || count>=buffer.Length)throw new IOException("Cannot verify mount namespace");return Encoding.UTF8.GetString(buffer,0,(int)count);
    }
    private static object HelperOperation(JsonElement value)
    {
        if(NamespaceLink("/proc/self/ns/mnt")==NamespaceLink("/proc/1/ns/mnt"))throw new IOException("Helper views require a private mount namespace");
        string op=Text(value,"op");
        if(op=="helper.prepare")
        {
            if(Helpers.Count>=8)throw new IOException("Helper limit reached; release an existing helper");
            string source=CheckedPath(Text(value,"path")),digest=Text(value,"sha256");
            if(!source.StartsWith("/opt/couchroot-agent/files/",StringComparison.Ordinal) || !IsDigest(digest))throw new ArgumentException("Expected a managed upload and SHA-256");
            JobDirectory();string parent="/opt/couchroot-agent/helpers";ManagedDirectory(parent,493);if(Directory.GetDirectories(parent).Length>=64)throw new IOException("Retained helper limit reached; inspect stale helper directories");
            string id=Guid.NewGuid().ToString("N"),directory=parent+"/"+id,binary=directory+"/helper";
            Directory.CreateDirectory(directory);bool mounted=false;
            try {
                File.Copy(source,binary,false);
                if(DigestPath(binary)!=digest)throw new IOException("Helper digest mismatch");
                if(chmod(directory,493)!=0 || chmod(binary,365)!=0)throw new IOException("Cannot protect helper");
                byte[] label=Encoding.UTF8.GetBytes("User");
                if(setxattr("/opt/couchroot-agent","security.SMACK64",label,(UIntPtr)label.Length,0)!=0 || setxattr(parent,"security.SMACK64",label,(UIntPtr)label.Length,0)!=0 || setxattr(directory,"security.SMACK64",label,(UIntPtr)label.Length,0)!=0 || setxattr(binary,"security.SMACK64",label,(UIntPtr)label.Length,0)!=0)throw new IOException("Cannot label helper");
                // Keep this view local even if an ancestor was a shared mount.
                if(mount(null,"/",null,(UIntPtr)(16384|262144),null)!=0)throw new IOException("Cannot privatize mount propagation");
                if(mount(directory,directory,null,(UIntPtr)4096,null)!=0)throw new IOException("Cannot bind helper view");mounted=true;
                if(mount(null,directory,null,(UIntPtr)(4096|32|1),null)!=0)throw new IOException("Cannot make helper view read-only");
                Helpers.Add(id);return new {helper_id=id,path=binary,sha256=digest,profile="app"};
            } catch {if(mounted)umount2(directory,0);FileDelete(binary);try{Directory.Delete(directory);}catch{}throw;}
        }
        if(op=="helper.release")
        {
            string id=Text(value,"helper_id");if(!Helpers.Contains(id))throw new ArgumentException("Unknown helper in this worker");
            string directory="/opt/couchroot-agent/helpers/"+id;
            if(umount2(directory,0)!=0)throw new IOException("Cannot unmount helper (it may still be in use)");
            File.Delete(directory+"/helper");Directory.Delete(directory);Helpers.Remove(id);return new {released=true};
        }
        throw new ArgumentException("Unknown helper operation");
    }
    private static void CloseHelpers()
    {
        foreach(string id in Helpers)
        {
            string directory="/opt/couchroot-agent/helpers/"+id;
            if(umount2(directory,0)==0){FileDelete(directory+"/helper");try{Directory.Delete(directory);}catch{}}
        }
        Helpers.Clear();
    }
    [DllImport("libc",SetLastError=true)]private static extern IntPtr readlink(string path,byte[] buffer,UIntPtr size);
    [DllImport("libc",SetLastError=true)]private static extern int setxattr(string path,string name,byte[] value,UIntPtr size,int flags);
    [DllImport("libc",SetLastError=true)]private static extern int mount(string source,string target,string type,UIntPtr flags,string data);
    [DllImport("libc",SetLastError=true)]private static extern int umount2(string path,int flags);
}
