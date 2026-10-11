using System;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using System.Security.Cryptography;

// One-shot boot helper, invoked by AT-HUB through the TV's signed .NET host.
// No network, resident process, account changes or security-policy changes.
class Boot {
    const string State = "/opt/minimal-saver";
    const string Stock = "/usr/apps/com.samsung.tv.spotlight-ss/lib/arm/libgl-demo-app.so";
    const string OriginalHash = "4f0b36d9639a194936def6250a03db1383db284f11f74d83ec7dda50420befaa";
    const string CustomHash = "db5656113275e613d9475c09af1c768cd8ad57d60eac31213214684721cc418a";
    const string DiagnosticHash = "c6369e7dec69408e176daa252d436acf6f8e265f560504d8bd831c8023c71d61";
    [DllImport("libc.so.6")] static extern uint geteuid();
    [DllImport("libc.so.6", SetLastError=true)] static extern int mount(string source, string target, string fs, UIntPtr flags, string data);
    [DllImport("libc.so.6", SetLastError=true)] static extern int umount2(string target, int flags);
    static string Hash(string file) {
        using var input = File.OpenRead(file);
        using var sha = SHA256.Create();
        return Convert.ToHexString(sha.ComputeHash(input)).ToLowerInvariant();
    }
    static void Require(bool condition, string message) { if (!condition) throw new Exception(message); }
    static void Mount(string source, ulong flags) {
        int result = mount(source, Stock, null, new UIntPtr(flags), null);
        Require(result == 0, "mount failed errno=" + Marshal.GetLastWin32Error());
    }
    static bool HasOverlay() => File.ReadLines("/proc/self/mountinfo").Any(line => line.Split(' ')[4] == Stock);
    static void Apply(Action<string> log) {
        Require(geteuid() == 0, "must run as root");
        Require(new FileInfo("/proc/self/ns/mnt").LinkTarget == new FileInfo("/proc/1/ns/mnt").LinkTarget, "wrong mount namespace");
        if (!File.Exists(State + "/enabled")) { log("disabled"); return; }
        Require(Hash(State + "/libgl-demo-app.so") == CustomHash, "replacement hash mismatch; keeping stock");
        string current = Hash(Stock);
        if (current == CustomHash && HasOverlay()) { log("already active"); return; }
        Require(current == OriginalHash, "firmware renderer changed; keeping stock");
        Require(!HasOverlay(), "unknown existing overlay; leaving it untouched");
        bool mounted = false;
        try {
            Mount(State + "/libgl-demo-app.so", 4096); mounted = true;
            Mount(null, 4096 | 32 | 1); // remount bind read-only
            Require(Hash(Stock) == CustomHash, "mounted hash mismatch");
            mounted = false;
            log("active: read-only custom renderer overlay");
        } finally { if (mounted) umount2(Stock, 0); }
    }
    static int Main() {
        // Preserve AT-HUB's original signed diagnostic script, without editing it.
        int diagnosticStatus = 1;
        try {
            Require(Hash("/opt/etc/parseinfo.sh") == DiagnosticHash, "original diagnostic changed");
            using var process = Process.Start(new ProcessStartInfo("/opt/etc/parseinfo.sh", "&") {UseShellExecute=false});
            if (!process.WaitForExit(8000)) { process.Kill(true); throw new Exception("diagnostic timeout"); }
            diagnosticStatus = process.ExitCode;
        } catch (Exception e) { Console.Error.WriteLine("MinimalSaver diagnostic: " + e.Message); }
        try {
            using var logFile = new StreamWriter(State + "/last-boot.log", false) { AutoFlush=true };
            void Log(string text) { logFile.WriteLine(text); Console.WriteLine("MinimalSaver: " + text); }
            Log("boot_id=" + File.ReadAllText("/proc/sys/kernel/random/boot_id").Trim());
            Log("diagnostic_exit=" + diagnosticStatus);
            try { Apply(Log); } catch (Exception e) { Log("inactive: " + e.Message); }
        } catch (Exception e) { Console.Error.WriteLine("MinimalSaver: " + e.Message); }
        // The overlay is optional; failure must not obstruct the boot sequence.
        return diagnosticStatus;
    }
}
