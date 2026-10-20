using System;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Threading;

// One build-time allowlisted web app, no arbitrary command or database writes.
class AppCleanup {
#if HOME_CLEANUP_0
 const string App = "9FhM0cODbY.TikTokTV";
 const string ReviewedVersion = "1.1.8";
#elif HOME_CLEANUP_1
 const string App = "zigzSWa1hy.InstagramAirwave";
 const string ReviewedVersion = "5.10.10";
#elif HOME_CLEANUP_2
 const string App = "LImG0QPABV.QXHMarketplace";
 const string ReviewedVersion = "2.2.17";
#elif HOME_CLEANUP_3
 const string App = "jAfAs7yVDX.TheSix";
 const string ReviewedVersion = "1.7.3";
#elif HOME_CLEANUP_4
 const string App = "yL49PNFmjW.PromotionApp";
 const string ReviewedVersion = "3.2.96";
#elif HOME_CLEANUP_5
 const string App = "HupEmjIB4I.Glance";
 const string ReviewedVersion = "0.8.8";
#elif HOME_CLEANUP_6
 const string App = "GHI3a0zMSx.XboxGamePass";
 const string ReviewedVersion = "4.55.698";
#elif HOME_CLEANUP_7
 const string App = "IewQEY143t.GoogleDuoWeb";
 const string ReviewedVersion = "1.9.21";
#elif HOME_CLEANUP_8
 const string App = "AkhP5nCr24.GoogleAssistant";
 const string ReviewedVersion = "0.21.11110";
#elif HOME_CLEANUP_9
 const string App = "AQKO41xyKP.AmazonAlexa";
 const string ReviewedVersion = "0.21.10220";
#else
#error A fixed cleanup target must be selected.
#endif
 [DllImport("libc.so.6")] static extern uint getuid();
 [DllImport("libsqlite3.so.0")] static extern int sqlite3_open_v2(string path, out IntPtr db, int flags, IntPtr vfs);
 [DllImport("libsqlite3.so.0")] static extern int sqlite3_close(IntPtr db);
 [DllImport("libsqlite3.so.0")] static extern int sqlite3_prepare_v2(IntPtr db, string sql, int length, out IntPtr stmt, IntPtr tail);
 [DllImport("libsqlite3.so.0")] static extern int sqlite3_step(IntPtr stmt);
 [DllImport("libsqlite3.so.0")] static extern int sqlite3_column_int(IntPtr stmt, int column);
 [DllImport("libsqlite3.so.0")] static extern IntPtr sqlite3_column_text(IntPtr stmt, int column);
 [DllImport("libsqlite3.so.0")] static extern int sqlite3_finalize(IntPtr stmt);
 [DllImport("libglib-2.0.so.0")] static extern int g_main_context_iteration(IntPtr context, int mayBlock);
 [UnmanagedFunctionPointer(CallingConvention.Cdecl)]
 delegate void Notify(IntPtr app, int evt, int progress, int error, IntPtr data);
 [DllImport("libwas_manager_api.so", EntryPoint="_Z25was_manager_uninstall_app17was_app_id_type_ePKcPFvS1_18was_notify_event_eiiPvES3_i", CallingConvention=CallingConvention.Cdecl)]
 static extern int Uninstall(int type, string app, Notify callback, IntPtr data, int force);
 static volatile int terminalEvent;
 static int lastProgress = -1;
 static readonly Notify Callback = (app, evt, progress, error, data) => {
  if(evt != 121 || progress / 25 != lastProgress) {
   Console.WriteLine("Uninstall event=" + evt + " progress=" + progress + " error=" + error);
   lastProgress = progress / 25;
  }
  if(evt == 122 || evt == 123) terminalEvent = evt;
 };
 static int Count(IntPtr db, string sql) {
  IntPtr stmt;
  if(sqlite3_prepare_v2(db, sql, -1, out stmt, IntPtr.Zero) != 0) throw new Exception("Cannot prepare read-only package check");
  try {
   if(sqlite3_step(stmt) != 100) throw new Exception("Cannot read package state");
   return sqlite3_column_int(stmt, 0);
  } finally { sqlite3_finalize(stmt); }
 }
 static string StoreId(string pkg) {
  IntPtr db, stmt = IntPtr.Zero;
  if(sqlite3_open_v2("/opt/dbspace/.webappservice.db", out db, 1, IntPtr.Zero) != 0)
   throw new Exception("Cannot read Samsung app catalog");
  try {
   string sql = "SELECT id FROM widgetinfo WHERE pkgname='" + pkg + "' AND tizen_id='" + App + "' AND is_removable=1 AND is_system=0 AND is_lock=0 AND install_state=3 AND is_app_available=1 AND is_need_reset=0";
   if(sqlite3_prepare_v2(db, sql, -1, out stmt, IntPtr.Zero) != 0 || sqlite3_step(stmt) != 100)
    throw new Exception("Samsung app identity/protection check failed");
   string id = Marshal.PtrToStringAnsi(sqlite3_column_text(stmt, 0));
   if(String.IsNullOrEmpty(id) || sqlite3_step(stmt) != 101) throw new Exception("Ambiguous Samsung app identity");
   return id;
  } finally { if(stmt != IntPtr.Zero) sqlite3_finalize(stmt); sqlite3_close(db); }
 }
 static int Main() {
  foreach(string line in File.ReadLines("/proc/self/status"))
   if(line.StartsWith("Uid:") || line.StartsWith("Gid:")) Console.WriteLine(line);
  if(getuid() != 0) { Console.WriteLine("Owner baseline: no action"); return 0; }
  IntPtr db = IntPtr.Zero;
  try {
   if(sqlite3_open_v2("/opt/dbspace/.pkgmgr_parser.db", out db, 1, IntPtr.Zero) != 0)
    throw new Exception("Cannot open package database read-only");
   string pkg = App.Split('.')[0];
   string predicate = " FROM package_info WHERE package='" + pkg + "'";
   if(Count(db, "SELECT COUNT(*)" + predicate + " AND mainapp_id='" + App + "' AND package_version='" + ReviewedVersion + "' AND package_type='wgt' AND package_removable='true' AND package_preload='false' AND package_readonly='false' AND package_system='false'") != 1 ||
      Count(db, "SELECT COUNT(*) FROM package_dependency_info WHERE depends_on='" + pkg + "'") != 0)
    throw new Exception("Package protection/identity/dependency guard refused removal");
   var timer = Stopwatch.StartNew();
   // WAS type 0 expects the catalog/store ID, not the Tizen launch ID.
   string storeId = StoreId(pkg);
   int rc = Uninstall(0, storeId, Callback, IntPtr.Zero, 0);
   Console.WriteLine("Normal WAS uninstall request for " + App + " (" + storeId + "): " + rc);
   if(rc != 0) throw new Exception("Uninstall request refused; inspect before retrying");
   while(timer.ElapsedMilliseconds < 11000) {
    for(int i=0;i<10;i++) if(g_main_context_iteration(IntPtr.Zero, 0) == 0) break;
    if(terminalEvent == 123) throw new Exception("Samsung reported uninstall failure; inspect before retrying");
    if(terminalEvent == 122 && Count(db, "SELECT COUNT(*)" + predicate) == 0 &&
       Count(db, "SELECT COUNT(*) FROM package_app_info WHERE package='" + pkg + "'") == 0) {
     Console.WriteLine("Package and application registration absent; host must verify full scope");
     return 0;
    }
    Thread.Sleep(100);
   }
   throw new Exception("No verified removal before deadline; inspect before retrying");
  } catch(Exception e) { Console.Error.WriteLine(e.Message); return 1; }
  finally { if(db != IntPtr.Zero) sqlite3_close(db); }
 }
}
