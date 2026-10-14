// Test-only line protocol over the actual managed operation implementation.
// Never included in the TV payload. SPDX-License-Identifier: 0BSD
using System;
using System.IO;
using System.Text;
using System.Text.Json;
internal static partial class SamsungTvRootAgent
{
    internal static int ParityBridge(string root)
    {
        if (Environment.GetEnvironmentVariable("COUCHROOT_PARITY_CONTAINER") != "1")
            throw new InvalidOperationException("Use an isolated disposable container");
        root = Path.GetFullPath(root).TrimEnd('/') + "/";
        try {
            string line;
            while ((line = Console.ReadLine()) != null) {
                try {
                    using var request = JsonDocument.Parse(line);
                    var value = request.RootElement;
                    object result;
                    if (Text(value, "op") == "parity.exec") {
                        var r = Execute(Text(value, "command"), value.GetProperty("timeout_ms").GetInt32());
                        result = new {exit_code=r.ExitCode, timed_out=r.TimedOut,
                            stdout=Convert.ToBase64String(r.StandardOutput), stderr=Convert.ToBase64String(r.StandardError)};
                    } else result = Operation(value, root, root);
                    Console.WriteLine(JsonSerializer.Serialize(new {ok=true,result}));
                } catch (Exception e) {
                    Console.WriteLine(JsonSerializer.Serialize(new {ok=false,outcome="failed",error=e.GetType().Name}));
                }
            }
        } finally {StopJobs();CloseTransfers();}
        return 0;
    }
}
