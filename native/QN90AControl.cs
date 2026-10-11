using System;
using System.Runtime.InteropServices;

// QN85QN90AAFXZA / 2301.1 only. The Mac wrapper verifies the target before upload.
class QN90AControl {
 const string Hub = "MiniHub001.Hub", Stock = "com.samsung.tv.csfs";
 const string First = "db/first_screen/type", Overlay = "db/appfw/overlay_home_appid";
 const string Auto = "db/menu/smart_hub/ontvsetting/auto_start";
 [DllImport("libvconf.so.0")] static extern IntPtr vconf_get_str(string key);
 [DllImport("libvconf.so.0")] static extern int vconf_get_int(string key, out int value);
 [DllImport("libvconf.so.0")] static extern int vconf_set_str(string key, string value);
 [DllImport("libvconf.so.0")] static extern int vconf_set_int(string key, int value);
 [DllImport("libc")] static extern void free(IntPtr p);
 static string Read(string key) {
  IntPtr p = vconf_get_str(key);
  if (p == IntPtr.Zero) throw new Exception("Missing setting: " + key);
  try { return Marshal.PtrToStringAnsi(p); } finally { free(p); }
 }
 static void Set(string key, string value) {
  if (vconf_set_str(key, value) != 0 || Read(key) != value)
   throw new Exception("Setting/readback failed: " + key);
 }
 static void SetAuto(int value) {
  int actual;
  if (vconf_set_int(Auto, value) != 0 || vconf_get_int(Auto, out actual) != 0 || actual != value)
   throw new Exception("Autostart setting/readback failed");
 }
 static int Main(string[] args) {
  try {
   if (IntPtr.Size != 4 || args.Length != 1) return 2;
   string mode = args[0];
   if (mode != "query" && mode != "overlay" && mode != "restore-overlay" && mode != "enable" && mode != "restore") return 2;
   string first = Read(First), overlay = Read(Overlay);
   int auto;
   if (vconf_get_int(Auto, out auto) != 0) throw new Exception("Missing autostart setting");
   if (mode != "query") {
    if ((first != Stock && first != Hub) || (overlay != Stock && overlay != Hub) ||
        (auto != 0 && auto != 1) || Read("db/appfw/home_appid") != "org.tizen.tv-viewer")
     throw new Exception("Unexpected configuration; inspect before changing it");
    // These setters retain Buxton's access labels. No app-service DB rows change.
    try {
     if (mode == "restore") { Set(First, Stock); Set(Overlay, Stock); SetAuto(0); }
     else if (mode == "restore-overlay") { Set(Overlay, Stock); }
     else if (mode == "overlay") { Set(Overlay, Hub); }
     // Keep Samsung's partial overlay available; firstscreen is the cached key route.
     else { Set(Overlay, Stock); Set(First, Hub); SetAuto(1); }
    } catch {
     // Best-effort rollback to the values read before this invocation.
     try { Set(First, first); } catch (Exception e) { Console.Error.WriteLine(e.Message); }
     try { Set(Overlay, overlay); } catch (Exception e) { Console.Error.WriteLine(e.Message); }
     try { SetAuto(auto); } catch (Exception e) { Console.Error.WriteLine(e.Message); }
     throw;
    }
   }
   Console.WriteLine(First + "=" + Read(First));
   Console.WriteLine(Overlay + "=" + Read(Overlay));
   if (vconf_get_int(Auto, out auto) != 0) return 3;
   Console.WriteLine(Auto + "=" + auto);
   return 0;
  } catch (Exception e) { Console.Error.WriteLine(e.Message); return 1; }
 }
}
