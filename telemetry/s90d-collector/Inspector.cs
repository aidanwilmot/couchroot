using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.Json;

// Fixed read-only queries only. No shell, command lines, environment, or app data.
public static class Inspector {
    [DllImport("libsqlite3.so.0")] static extern int sqlite3_open_v2(string file, out IntPtr db, int flags, IntPtr vfs);
    [DllImport("libsqlite3.so.0")] static extern int sqlite3_close(IntPtr db);
    [DllImport("libsqlite3.so.0")] static extern int sqlite3_busy_timeout(IntPtr db, int milliseconds);
    [DllImport("libsqlite3.so.0")] static extern int sqlite3_prepare_v2(IntPtr db, string sql, int bytes, out IntPtr statement, IntPtr tail);
    [DllImport("libsqlite3.so.0")] static extern int sqlite3_step(IntPtr statement);
    [DllImport("libsqlite3.so.0")] static extern int sqlite3_finalize(IntPtr statement);
    [DllImport("libsqlite3.so.0")] static extern IntPtr sqlite3_column_text(IntPtr statement, int column);
    [DllImport("libsqlite3.so.0")] static extern int sqlite3_column_bytes(IntPtr statement, int column);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate int Progress(IntPtr data);
    [DllImport("libsqlite3.so.0")] static extern void sqlite3_progress_handler(IntPtr db, int instructions, Progress callback, IntPtr data);
    [DllImport("libc.so.6")] static extern IntPtr sysconf(int name);
    [DllImport("libc.so.6")] static extern int getpagesize();
    [DllImport("libc.so.6")] static extern void free(IntPtr pointer);
    [UnmanagedFunctionPointer(CallingConvention.Cdecl)] delegate bool ContextCallback(IntPtr context,IntPtr data);
    [DllImport("libcapi-appfw-app-manager.so.0")] static extern int app_manager_foreach_app_context(ContextCallback callback,IntPtr data);
    [DllImport("libcapi-appfw-app-manager.so.0")] static extern int app_context_get_pid(IntPtr context,out int pid);
    [DllImport("libcapi-appfw-app-manager.so.0")] static extern int app_context_get_app_id(IntPtr context,out IntPtr id);
    [DllImport("libcapi-system-runtime-info.so.0")] static extern int runtime_info_get_process_memory_info(int[] pids,int count,ref IntPtr result);
    [StructLayout(LayoutKind.Sequential)] struct MemoryInfo {public int vsz,rss,pss,sharedClean,sharedDirty,privateClean,privateDirty;}
    public const int AppLimit=1024, ProcessLimit=512;
    static Dictionary<int, (long start, long ticks)> previous = new Dictionary<int, (long, long)>();
    static double previousAt;
    public const string AppQuery = @"SELECT a.app_id,a.package,p.package_version,p.package_type,a.app_component,
        (SELECT package_label FROM package_localized_info l WHERE l.package=a.package
         ORDER BY CASE package_locale WHEN 'en_US' THEN 0 WHEN 'No Locale' THEN 1 ELSE 2 END,package_locale LIMIT 1),
        p.package_system,p.package_removable,p.package_disable,a.app_disable,a.app_onboot,a.app_autorestart
        FROM package_app_info a LEFT JOIN package_info p ON p.package=a.package ORDER BY a.app_id LIMIT 1025";
    static readonly string[] Columns={"id","package","version","type","component","label","system","removable","package_disabled","app_disabled","on_boot","auto_restart"};
    static string Text(IntPtr statement,int column) {
        IntPtr p=sqlite3_column_text(statement,column);if(p==IntPtr.Zero)return null;
        int size=sqlite3_column_bytes(statement,column);if(size>512)throw new IOException("oversize field");
        byte[] bytes=new byte[size];Marshal.Copy(p,bytes,0,size);return Encoding.UTF8.GetString(bytes);
    }
    public static object Flag(string text) => text=="true" ? (object)true : text=="false" ? false : null;
    static Dictionary<string,object> Section(string status, List<Dictionary<string,object>> rows, bool truncated=false, int skipped=0) =>
        new Dictionary<string,object>{{"status",status},{"rows",rows},{"truncated",truncated},{"skipped",skipped}};
    static Dictionary<string,object> Apps(string path) {
        IntPtr db=IntPtr.Zero,statement=IntPtr.Zero;
        var rows=new List<Dictionary<string,object>>();var watch=Stopwatch.StartNew();
        Progress progress=_=>watch.ElapsedMilliseconds>250?1:0;
        try {
            // SQLITE_OPEN_READONLY: cannot create a missing database or modify one.
            if(sqlite3_open_v2(path,out db,1,IntPtr.Zero)!=0)throw new IOException();
            sqlite3_busy_timeout(db,100);sqlite3_progress_handler(db,1000,progress,IntPtr.Zero);
            if(sqlite3_prepare_v2(db,AppQuery,-1,out statement,IntPtr.Zero)!=0)throw new IOException();
            int rc;
            while((rc=sqlite3_step(statement))==100) {
                if(rows.Count==AppLimit)return Section("partial",rows,true);
                var row=new Dictionary<string,object>();
                for(int i=0;i<Columns.Length;i++){string value=Text(statement,i);row[Columns[i]]=i>=6?Flag(value):value;}
                rows.Add(row);
            }
            if(rc!=101)throw new IOException();
            return Section("ok",rows);
        } catch { return Section("unavailable",new List<Dictionary<string,object>>()); }
        finally {if(statement!=IntPtr.Zero)sqlite3_finalize(statement);if(db!=IntPtr.Zero)sqlite3_close(db);GC.KeepAlive(progress);}
    }
    static string Read(string path) {
        using var stream=new FileStream(path,FileMode.Open,FileAccess.Read,FileShare.ReadWrite);
        byte[] bytes=new byte[4097];int count=0,n;
        while(count<bytes.Length&&(n=stream.Read(bytes,count,bytes.Length-count))>0)count+=n;
        if(count>4096)throw new IOException();return Encoding.UTF8.GetString(bytes,0,count);
    }
    // stat's comm field may contain spaces and ')'; locate the final closing paren.
    public static (string name,string state,long start,long ticks,long rss) ParseStat(string text,long pageSize) {
        int open=text.IndexOf('('),close=text.LastIndexOf(')');
        if(open<0||close<=open)throw new FormatException();
        string name=text.Substring(open+1,close-open-1);
        if(name.Length>128)throw new FormatException();
        string[] fields=text.Substring(close+1).Split(new[]{' '},StringSplitOptions.RemoveEmptyEntries);
        long Number(int i)=>long.Parse(fields[i],CultureInfo.InvariantCulture);
        long ticks=checked(Number(11)+Number(12)),start=Number(19),rss=checked(Number(21)*pageSize);
        if(ticks<0||start<0||rss<0)throw new FormatException();
        return (name,fields[0],start,ticks,rss);
    }
    public static double? Cpu(long start,long ticks,long oldStart,long oldTicks,double elapsed,long hz) =>
        start==oldStart&&ticks>=oldTicks&&elapsed>0&&elapsed<=150&&hz>0 ? (double?)(100.0*(ticks-oldTicks)/hz/elapsed) : null;
    static Dictionary<string,object> Processes(string root,double now) {
        var rows=new List<Dictionary<string,object>>();var next=new Dictionary<int,(long,long)>();
        var watch=Stopwatch.StartNew();int skipped=0;bool truncated=false;
        try {
            long hz=sysconf(2).ToInt64(),pages=getpagesize();if(hz<=0||pages<=0)throw new IOException();
            // Enumerate names without stat'ing PID directories: on Tizen the
            // directory metadata may be restricted even when stat is readable.
            foreach(string dir in Directory.EnumerateFileSystemEntries(root)) {
                if(!int.TryParse(Path.GetFileName(dir),out int pid)||pid<=0)continue;
                if(rows.Count>=ProcessLimit||watch.ElapsedMilliseconds>250){truncated=true;break;}
                try {
                    var p=ParseStat(Read(Path.Combine(dir,"stat")),pages);double? cpu=null;
                    if(previous.TryGetValue(pid,out var old))cpu=Cpu(p.start,p.ticks,old.start,old.ticks,now-previousAt,hz);
                    rows.Add(new Dictionary<string,object>{{"pid",pid},{"name",p.name},{"state",p.state},{"rss_bytes",p.rss},{"cpu_percent",cpu}});
                    next[pid]=(p.start,p.ticks);
                } catch {skipped++;}
            }
            // The signed TV sandbox can hide other PIDs from /proc. The public
            // application-manager API can still enumerate managed app contexts.
            // Broker-only rows have unknown CPU/state: no guessed PID lifetime.
            bool managedOnly=rows.Count<=1&&!truncated;
            if(managedOnly) {
                var seen=new HashSet<int>(rows.Select(r=>(int)r["pid"]));
                ContextCallback callback=(context,data)=>{
                    IntPtr id=IntPtr.Zero;
                    try {
                        if(rows.Count>=ProcessLimit){truncated=true;return false;}
                        if(app_context_get_pid(context,out int pid)!=0||pid<=0||seen.Contains(pid))return true;
                        if(app_context_get_app_id(context,out id)!=0||id==IntPtr.Zero)return true;
                        string name=Marshal.PtrToStringAnsi(id);if(name==null||Encoding.UTF8.GetByteCount(name)>128)return true;
                        rows.Add(new Dictionary<string,object>{{"pid",pid},{"name",name},{"state","?"},{"rss_bytes",null},{"cpu_percent",null}});seen.Add(pid);
                    }catch{skipped++;}finally{if(id!=IntPtr.Zero)free(id);}
                    return true;
                };
                try {
                    if(app_manager_foreach_app_context(callback,IntPtr.Zero)!=0)skipped++;
                    var missing=rows.Where(r=>r["rss_bytes"]==null).ToArray();
                    if(missing.Length>0) {
                        IntPtr memory=IntPtr.Zero;
                        try {
                            if(runtime_info_get_process_memory_info(missing.Select(r=>(int)r["pid"]).ToArray(),missing.Length,ref memory)==0&&memory!=IntPtr.Zero)
                                for(int n=0;n<missing.Length;n++){var m=Marshal.PtrToStructure<MemoryInfo>(IntPtr.Add(memory,n*Marshal.SizeOf<MemoryInfo>()));if(m.rss>0)missing[n]["rss_bytes"]=(long)m.rss*1024;}
                        }finally{if(memory!=IntPtr.Zero)free(memory);}
                    }
                }catch{skipped++;}finally{GC.KeepAlive(callback);}
            }
            previous=next;previousAt=now;
            rows.Sort((a,b)=>((int)a["pid"]).CompareTo((int)b["pid"]));
            var result=Section(managedOnly||truncated||skipped>0?"partial":"ok",rows,truncated,skipped);
            result["scope"]=managedOnly?"managed-apps":"visible-proc";return result;
        } catch {previous.Clear();previousAt=0;return Section("unavailable",rows);}
    }
    public static Dictionary<string,object> Sample(double uptime) {
        var apps=Apps("/opt/dbspace/.pkgmgr_parser.db");var processes=Processes("/proc",uptime);
        var result=new Dictionary<string,object>{{"schema",1},{"uptime",uptime},{"apps",apps},{"processes",processes}};
        // Leave room for the existing bounded counters and envelope in 512 KiB.
        while(JsonSerializer.SerializeToUtf8Bytes(result).Length>400000) {
            var rows=(List<Dictionary<string,object>>)apps["rows"];
            if(rows.Count==0)break;
            rows.RemoveRange(Math.Max(0,rows.Count-64),Math.Min(64,rows.Count));
            apps["truncated"]=true;apps["status"]="partial";
        }
        return result;
    }
}
