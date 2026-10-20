// Original Couchroot signed native launcher lifecycle (0BSD).
using System;
using System.IO;
using System.Text;

internal static partial class SamsungTvRootAgent
{
    private static string AppLauncherDirectory, AppLauncherPath, AppLauncherDigest;
    private static void PrepareAppLauncher()
    {
        if (NamespaceLink("/proc/self/ns/mnt") == NamespaceLink("/proc/1/ns/mnt"))
            throw new IOException("App launcher requires a private mount namespace");
        byte[] bytes;
        using (var resource = typeof(SamsungTvRootAgent).Assembly.GetManifestResourceStream("Couchroot.AppLauncher"))
        {
            if (resource == null || resource.Length < 52 || resource.Length > 1024 * 1024)
                throw new IOException("Missing or invalid signed native app launcher");
            using (var copy = new MemoryStream()) { resource.CopyTo(copy); bytes = copy.ToArray(); }
        }
        if (bytes[0] != 127 || bytes[1] != 'E' || bytes[2] != 'L' || bytes[3] != 'F' || bytes[4] != 1 || bytes[5] != 1 || bytes[18] != 40 || bytes[19] != 0)
            throw new IOException("Native app launcher must be ARM ELF32 little-endian");
        string digest; using (var stream = new MemoryStream(bytes)) digest = Digest(stream);
        ManagedDirectory("/opt/couchroot-agent", 493);
        string parent = "/opt/couchroot-agent/launchers";
        ManagedDirectory(parent, 448);
        if (Directory.GetDirectories(parent).Length >= 64) throw new IOException("Retained launcher limit reached; inspect stale directories");
        string directory = parent + "/" + WorkerId, binary = directory + "/app-launcher";
        // Exclusive creation; never adopt or recursively remove an existing path.
        if (mkdir(directory, 448) != 0) throw new IOException("Cannot create app launcher directory");
        bool mounted = false;
        try
        {
            using (var file = new FileStream(binary, FileMode.CreateNew, FileAccess.Write, FileShare.None)) { file.Write(bytes, 0, bytes.Length); file.Flush(true); }
            if (chmod(binary, 320) != 0 || DigestPath(binary) != digest) throw new IOException("Cannot protect or verify app launcher");
            byte[] label = Encoding.UTF8.GetBytes("User");
            foreach (string path in new[] { "/opt/couchroot-agent", parent, directory, binary })
                if (setxattr(path, "security.SMACK64", label, (UIntPtr)label.Length, 0) != 0) throw new IOException("Cannot label app launcher");
            if (mount(null, "/", null, (UIntPtr)(16384 | 262144), null) != 0) throw new IOException("Cannot privatize launcher mount propagation");
            if (mount(directory, directory, null, (UIntPtr)4096, null) != 0) throw new IOException("Cannot bind app launcher");
            mounted = true;
            if (mount(null, directory, null, (UIntPtr)(4096 | 32 | 1), null) != 0) throw new IOException("Cannot protect launcher mount");
            AppLauncherDirectory = directory; AppLauncherPath = binary; AppLauncherDigest = digest;
        }
        catch
        {
            // Never delete through a mount that failed to unmount.
            if (!mounted || umount2(directory, 0) == 0) { FileDelete(binary); try { Directory.Delete(directory); } catch { } }
            throw;
        }
    }
    private static string AppCommand(string command)
    {
        if (AppLauncherPath == null || DigestPath(CheckedPath(AppLauncherPath)) != AppLauncherDigest)
            throw new IOException("Verified native app launcher is unavailable");
        return "exec " + ShellQuote(AppLauncherPath) + " --command " + ShellQuote(command);
    }
    private static void CloseAppLauncher()
    {
        if (AppLauncherDirectory == null) return;
        if (umount2(AppLauncherDirectory, 0) == 0)
        {
            FileDelete(AppLauncherPath);
            try { Directory.Delete(AppLauncherDirectory); } catch { }
        }
        AppLauncherDirectory = AppLauncherPath = AppLauncherDigest = null;
    }
}
