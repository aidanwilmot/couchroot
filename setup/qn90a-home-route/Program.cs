using System;
using System.IO;
using System.Diagnostics;
using System.Reflection;
using System.Runtime.InteropServices;

// Fixed QN90A-only operations; the host wrapper verifies firmware and original files.
class HomeRoute {
 const string Database = "/opt/dbspace/.app-context.db";
 const string Changed = "memory/appfw/app_context_db_change";
 [DllImport("libc.so.6")] static extern uint getuid();
 [DllImport("libsqlite3.so.0")] static extern int sqlite3_open_v2(string path, out IntPtr db, int flags, IntPtr vfs);
 [DllImport("libsqlite3.so.0")] static extern int sqlite3_close(IntPtr db);
 [DllImport("libsqlite3.so.0")] static extern int sqlite3_busy_timeout(IntPtr db, int ms);
 [DllImport("libsqlite3.so.0")] static extern int sqlite3_exec(IntPtr db, string sql, IntPtr callback, IntPtr data, out IntPtr error);
 [DllImport("libsqlite3.so.0")] static extern void sqlite3_free(IntPtr error);
 [DllImport("libvconf.so.0")] static extern int vconf_get_int(string key, out int value);
 [DllImport("libvconf.so.0")] static extern int vconf_set_int(string key, int value);
 static string Sql(string mode) {
  using(var stream = Assembly.GetExecutingAssembly().GetManifestResourceStream("RootIdentity." + mode + ".sql"))
  using(var reader = new StreamReader(stream)) return reader.ReadToEnd();
 }
 static void Exec(IntPtr db, string sql) {
  IntPtr error;
  int rc = sqlite3_exec(db, sql, IntPtr.Zero, IntPtr.Zero, out error);
  string message = error == IntPtr.Zero ? "" : Marshal.PtrToStringAnsi(error);
  if(error != IntPtr.Zero) sqlite3_free(error);
  if(rc != 0) throw new Exception("SQLite " + rc + ": " + message);
 }
 static void Notify(int value) {
  int actual;
  if(vconf_set_int(Changed, value) != 0 || vconf_get_int(Changed, out actual) != 0 || actual != value)
   throw new Exception("Context reload notification failed");
 }
 static void Change(string mode) {
  int previous;
  if(vconf_get_int(Changed, out previous) != 0) throw new Exception("Missing context reload notification key");
  IntPtr db;
  if(sqlite3_open_v2(Database, out db, 2, IntPtr.Zero) != 0) {
   if(db != IntPtr.Zero) sqlite3_close(db);
   throw new Exception("Cannot open existing routing DB for update");
  }
  try {
   sqlite3_busy_timeout(db, 2000);
   Exec(db, Sql(mode));
   Console.WriteLine("Committed Home route " + mode);
   try { Notify(previous == 0 ? 1 : 0); }
   catch {
    string reverse = mode.EndsWith("apply") ? mode.Replace("apply", "restore") : mode.Replace("restore", "apply");
    Exec(db, Sql(reverse));
    Console.WriteLine("Reversed DB change after notification failure");
    Notify(previous == 0 ? 1 : 0);
    throw;
   }
   Console.WriteLine("Native context reload notification accepted (5-second debounce)");
  } finally { sqlite3_close(db); } // Closing rolls back any failed open transaction.
 }
 static void HomeKey() {
  var start = new ProcessStartInfo("/usr/bin/input_keyevent") { UseShellExecute = false };
  start.ArgumentList.Add("XF86Home");
  using(var p = Process.Start(start)) {
   if(!p.WaitForExit(4000)) { p.Kill(); throw new Exception("Input helper timeout"); }
   if(p.ExitCode != 0) throw new Exception("Input helper failed: " + p.ExitCode);
  }
  Console.WriteLine("One native Home key submitted");
 }
 static int Main() {
  foreach(string line in File.ReadLines("/proc/self/status"))
   if(line.StartsWith("Uid:") || line.StartsWith("Gid:")) Console.WriteLine(line);
  if(getuid() != 0) { Console.WriteLine("Owner baseline: no action"); return 0; }
  try {
#if HOME_APPLY
   Change("apply");
#elif HOME_RESTORE
   Change("restore");
#elif HOME_CAST_APPLY
   Change("cast-apply");
#elif HOME_CAST_RESTORE
   Change("cast-restore");
#elif HOME_CAST_EARLY_APPLY
   Change("cast-early-apply");
#elif HOME_CAST_EARLY_RESTORE
   Change("cast-early-restore");
#elif HOME_KEY
   HomeKey();
#else
#error A fixed operation must be selected at build time.
#endif
   return 0;
  } catch(Exception e) { Console.Error.WriteLine(e.Message); return 1; }
 }
}
