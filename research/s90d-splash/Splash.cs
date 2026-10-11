using System;
using System.Diagnostics;
using System.IO;
using System.Runtime.InteropServices;
using System.Security.Cryptography;

// Opt-in compatibility launch through Samsung's own splash visibility callback.
static class Splash {
    const string State = "/opt/minimal-splash";
    const string Native = "/usr/bin/boot_splashscreen";
    const string Resource = "/usr/apps/com.samsung.tv.csfs/shared/res/homeloading.edj";
    static Process child;
    static StreamWriter log;
    [DllImport("libvconf.so.0")] static extern IntPtr vconf_get_str(string key);
    [DllImport("libc.so.6")] static extern void free(IntPtr pointer);
    static string Hash(string path) {
        using var input = File.OpenRead(path);
        using var sha = SHA256.Create();
        return Convert.ToHexString(sha.ComputeHash(input)).ToLowerInvariant();
    }
    static void Mark(string text) {
        try {
            log?.WriteLine((Stopwatch.GetTimestamp() / (double)Stopwatch.Frequency)
                .ToString("F6", System.Globalization.CultureInfo.InvariantCulture) + " " + text);
        } catch { /* Diagnostic I/O must not interrupt normal boot work. */ }
    }
    public static void Start() {
        try {
            if (!Directory.Exists(State) || new DirectoryInfo(State).LinkTarget != null ||
                !File.Exists(State + "/enabled") || new FileInfo(State + "/enabled").LinkTarget != null) return;
            string path = State + "/last-boot.log";
            if (File.Exists(path) && new FileInfo(path).LinkTarget != null) return;
            log = new StreamWriter(path, false) { AutoFlush = true };
            log.WriteLine("boot_id=" + File.ReadAllText("/proc/sys/kernel/random/boot_id").Trim());
            Mark("helper-entry");
            // Never reopen a splash after the system has already requested resume.
            if (File.Exists("/tmp/root_app_resume_requested") || File.Exists("/tmp/boot_splash_resumed")) {
                Mark("skip: resume already requested or acknowledged"); return;
            }
            if (!File.ReadAllText("/etc/prd_info.ini").Contains("Version=T-PTMDAKUC-0090-2130.0;")) {
                Mark("skip: firmware changed"); return;
            }
            IntPtr p = vconf_get_str("db/appfw/home_appid");
            string home = p == IntPtr.Zero ? null : Marshal.PtrToStringAnsi(p);
            if (p != IntPtr.Zero) free(p);
            if (home != "MiniHub001.Hub") { Mark("skip: custom Home not selected"); return; }
            if (Hash(Native) != "da40cc2088fd63d06fd3170fcb0e797b45125335e154b67912108bce21b29882" ||
                Hash(Resource) != "9895cdeba1abef45c60cf13057cc662f159caf94db17436713cbc9d5649b587f") {
                Mark("skip: native splash or resource changed"); return;
            }
            foreach (var process in Process.GetProcessesByName("boot_splashscre")) {
                process.Dispose(); Mark("skip: native splash already running"); return;
            }
            // Match Samsung's launch_splash.sh environment before replacing the shell.
            var start = new ProcessStartInfo("/bin/bash") { UseShellExecute = false };
            start.ArgumentList.Add("-c");
            start.ArgumentList.Add(". /etc/profile; export HOME=/home/root; exec " + Native + " " + Resource);
            start.Environment["HOME"] = "/home/root";
            child = Process.Start(start);
            Mark("native-start pid=" + child.Id);
        } catch (Exception e) { Mark("error: " + e.Message); }
    }
    public static void Finish() {
        try {
            if (child != null) {
                // Fail back to Samsung's existing timeout if its splash cannot finish.
                if (!child.WaitForExit(10000)) {
                    Mark("native deadline; stopping owned child");
                    child.Kill();
                    child.WaitForExit(1000);
                }
                Mark("native-end exit=" + (child.HasExited ? child.ExitCode.ToString() : "unknown"));
                Mark("ack=" + File.Exists("/tmp/boot_splash_resumed") +
                     " resume=" + File.Exists("/tmp/root_app_resume_requested"));
                child.Dispose();
            }
        } catch (Exception e) { Mark("finish error: " + e.Message); }
        finally { try { log?.Dispose(); } catch { } log = null; }
    }
}
